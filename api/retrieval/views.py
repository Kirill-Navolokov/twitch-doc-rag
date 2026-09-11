import json
import logging
import time
from collections.abc import Iterator

from django.conf import settings
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from rest_framework import renderers
from rest_framework.request import Request
from rest_framework.views import APIView

from retrieval.generation import GenerationError, generate, select_model
from retrieval.service import retrieve
from retrieval.types import RetrievedChunk, TaskDescriptor

logger = logging.getLogger(__name__)

FALLBACK_TEXT = "Sorry, we can't find any information related to your request"

Citation = dict[str, str | int | float]
EventData = dict[str, str | list[Citation]]


def _sse_event(event: str, data: EventData) -> bytes:
    # json.dumps without indent keeps data on one line, which SSE's line-oriented framing requires.
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def _citation(chunk: RetrievedChunk) -> Citation:
    return {
        "source_url": chunk.source_url,
        "title": chunk.title,
        "chunk_index": chunk.chunk_index,
        "score": chunk.score,
    }


def _log_query(
    question: str, chunks: list[RetrievedChunk], *, fallback_triggered: bool, start: float
) -> None:
    retrieved = [
        {"source_url": chunk.source_url, "chunk_index": chunk.chunk_index, "score": chunk.score}
        for chunk in chunks
    ]
    logger.info(
        "rag_query question=%r fallback_triggered=%s response_time_ms=%d retrieved_chunks=%s",
        question,
        fallback_triggered,
        int((time.monotonic() - start) * 1000),
        retrieved,
    )


def _stream_answer(question: str) -> Iterator[bytes]:
    # Timing and logging live here rather than in the view: StreamingHttpResponse returns before a
    # single byte is produced, and this generator only runs as the server iterates it.
    start = time.monotonic()
    chunks = retrieve(question)
    top_score = max((chunk.score for chunk in chunks), default=None)

    if top_score is None or top_score < settings.RELEVANCE_THRESHOLD:
        yield _sse_event("fallback", {"text": FALLBACK_TEXT})
        _log_query(question, chunks, fallback_triggered=True, start=start)
        return

    yield _sse_event("citations", {"citations": [_citation(chunk) for chunk in chunks]})

    try:
        result = generate(select_model(TaskDescriptor()), question, chunks, stream=True)
        for token in result.token_stream:
            yield _sse_event("token", {"text": token})
        yield _sse_event("done", {})
    # Catching around the whole loop covers a failure on the first token and one that interrupts an
    # answer already partly sent, which generation raises without retrying.
    except GenerationError as exc:
        yield _sse_event("error", {"message": str(exc)})
    _log_query(question, chunks, fallback_triggered=False, start=start)


class AskView(APIView):
    def perform_content_negotiation(
        self, request: Request, force: bool = False
    ) -> tuple[renderers.BaseRenderer, str]:
        # The answer is a hand-built StreamingHttpResponse that never passes through DRF's renderer
        # pipeline, so the negotiated renderer only ever formats DRF's own error responses. Left to
        # negotiate, DRF would reject the `Accept: text/event-stream` every real SSE client sends.
        renderer = renderers.JSONRenderer()
        return renderer, renderer.media_type

    def post(self, request: Request) -> StreamingHttpResponse | JsonResponse:
        # A JSON body is not necessarily an object: a list or a bare string parses fine and has no
        # .get(), which would otherwise crash before the request is recognised as malformed.
        body = request.data if isinstance(request.data, dict) else {}
        question = body.get("question")
        if not isinstance(question, str) or not question.strip():
            return JsonResponse({"error": "question is required"}, status=400)

        response = StreamingHttpResponse(_stream_answer(question), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        # Stops a reverse proxy from buffering the stream into one response at the end.
        response["X-Accel-Buffering"] = "no"
        response["Access-Control-Allow-Origin"] = "*"
        return response

    def options(self, request: Request) -> HttpResponse:
        response = HttpResponse()
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type"
        return response
