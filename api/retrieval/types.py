from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source_url: str
    title: str
    chunk_index: int
    score: float
