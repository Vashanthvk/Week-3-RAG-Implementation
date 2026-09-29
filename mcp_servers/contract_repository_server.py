"""Week 9 Task Set F -- "server two": the contract-repository server.

Stands in for the third-party server the knowledge team stood up (see
week9_evidence/risk_note.md for the supply-chain framing). Genuinely
independent of clause_search_server.py: separate process, separate data
source (a small JSON repository keyed by contract id), no shared code.
Exposes exactly what the brief asks for -- lookup by contract id, its
effective date, and its amendment chain -- and nothing else. No LLM call
inside this server either.

Run standalone (stdio transport):
    python mcp_servers/contract_repository_server.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastmcp import FastMCP


DATA_PATH = Path(__file__).with_name("contract_repository_data.json")
REPOSITORY: dict[str, dict[str, Any]] = json.loads(DATA_PATH.read_text(encoding="utf-8"))


mcp = FastMCP(
    name="contract-repository",
    instructions=(
        "Look up a contract by its repository id: its parties and title, "
        "its effective date, and its amendment chain. Contract ids look "
        "like 'MSA-2021-0142'. This server does not search clause text -- "
        "for that, use the clause-search server."
    ),
)


def _known_ids() -> str:
    return ", ".join(sorted(REPOSITORY.keys()))


def _validate_contract_id(contract_id: Any) -> dict[str, Any] | None:
    """Return a structured error for values that cannot be repository ids."""

    if not isinstance(contract_id, str):
        return {
            "found": False,
            "error": (
                "Invalid contract_id: expected a string, "
                f"received {type(contract_id).__name__}."
            ),
        }
    if not contract_id.strip():
        return {
            "found": False,
            "error": "Invalid contract_id: expected a non-empty string.",
        }
    return None


def _missing_contract_error(contract_id: str) -> dict[str, Any]:
    return {
        "found": False,
        "error": f"No contract with id '{contract_id}' in the repository. Known ids: {_known_ids()}.",
    }


@mcp.tool
def lookup_contract(contract_id: Any) -> dict[str, Any]:
    """Look up a contract's title and parties by its repository id (for
    example 'MSA-2021-0142'). Use this to confirm a contract id exists and
    see which parties it is between before calling the other two tools.
    """

    validation_error = _validate_contract_id(contract_id)
    if validation_error:
        return validation_error

    record = REPOSITORY.get(contract_id)
    if not record:
        return _missing_contract_error(contract_id)
    return {
        "found": True,
        "contract_id": contract_id,
        "title": record["title"],
        "parties": record["parties"],
    }


@mcp.tool
def get_effective_date(contract_id: Any) -> dict[str, Any]:
    """Return the effective date of a contract by its repository id (for
    example 'MSA-2021-0142'). This is the ORIGINAL contract's effective
    date, not an amendment's -- call get_amendment_chain for amendment
    dates.
    """

    validation_error = _validate_contract_id(contract_id)
    if validation_error:
        return validation_error

    record = REPOSITORY.get(contract_id)
    if not record:
        return _missing_contract_error(contract_id)
    return {"found": True, "contract_id": contract_id, "effective_date": record["effective_date"]}


@mcp.tool
def get_amendment_chain(contract_id: Any) -> dict[str, Any]:
    """Return the ordered list of amendments to a contract by its
    repository id (for example 'MSA-2021-0142'), each with its own
    effective date and a summary of what it changed (e.g. clause
    renumbering). Returns an empty list -- not an error -- for a contract
    that has never been amended; that is a normal, valid state, distinct
    from the contract id not existing at all.
    """

    validation_error = _validate_contract_id(contract_id)
    if validation_error:
        return validation_error

    record = REPOSITORY.get(contract_id)
    if not record:
        return _missing_contract_error(contract_id)
    return {
        "found": True,
        "contract_id": contract_id,
        "current_clause_range": record["current_clause_range"],
        "amendments": record["amendments"],
    }


if __name__ == "__main__":
    mcp.run()
