"""Small, dependency-free observability helpers for the Week 11 RAG workflow."""

from __future__ import annotations

import hashlib
from time import perf_counter


PROMPT_VERSION = "legal-contract-rag-v2.0"


def context_id(source, page, content):
    """Return a stable, non-sensitive identifier for a retrieved chunk."""
    identity = f"{source}|{page}|{content}".encode("utf-8")
    return "ctx_" + hashlib.sha256(identity).hexdigest()[:12]


def estimate_tokens(text):
    """Fallback estimate used only when the local provider reports no usage."""
    return max(0, (len(text or "") + 3) // 4)


def span(name, started_at, *, input_tokens=0, output_tokens=0, cost_usd=0.0, **extra):
    """Create a JSON-safe span with a monotonic latency measurement."""
    value = {
        "name": name,
        "latency_ms": round((perf_counter() - started_at) * 1000, 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 8),
    }
    value.update(extra)
    return value


def cost_by_stage(spans):
    """Aggregate trace span costs into the stages required by the brief."""
    stages = {"retrieval": 0.0, "generation": 0.0, "tools": 0.0}
    for item in spans:
        stage = item.get("stage")
        if stage in stages:
            stages[stage] += float(item.get("cost_usd", 0.0) or 0.0)
    return {name: round(value, 8) for name, value in stages.items()}
