from shared.voyage import count_tokens

from ingestion.chunker import MAX_CHUNK_TOKENS, chunk_markdown

SENTENCE = "The Helix endpoint returns a paginated list of broadcaster records for the caller. "


def prose(sentences: int) -> str:
    return (SENTENCE * sentences).strip()


def paragraphs(count: int, sentences: int = 6) -> str:
    return "\n\n".join(prose(sentences) for _ in range(count))


def table(rows: int, columns: int = 4) -> str:
    header = "| " + " | ".join(f"column{index}" for index in range(columns)) + " |"
    separator = "| " + " | ".join("---" for _ in range(columns)) + " |"
    body = [
        "| " + " | ".join(f"row{row}field{column}" for column in range(columns)) + " |"
        for row in range(rows)
    ]
    return "\n".join([header, separator, *body])


def code_block(lines: int) -> str:
    body = "\n".join(f'    print("streams response line {index}")' for index in range(lines))
    return f"```python\n{body}\n```"


def test_short_document_stays_one_chunk() -> None:
    text = "# Twitch API\n\nA short overview of the reference documentation."

    assert chunk_markdown(text) == [text]


def test_empty_document_produces_no_chunks() -> None:
    assert chunk_markdown("") == []
    assert chunk_markdown("\n\n   \n") == []


def test_splits_at_top_level_heading_boundaries() -> None:
    text = "# Title\n\nIntro.\n\n## Get Streams\n\nBody one.\n\n## Get Users\n\nBody two."

    chunks = chunk_markdown(text)

    assert chunks == [
        "# Title\n\nIntro.\n",
        "## Get Streams\n\nBody one.\n",
        "## Get Users\n\nBody two.",
    ]


def test_oversized_section_falls_back_to_subheadings() -> None:
    text = "\n\n".join(
        [
            "## Get Streams",
            "### Request",
            paragraphs(5),
            "### Response",
            paragraphs(5),
            "### Errors",
            paragraphs(5),
        ]
    )

    chunks = chunk_markdown(text)

    assert [chunk.splitlines()[0] for chunk in chunks] == [
        "## Get Streams",
        "### Request",
        "### Response",
        "### Errors",
    ]
    assert all(count_tokens(chunk) <= MAX_CHUNK_TOKENS for chunk in chunks)


def test_document_without_headings_splits_on_paragraph_boundaries() -> None:
    blocks = [f"Paragraph {index}. {prose(6)}" for index in range(16)]
    text = "\n\n".join(blocks)

    chunks = chunk_markdown(text)

    assert len(chunks) > 1
    assert all(count_tokens(chunk) <= MAX_CHUNK_TOKENS for chunk in chunks)
    rejoined = "\n\n".join(chunks)
    assert rejoined == text


def test_oversized_subsection_table_splits_by_rows_repeating_header() -> None:
    text = f"## Get Streams\n\n### Response Fields\n\n{table(rows=120)}"

    chunks = chunk_markdown(text)

    assert len(chunks) > 2
    body_rows: list[str] = []
    for chunk in chunks[1:]:
        lines = chunk.splitlines()
        assert lines[0] == "### Response Fields"
        assert lines[2].startswith("| column0")
        assert set(lines[3].replace(" ", "")) <= {"|", "-"}
        body_rows.extend(lines[4:])
    assert body_rows == table(rows=120).splitlines()[2:]
    assert all(count_tokens(chunk) <= MAX_CHUNK_TOKENS for chunk in chunks)


def test_headless_document_that_is_one_big_table_splits_by_rows() -> None:
    text = table(rows=120)

    chunks = chunk_markdown(text)

    assert len(chunks) > 1
    for chunk in chunks:
        lines = chunk.splitlines()
        assert lines[0].startswith("| column0")
        assert set(lines[1].replace(" ", "")) <= {"|", "-"}
    assert all(count_tokens(chunk) <= MAX_CHUNK_TOKENS for chunk in chunks)


def test_no_chunk_boundary_falls_inside_a_table_row() -> None:
    chunks = chunk_markdown(table(rows=120))

    for chunk in chunks:
        for line in chunk.splitlines():
            assert line.startswith("|") and line.endswith("|")


def test_table_straddling_a_paragraph_fallback_boundary_stays_intact() -> None:
    embedded = table(rows=12)
    text = "\n\n".join([paragraphs(8), embedded, paragraphs(8)])

    chunks = chunk_markdown(text)

    assert len(chunks) > 1
    assert any(embedded in chunk for chunk in chunks)


def test_oversized_table_reached_through_the_paragraph_fallback_splits_by_rows() -> None:
    text = "\n\n".join([paragraphs(8), table(rows=120)])

    chunks = chunk_markdown(text)

    table_chunks = [chunk for chunk in chunks if chunk.startswith("| column0")]
    assert len(table_chunks) > 1
    for chunk in table_chunks:
        lines = chunk.splitlines()
        assert set(lines[1].replace(" ", "")) <= {"|", "-"}
        assert all(line.startswith("|") and line.endswith("|") for line in lines)


def test_oversized_prose_subsection_falls_back_to_paragraphs() -> None:
    text = f"## Get Streams\n\n### Description\n\n{paragraphs(16)}"

    chunks = chunk_markdown(text)

    assert len(chunks) > 2
    assert chunks[1].startswith("### Description")
    assert all(count_tokens(chunk) <= MAX_CHUNK_TOKENS for chunk in chunks)


def test_heading_inside_a_fenced_code_block_is_not_a_split_boundary() -> None:
    fenced = "```markdown\n## Get Streams\n\n### Request\nsample doc snippet\n```"
    text = f"## Examples\n\n{fenced}\n\n## Errors\n\nSomething else."

    chunks = chunk_markdown(text)

    assert len(chunks) == 2
    assert fenced in chunks[0]
    assert chunks[1].startswith("## Errors")


def test_paragraph_fallback_never_splits_a_fenced_code_block() -> None:
    fenced = code_block(lines=40)
    text = "\n\n".join([paragraphs(6), fenced, paragraphs(6)])

    chunks = chunk_markdown(text)

    assert len(chunks) > 1
    assert sum(chunk.count("```") for chunk in chunks) == 2
    assert any(fenced in chunk for chunk in chunks)


def test_oversized_fenced_code_block_is_kept_whole_over_the_cap() -> None:
    fenced = code_block(lines=400)

    chunks = chunk_markdown(fenced)

    assert chunks == [fenced]
    assert count_tokens(chunks[0]) > MAX_CHUNK_TOKENS


def test_oversized_single_paragraph_falls_back_to_sentence_boundaries() -> None:
    text = prose(120)

    chunks = chunk_markdown(text)

    assert len(chunks) > 1
    assert all(count_tokens(chunk) <= MAX_CHUNK_TOKENS for chunk in chunks)
    assert all(chunk.endswith(".") for chunk in chunks)


def test_single_oversized_sentence_is_hard_split_as_a_last_resort() -> None:
    text = "word " * 4000

    chunks = chunk_markdown(text)

    assert len(chunks) > 1
    assert all(count_tokens(chunk) <= MAX_CHUNK_TOKENS for chunk in chunks)
    assert "".join(chunks) == text
