from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source_url: str
    title: str
    chunk_index: int
    score: float


@dataclass(frozen=True)
class TaskDescriptor:
    kind: str = "answer_generation"


@dataclass(frozen=True)
class ModelHandle:
    provider: str
    model_id: str


# Not frozen like the others: it carries a live generator, which neither compares nor hashes well.
@dataclass
class GenerationResult:
    citations: list[RetrievedChunk]
    text: str | None = None
    token_stream: Iterator[str] | None = None
