import functools
import logging
import time
from collections.abc import Iterator

from django.conf import settings
from groq import APITimeoutError, Groq, GroqError, RateLimitError
from groq.types.chat import ChatCompletionMessageParam

from retrieval.types import GenerationResult, ModelHandle, RetrievedChunk, TaskDescriptor

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

SYSTEM_PROMPT = (
    "You answer developer questions about the Twitch API using only the documentation excerpts "
    "supplied with the question. If the excerpts do not contain the answer, say so plainly rather "
    "than guessing or drawing on anything you know from elsewhere. Name the title of every excerpt "
    "you rely on, so the reader can find the section it came from."
)

USER_PROMPT_TEMPLATE = """Documentation excerpts:
{excerpts}

Question: {question}"""

EXCERPT_TEMPLATE = """[{number}] {title} - {source_url}
{text}"""


class GenerationError(Exception):
    """A Groq failure, in a type the caller can catch without importing the provider's own."""


@functools.cache
def _client() -> Groq:
    # max_retries=0 because the SDK retries on its own by default, which would multiply FR-4's
    # attempts and stretch the wait well past the 2/4/8s the retry loop below promises.
    return Groq(api_key=settings.GROQ_API_KEY, max_retries=0)


def _build_messages(
    question: str, chunks: list[RetrievedChunk]
) -> list[ChatCompletionMessageParam]:
    excerpts = "\n\n".join(
        EXCERPT_TEMPLATE.format(
            number=number,
            title=chunk.title,
            source_url=chunk.source_url,
            text=chunk.text,
        )
        for number, chunk in enumerate(chunks, start=1)
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(excerpts=excerpts, question=question),
        },
    ]


def _backoff_or_fail(attempt: int, exc: GroqError) -> None:
    if attempt == MAX_RETRIES:
        raise GenerationError(
            f"groq generation failed after {MAX_RETRIES} retries: {exc}"
        ) from exc
    delay = 2 ** (attempt + 1)
    logger.warning("groq generate attempt=%d retrying_in=%ds reason=%s", attempt + 1, delay, exc)
    time.sleep(delay)


def _complete(model: ModelHandle, messages: list[ChatCompletionMessageParam]) -> str | None:
    for attempt in range(MAX_RETRIES + 1):
        try:
            completion = _client().chat.completions.create(
                model=model.model_id, messages=messages, stream=False
            )
            return completion.choices[0].message.content
        except (RateLimitError, APITimeoutError) as exc:
            _backoff_or_fail(attempt, exc)
        except GroqError as exc:
            raise GenerationError(f"groq generation failed: {exc}") from exc


def _stream_tokens(model: ModelHandle, messages: list[ChatCompletionMessageParam]) -> Iterator[str]:
    first_token_yielded = False
    for attempt in range(MAX_RETRIES + 1):
        try:
            for chunk in _client().chat.completions.create(
                model=model.model_id, messages=messages, stream=True
            ):
                content = chunk.choices[0].delta.content
                # Groq opens the stream with a role-only delta; that is not a token, so a failure
                # right after it is still part of the retryable connection phase.
                if not content:
                    continue
                first_token_yielded = True
                yield content
            return
        except (RateLimitError, APITimeoutError) as exc:
            # Retrying here would re-send text the caller has already forwarded downstream.
            if first_token_yielded:
                raise GenerationError(f"groq generation failed mid-stream: {exc}") from exc
            _backoff_or_fail(attempt, exc)
        except GroqError as exc:
            raise GenerationError(f"groq generation failed: {exc}") from exc


def select_model(task: TaskDescriptor) -> ModelHandle:
    # The seam exists so a second provider can be routed to later; until then every task kind
    # resolves to the one configured model.
    return ModelHandle(provider="groq", model_id=settings.GROQ_MODEL)


def generate(
    model: ModelHandle,
    question: str,
    chunks: list[RetrievedChunk],
    stream: bool = True,
) -> GenerationResult:
    messages = _build_messages(question, chunks)
    if stream:
        # _stream_tokens is a generator function, so Groq is not called until the caller iterates:
        # citations reach the caller without waiting on the provider (or on its retry backoff).
        return GenerationResult(citations=chunks, token_stream=_stream_tokens(model, messages))
    return GenerationResult(citations=chunks, text=_complete(model, messages))
