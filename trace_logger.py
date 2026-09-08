import json
from datetime import datetime, timezone
from pathlib import Path


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