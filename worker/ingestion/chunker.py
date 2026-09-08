import re
from dataclasses import dataclass

from shared.voyage import count_tokens

MAX_CHUNK_TOKENS = 1000

FENCE_RE = re.compile(r"^ {0,3}(```|~~~)")
TABLE_SEPARATOR_RE = re.compile(r"^[\s|:-]+$")
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.?!])(?:\s+(?=[A-Z])|\n)")


@dataclass(frozen=True)
class Table:
    headings: list[str]
    header: str
    separator: str
    rows: list[str]


def chunk_markdown(text: str) -> list[str]:
    return [chunk for section in _split_by_heading(text, 2) for chunk in _split_section(section)]


def _split_section(section: str) -> list[str]:
    if _fits(section):
        return [section]
    subsections = _split_by_heading(section, 3)
    if len(subsections) > 1:
        return [chunk for subsection in subsections for chunk in _split_oversized(subsection)]
    return _split_oversized(section)


def _split_oversized(unit: str) -> list[str]:
    if _fits(unit):
        return [unit]
    table = _parse_table(unit)
    if table is not None:
        return _split_table(table)
    return _split_paragraphs(unit)


def _split_paragraphs(unit: str) -> list[str]:
    atoms = _split_atoms(unit)
    if len(atoms) == 1:
        return _split_atom(atoms[0])
    # Every group here holds fewer atoms than `unit` did, so re-entering the ladder terminates.
    return [chunk for group in _group(atoms, "\n\n") for chunk in _split_oversized(group)]


def _split_atom(atom: str) -> list[str]:
    # A fenced code block is indivisible; the cap yields to that invariant.
    if _is_fenced(atom):
        return [atom]
    # Grouping whole lines before reaching for sentence boundaries is what keeps a split from
    # landing inside a table row, since a row is always exactly one line.
    return [
        chunk
        for group in _group(atom.split("\n"), "\n")
        for chunk in ([group] if _fits(group) else _split_sentences(group))
    ]


def _split_sentences(line: str) -> list[str]:
    return [
        chunk
        for group in _group(SENTENCE_BOUNDARY_RE.split(line), " ")
        for chunk in ([group] if _fits(group) else _hard_split(group))
    ]


def _hard_split(text: str) -> list[str]:
    if _fits(text):
        return [text]
    middle = len(text) // 2
    return _hard_split(text[:middle]) + _hard_split(text[middle:])


def _fits(text: str) -> bool:
    return count_tokens(text) <= MAX_CHUNK_TOKENS


def _group(units: list[str], joiner: str, prefix: str = "") -> list[str]:
    groups: list[str] = []
    current: list[str] = []
    for unit in units:
        if current and not _fits(prefix + joiner.join([*current, unit])):
            groups.append(prefix + joiner.join(current))
            current = [unit]
        else:
            current.append(unit)
    if current:
        groups.append(prefix + joiner.join(current))
    return groups


def _fence_flags(lines: list[str]) -> list[bool]:
    flags: list[bool] = []
    open_marker: str | None = None
    for line in lines:
        match = FENCE_RE.match(line)
        if open_marker is None:
            open_marker = match.group(1) if match else None
            flags.append(match is not None)
        else:
            flags.append(True)
            if match and match.group(1) == open_marker:
                open_marker = None
    return flags


def _split_by_heading(text: str, level: int) -> list[str]:
    prefix = "#" * level + " "
    lines = text.split("\n")
    parts: list[str] = []
    current: list[str] = []
    for line, in_fence in zip(lines, _fence_flags(lines), strict=True):
        if current and not in_fence and line.startswith(prefix):
            parts.append("\n".join(current))
            current = []
        current.append(line)
    parts.append("\n".join(current))
    return [part for part in parts if part.strip()]


def _split_atoms(unit: str) -> list[str]:
    """Blank-line-separated blocks, each fenced code block kept whole as one indivisible atom."""
    lines = unit.split("\n")
    atoms: list[str] = []
    current: list[str] = []
    was_in_fence = False
    for line, in_fence in zip(lines, _fence_flags(lines), strict=True):
        if in_fence != was_in_fence or (not in_fence and not line.strip()):
            if current:
                atoms.append("\n".join(current))
                current = []
            was_in_fence = in_fence
        if in_fence or line.strip():
            current.append(line)
    if current:
        atoms.append("\n".join(current))
    return atoms


def _is_fenced(text: str) -> bool:
    return FENCE_RE.match(text) is not None


def _parse_table(unit: str) -> Table | None:
    lines = [line for line in unit.split("\n") if line.strip()]
    headings = [line for line in lines if line.lstrip().startswith("#")]
    rows = [line for line in lines if not line.lstrip().startswith("#")]
    if len(rows) < 3 or not all("|" in row for row in rows):
        return None
    if not _is_table_separator(rows[1]):
        return None
    return Table(headings=headings, header=rows[0], separator=rows[1], rows=rows[2:])


def _is_table_separator(line: str) -> bool:
    return "|" in line and "-" in line and TABLE_SEPARATOR_RE.match(line) is not None


def _split_table(table: Table) -> list[str]:
    heading_lines = [*table.headings, ""] if table.headings else []
    header_block = "\n".join([*heading_lines, table.header, table.separator])
    return _group(table.rows, "\n", prefix=header_block + "\n")
