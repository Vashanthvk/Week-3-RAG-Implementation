import json
from datetime import datetime, timezone
from pathlib import Path

from observability import PROMPT_VERSION, context_id, cost_by_stage


TRACE_DIR = Path("traces")
TRACE_FILE = TRACE_DIR / "traces.jsonl"


def _next_trace_id():
    """Return the next sequential trace ID."""
    if not TRACE_FILE.exists():
        return 1

    count = 0

    with TRACE_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                count += 1

    return count + 1


def save_trace(
    question,
    answer,
    retrieval,
    results,
    sources,
    model_name,
    spans=None,
    prompt_version=PROMPT_VERSION,
    input_type="text",
):
    """
    Save one complete RAG execution as a JSONL trace.

    One line in traces/traces.jsonl = one RAG request.
    """

    TRACE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    retrieved_chunks = []

    for result in results:

        document = result.get(
            "document",
            {}
        )

        metadata = document.get(
            "metadata",
            {}
        ) or {}

        retrieved_chunks.append(
            {
                "context_id": context_id(
                    metadata.get("source", "Unknown"),
                    metadata.get("page_label", metadata.get("page", 1)),
                    document.get("content", ""),
                ),
                "rank": result.get("rank"),

                "rrf_score": result.get(
                    "rrf_score"
                ),

                "relevance_score": result.get(
                    "keyword_score",
                    0.0
                ),

                "document": metadata.get(
                    "source",
                    "Unknown"
                ),

                "page": metadata.get(
                    "page_label",
                    metadata.get(
                        "page",
                        1
                    )
                ),

                "content": document.get(
                    "content",
                    ""
                ),
            }
        )

    trace = {
        "trace_id": _next_trace_id(),

        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),

        "question": question,

        "model": model_name,
        "prompt_version": prompt_version,
        "input_type": input_type,

        "retrieval": {
            "attempt": retrieval.get(
                "attempt"
            ),

            "retry_used": retrieval.get(
                "retry_used"
            ),

            "retrieved_chunk_count": len(
                results
            ),
        },

        "retrieved_chunks": retrieved_chunks,

        "final_answer": answer,

        "sources": sources,
        "spans": spans or [],
        "cost_by_stage_usd": cost_by_stage(spans or []),
    }

    with TRACE_FILE.open(
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            json.dumps(
                trace,
                ensure_ascii=False
            )
            + "\n"
        )

    return trace


def read_traces():
    """Read all saved traces."""

    if not TRACE_FILE.exists():
        return []

    traces = []

    with TRACE_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            if line.strip():

                traces.append(
                    json.loads(line)
                )

    return traces
