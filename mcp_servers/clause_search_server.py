"""Week 9 Task Set F -- "server one": our own clause-search MCP server.

Exposes exactly the retrieval/lookup capability of this app over MCP so any
MCP-speaking agent (ours or someone else's) can call it -- not just code we
wired in by hand. Deliberately contains NO LLM call: the server offers a
capability (search a vector+keyword index, resolve a defined term), the
host (the agent process) runs the model. Putting an LLM call in here would
be exactly the mistake the brief warns about.

Run standalone (stdio transport, the MCP default):
    python mcp_servers/clause_search_server.py

Toggle the "before" (blunt) error text for the req #5 demonstration:
    CLAUSE_SEARCH_LEGACY_ERRORS=1 python mcp_servers/clause_search_server.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP

# rag.py's own module-level print() calls (the "LOADING LEGAL CONTRACT
# RAG" banner, ChromaDB/BM25 status lines) run at import time, before
# mcp.run() below has a chance to set up its stdio protocol protection --
# so they can end up buffered in Python's stdout and later flushed onto
# the same pipe the JSON-RPC wire uses, corrupting a message frame (seen
# as "Failed to parse JSONRPC message from server" on the client side).
# Route them to stderr for just this import, then restore the real
# stdout so mcp.run() gets the untouched object it needs to claim.
_real_stdout = sys.stdout
sys.stdout = sys.stderr
try:
    from rag import bm25, documents, retrieve_with_retry, vector_store
finally:
    sys.stdout = _real_stdout

from hybrid_retrieval import get_filename


LEGACY_ERRORS = os.environ.get("CLAUSE_SEARCH_LEGACY_ERRORS") == "1"

CONTRACT_VERSIONS = [
    "Employment_Agreement",
    "Lease_Agreement",
    "Non_Disclosure_Agreement",
    "Master_Service_Agreement",
    "Software_License_Agreement",
]

KNOWN_DEFINED_TERMS_BY_CONTRACT = {
    "Master_Service_Agreement": ["Cause", "Notice Period", "Renewal Term"],
    "Software_License_Agreement": ["Initial Term", "Termination Notice Period", "Renewal Date"],
    "Employment_Agreement": [],
    "Lease_Agreement": [],
    "Non_Disclosure_Agreement": [],
}


mcp = FastMCP(
    name="clause-search",
    instructions=(
        "Search this firm's ingested contracts and resolve defined terms. "
        "This server never drafts prose or calls a language model -- it "
        "only returns raw clause text and defined-term lookups; composing "
        "an answer from that evidence is the calling agent's job."
    ),
)


@mcp.tool
def retrieve_contract_evidence(question: str) -> dict[str, Any]:
    """Search across every ingested contract and return the single
    top-ranked clause chunk relevant to a legal question.

    Use this first for any question about contract terms. Returns the
    source contract file, page, a text snippet of the matching clause, and
    a 0-1 relevance score. Does NOT look up what a specific defined term
    (e.g. "Cause", "Notice Period") means -- call get_definitions for
    that. Does NOT draft an answer.
    """

    retrieval = retrieve_with_retry(vector_store, documents, bm25, question)
    results = retrieval["results"][:1]

    if not results:
        return {"found": False, "results": [], "message": "No relevant contract clause was found for this question."}

    top = results[0]
    metadata = top["document"]["metadata"]
    return {
        "found": True,
        "source": get_filename(metadata.get("source")),
        "page": metadata.get("page_label", metadata.get("page", 1)),
        "score": round(top.get("keyword_score", 0.0), 4),
        "snippet": top["document"]["content"][:600],
    }


def _resolve_contract_version(contract_version: str) -> str | None:
    normalized = str(contract_version or "").strip()
    if normalized.endswith(".pdf"):
        normalized = normalized[:-4]
    lookup = {v.lower(): v for v in CONTRACT_VERSIONS}
    return lookup.get(normalized.lower())


@mcp.tool
def get_definitions(term: str, contract_version: str) -> dict[str, Any]:
    """Look up the literal meaning of ONE named defined term (for example
    'Cause' or 'Notice Period') inside a single contract's Definitions
    section.

    contract_version must be exactly one of: Employment_Agreement,
    Lease_Agreement, Non_Disclosure_Agreement, Master_Service_Agreement,
    Software_License_Agreement. Call retrieve_contract_evidence first to
    find out which contract is relevant and to see which defined terms it
    actually references -- this tool does not search broadly and does not
    draft an answer, it only resolves one exact term you already know the
    name of.
    """

    normalized_version = _resolve_contract_version(contract_version)
    if normalized_version is None:
        if LEGACY_ERRORS:
            return {"found": False, "error": "Error 2: bad contract_version"}
        return {
            "found": False,
            "error": (
                f"'{contract_version}' is not a known contract. Valid values for "
                f"contract_version are: {', '.join(CONTRACT_VERSIONS)}. Call "
                "retrieve_contract_evidence first if you don't know which contract "
                "applies to this question."
            ),
        }

    source_name = f"{normalized_version}.pdf"
    matching_chunks = [
        doc["content"] for doc in documents
        if get_filename(doc.get("metadata", {}).get("source")) == source_name
    ]
    full_text = re.sub(r"\s+", " ", " ".join(matching_chunks))
    normalized_term = re.sub(r"\s+", " ", term or "").strip()

    pattern = re.compile(r'"' + re.escape(normalized_term) + r'"\s+means\s+([^.]+\.)', re.IGNORECASE)
    match = pattern.search(full_text)

    if not match:
        if LEGACY_ERRORS:
            # BEFORE (req #5): unrecoverable -- the model has no way to
            # know what it should try instead.
            return {"found": False, "error": "Error 3"}

        # AFTER (req #5): recoverable -- names what actually exists in
        # THIS contract, so the model's next action is obvious.
        known_terms = KNOWN_DEFINED_TERMS_BY_CONTRACT.get(normalized_version, [])
        if known_terms:
            hint = f"This contract's defined terms are: {', '.join(known_terms)}."
        else:
            hint = f"{normalized_version.replace('_', ' ')} has no Definitions section at all -- read the clause text directly instead."
        return {
            "found": False,
            "error": f"'{normalized_term}' is not a defined term in {normalized_version}. {hint}",
        }

    return {
        "found": True,
        "term": normalized_term,
        "contract_version": normalized_version,
        "definition": match.group(1).strip(),
    }


if __name__ == "__main__":
    mcp.run()
