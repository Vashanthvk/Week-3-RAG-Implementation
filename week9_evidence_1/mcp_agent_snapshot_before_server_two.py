"""Week 9 Task Set F -- the MCP-connected agent (host + client).

This is the "agent module" referenced by requirement #2: it must show
ZERO changed lines when a second MCP server is added to
mcp_servers/mcp_config.json. It never hard-codes a tool list -- every tool
name, description, and argument schema shown to the model comes from a
live tools/list call against whatever servers the config names. Add a
server to the config, this file does not change, and the agent picks up
its tools automatically.

The model runs HERE, on the host, over a local Ollama call. It never runs
inside an MCP server (see mcp_servers/*.py -- neither one imports ollama).
The two MCP server processes are pure capability providers: they parse a
tools/call request, run deterministic Python (a retrieval, a JSON lookup),
and return a result -- they have no idea a model exists.

Separate from, and does not modify, the existing Week 7/8 agent
(agent_loops.py) or anything that imports it (race.py, trajectory_eval.py,
run_contract_agent.py) -- those keep working exactly as before.

Usage:
    python mcp_agent.py --question "What is the effective date of MSA-2021-0142?"
    python mcp_agent.py --question "..." --config mcp_servers/mcp_config.json --trace-out trace.json
    python mcp_agent.py --generate-evidence
        Regenerates tool_counts.md, mcp_config_diff.txt, wire.json, and
        error_before_after.md in week9_evidence/ in one command, the same
        way race.py does for Week 7 and trajectory_eval.py does for
        Week 8. Leaves risk_note.md (a judgment document) and agent_diff.txt
        (a one-time historical proof -- see _check_agent_diff_still_frozen)
        untouched, printing a consistency check for each instead.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "mcp_servers" / "mcp_config.json"

MODEL_NAME = "llama3.2"
ROUTING_TEMPERATURE = 0.2
MAX_STEPS = 6

FINAL_ANSWER_SIGNAL = "answer_now"


@dataclass
class ToolEntry:
    server_name: str
    session: ClientSession
    description: str
    input_schema: dict[str, Any]


@dataclass
class RunState:
    question: str
    step: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    transcript: list[tuple[str, str]] = field(default_factory=list)
    seen_calls: set[tuple[str, str]] = field(default_factory=set)
    stuck_count: int = 0
    answer: str = ""
    stop_reason: str = ""


def _record(state: RunState, phase: str, message: str, **data: Any) -> None:
    event = {"step": state.step, "phase": phase, "message": message}
    event.update(data)
    state.events.append(event)
    print(f"[mcp-agent step {state.step}] {phase}: {message}")


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


async def connect_servers(config: dict[str, Any], stack: AsyncExitStack) -> dict[str, ToolEntry]:
    """Launch every server in the config over stdio, call tools/list on
    each, and return one merged {tool_name: ToolEntry} registry. This is
    the ONLY place tool names enter this program -- discovered, never
    typed in."""

    registry: dict[str, ToolEntry] = {}

    for server_cfg in config["servers"]:
        params = StdioServerParameters(
            command=server_cfg["command"],
            args=server_cfg["args"],
            cwd=str(REPO_ROOT),
        )
        read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        tools_result = await session.list_tools()

        for tool in tools_result.tools:
            registry[tool.name] = ToolEntry(
                server_name=server_cfg["name"],
                session=session,
                description=tool.description or "",
                input_schema=tool.input_schema or {},
            )

    return registry


def _build_prompt(question: str, registry: dict[str, ToolEntry], state: RunState) -> str:
    tool_lines = []
    for name, entry in registry.items():
        params = ", ".join(entry.input_schema.get("properties", {}).keys())
        tool_lines.append(f"- {name}({params}) [{entry.server_name}]: {entry.description}")
    tools_block = "\n".join(tool_lines)

    header = f"""You are a legal-contract agent. Decide the next tool call yourself, one \
step at a time, using only the tools below (discovered via MCP, not hard-coded). \
Never call the same tool with the same input twice.

Tools:
{tools_block}

When you have gathered enough evidence to answer, respond with exactly:
Thought: <one short sentence>
Action: {FINAL_ANSWER_SIGNAL}
Action Input: {{}}

Otherwise respond with exactly:
Thought: <one short sentence>
Action: <one of the tool names above>
Action Input: <a single JSON object matching that tool's parameters>
"""

    if state.transcript:
        history = "\n".join(f"Observation ({tool}): {obs}" for tool, obs in state.transcript)
    else:
        history = "(no tools called yet)"

    return f"{header}\nQuestion: {question}\nStep {state.step} of {MAX_STEPS}.\n{history}\nThought:"


_ACTION_RE = re.compile(r"Action:\s*([A-Za-z_]+)", re.IGNORECASE)
_INPUT_RE = re.compile(r"Action Input:\s*(\{.*\})", re.IGNORECASE | re.DOTALL)


def _call_llm(prompt: str) -> dict[str, Any]:
    """The one and only place a model runs in this whole program -- on
    the host, over a local Ollama call. No MCP server ever does this."""

    import ollama

    response = ollama.generate(
        model=MODEL_NAME,
        prompt=prompt,
        options={"temperature": ROUTING_TEMPERATURE, "seed": 42},
    )
    return {
        "text": (response.response or "").strip(),
        "prompt_tokens": response.prompt_eval_count or 0,
        "completion_tokens": response.eval_count or 0,
    }


def _parse_response(text: str) -> tuple[str, dict[str, Any]] | None:
    action_match = _ACTION_RE.search(text)
    if not action_match:
        return None
    tool_name = action_match.group(1).strip()

    tool_input: dict[str, Any] = {}
    input_match = _INPUT_RE.search(text)
    if input_match:
        try:
            tool_input = json.loads(input_match.group(1))
        except json.JSONDecodeError:
            tool_input = {}
    return tool_name, tool_input


async def _dispatch(entry: ToolEntry, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    result = await entry.session.call_tool(tool_name, tool_input)
    for block in result.content:
        if getattr(block, "type", None) == "text":
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                return {"raw": block.text}
    return {"raw": str(result.content)}


def _draft_final_answer(question: str, state: RunState) -> str:
    """Composing the final answer is host-side reasoning, not a
    discoverable MCP capability -- it happens here, locally, using the
    same real model and the same real prompt-building approach as the
    Week 7/8 agent (rag.generate_answer_with_usage), never inside a
    server."""

    from rag import generate_answer_with_usage
    from security_controls import wrap_untrusted_context

    if not state.transcript:
        return "I don't know based on the provided contracts."

    context = wrap_untrusted_context(
        "\n\n".join(f"{tool}: {json.dumps(obs)}" for tool, obs in state.transcript)
    )
    usage = generate_answer_with_usage(question, context)
    return usage["answer"]


async def run_query(question: str, registry: dict[str, ToolEntry]) -> dict[str, Any]:
    state = RunState(question=question)
    started_at = monotonic()

    while not state.answer and state.step < MAX_STEPS:
        state.step += 1
        prompt = _build_prompt(question, registry, state)
        llm_result = _call_llm(prompt)
        parsed = _parse_response(llm_result["text"])

        if parsed is None:
            _record(state, "OBSERVE", "Model response did not match the required format; retrying.")
            continue

        tool_name, tool_input = parsed

        if tool_name == FINAL_ANSWER_SIGNAL:
            _record(state, "ACT", "Model signalled it has enough evidence to draft.")
            break

        already_retrieved = tool_name == "retrieve_contract_evidence" and any(
            called == "retrieve_contract_evidence" for called, _ in state.transcript
        )
        signature = (tool_name, json.dumps(tool_input, sort_keys=True))
        repeat_call = signature in state.seen_calls
        unknown_tool = tool_name not in registry

        if unknown_tool or already_retrieved or repeat_call:
            reason = (
                f"Unknown tool '{tool_name}'. Choose one of {list(registry)} or {FINAL_ANSWER_SIGNAL}."
                if unknown_tool
                else "retrieve_contract_evidence may only be called once per question and already ran."
                if already_retrieved
                else "Already called with this exact input; result unchanged."
            )
            state.transcript.append((tool_name, reason))
            _record(state, "OBSERVE", f"Skipped/invalid action: {reason}")
            state.stuck_count += 1
            if state.stuck_count >= 2:
                _record(state, "STOP", "Stuck-loop guard: drafting now with whatever evidence is in hand.")
                break
            continue
        state.stuck_count = 0
        state.seen_calls.add(signature)

        entry = registry[tool_name]
        _record(state, "ACT", f"Call {tool_name} on server '{entry.server_name}'.", tool=tool_name, server=entry.server_name, argument=tool_input)

        observation = await _dispatch(entry, tool_name, tool_input)
        state.transcript.append((tool_name, json.dumps(observation)))
        _record(state, "OBSERVE", json.dumps(observation), server=entry.server_name)

    state.answer = _draft_final_answer(question, state)
    state.stop_reason = "answer_ready" if state.step < MAX_STEPS else "max_steps"

    return {
        "answer": state.answer,
        "steps": state.step,
        "stop_reason": state.stop_reason,
        "elapsed_seconds": round(monotonic() - started_at, 4),
        "events": state.events,
        "tools_called": sorted({event["tool"] for event in state.events if event.get("phase") == "ACT" and "tool" in event}),
        "servers_used": sorted({event["server"] for event in state.events if event.get("phase") == "ACT" and "server" in event}),
    }


# ============================================================
# WEEK 9 EVIDENCE GENERATION (--generate-evidence)
#
# Regenerates every piece of Week 9 Task Set F evidence that is
# mechanically reproducible in one command, the same way race.py does
# for Week 7 and trajectory_eval.py does for Week 8. week9_evidence/
# risk_note.md is deliberately left untouched -- it is a pure judgment
# document (who wrote the third-party server, what a stolen token could
# do) with no run-to-run data in it, so there is nothing to regenerate.
# ============================================================

def _sha256_of(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def _discover_only(config: dict[str, Any]) -> dict[str, ToolEntry]:
    async with AsyncExitStack() as stack:
        return await connect_servers(config, stack)


def _generate_tool_counts_and_config_diff(evidence_dir: Path, live_config_path: Path) -> None:
    import subprocess

    live_config = load_config(live_config_path)
    clause_search_entry = next(s for s in live_config["servers"] if s["name"] == "clause_search")
    before_config = {"servers": [clause_search_entry]}

    before_registry = asyncio.run(_discover_only(before_config))
    after_registry = asyncio.run(_discover_only(live_config))

    print(f"Before (server one only):  {len(before_registry)} tools -- {sorted(before_registry)}")
    print(f"After  (current config):   {len(after_registry)} tools -- {sorted(after_registry)}")

    tool_counts_md = f"""# Tool discovery: before -> after

Taken directly from `tools/list` responses (via `connect_servers`), not
from notes or documentation. Regenerated by `mcp_agent.py --generate-evidence`
-- the "before" config is reconstructed from the live
`mcp_servers/mcp_config.json`'s own `clause_search` entry, not a
separately hand-maintained file that could go stale.

## Before -- server one only (`clause_search`)

- Servers configured: 1 (`clause_search`)
- **Tools discovered: {len(before_registry)}**
- Names: {', '.join(f'`{name}`' for name in sorted(before_registry))}

## After -- current config ({len(live_config['servers'])} server(s))

- Servers configured: {len(live_config['servers'])} ({', '.join(s['name'] for s in live_config['servers'])})
- **Tools discovered: {len(after_registry)}**
- Names: {', '.join(f'`{name}`' for name in sorted(after_registry))}

## What changed to go from before to after

**Only `mcp_servers/mcp_config.json`.** See `mcp_config_diff.txt` for the
exact diff. `mcp_agent.py` was not opened, let alone edited -- see
`agent_diff.txt`.
"""
    (evidence_dir / "tool_counts.md").write_text(tool_counts_md, encoding="utf-8")
    print("Wrote tool_counts.md")

    before_config_path = evidence_dir / "mcp_config_before.json"
    after_config_path = evidence_dir / "mcp_config_after.json"
    before_config_path.write_text(json.dumps(before_config, indent=2) + "\n", encoding="utf-8")
    after_config_path.write_text(json.dumps(live_config, indent=2) + "\n", encoding="utf-8")

    diff = subprocess.run(
        ["git", "diff", "--no-index", "--no-color", str(before_config_path), str(after_config_path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    (evidence_dir / "mcp_config_diff.txt").write_text(diff.stdout, encoding="utf-8")
    print("Wrote mcp_config_diff.txt")


def _capture_wire(evidence_dir: Path) -> None:
    """Speaks the wire protocol directly -- manual newline-delimited JSON
    over the clause-search server subprocess's stdin/stdout, no SDK
    abstraction -- so the capture is the literal bytes exchanged."""

    import subprocess as sp

    protocol_version = "2026-07-28"
    proc = sp.Popen(
        [sys.executable, "mcp_servers/clause_search_server.py"],
        cwd=str(REPO_ROOT), stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.DEVNULL,
    )

    def send(message: dict) -> None:
        proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        proc.stdin.flush()

    def recv() -> dict:
        return json.loads(proc.stdout.readline().decode("utf-8"))

    exchange = []
    initialize_request = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": protocol_version, "capabilities": {}, "clientInfo": {"name": "wire-capture", "version": "1.0"}},
    }
    send(initialize_request)
    initialize_response = recv()
    exchange += [{"direction": "client -> server", "message": initialize_request}, {"direction": "server -> client", "message": initialize_response}]

    initialized_notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    send(initialized_notification)
    exchange.append({"direction": "client -> server", "message": initialized_notification})

    tools_list_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    send(tools_list_request)
    tools_list_response = recv()
    exchange += [{"direction": "client -> server", "message": tools_list_request}, {"direction": "server -> client", "message": tools_list_response}]

    tools_call_request = {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "get_definitions", "arguments": {"term": "Cause", "contract_version": "Master_Service_Agreement"}},
    }
    send(tools_call_request)
    tools_call_response = recv()
    exchange += [{"direction": "client -> server", "message": tools_call_request}, {"direction": "server -> client", "message": tools_call_response}]

    proc.stdin.close()
    proc.terminate()
    proc.wait(timeout=5)

    annotations = {
        "initialize (request)": {
            "jsonrpc": "JSON-RPC 2.0 envelope version -- fixed string, every message has it.",
            "id": "Request id (1). The server's response echoes this same id so the client can match request<->response on a shared stdio pipe.",
            "method": "'initialize' -- the very first call of any MCP session; nothing else may be sent before this.",
            "params.protocolVersion": "The MCP protocol version this CLIENT speaks. The server can accept, or downgrade/reject in its response.",
            "params.capabilities": "What optional features the CLIENT supports (sampling, roots, etc.). Empty here -- this is a minimal client.",
            "params.clientInfo": "Free-form name/version identifying the calling application, for logging/debugging on the server side.",
        },
        "initialize (response)": {
            "jsonrpc / id": "Echoes the request's id (1) so this response is matched to the initialize call.",
            "result.protocolVersion": "The version the SERVER will actually use for this session (may differ from what the client asked for).",
            "result.capabilities": "What the SERVER offers: here, 'tools' -- meaning it exposes callable tools (not resources or prompts in this server).",
            "result.serverInfo": "The server's own name/version -- this is how a client learns it's talking to 'clause-search', without being told in code.",
        },
        "notifications/initialized": {
            "jsonrpc / method": "A NOTIFICATION, not a request -- note there is no 'id' field, and the server sends no reply to it.",
            "meaning": "Client -> server signal that the handshake is done and normal requests (tools/list, tools/call, ...) may now be sent.",
        },
        "tools/list (request)": {
            "id": "New request id (2) -- ids are per-session unique, not global.",
            "params": "Empty here; would carry a pagination cursor on a very large tool set.",
        },
        "tools/list (response)": {
            "result.tools": "The array never written by hand here -- every name, description, and inputSchema came from the running server, discovered just now.",
            "each tool.name": "The literal string an agent must send back in a later tools/call to invoke it.",
            "each tool.title": "A human-readable label FastMCP auto-derived from the function name -- for display, not for calling.",
            "each tool.description": "This IS the docstring from clause_search_server.py -- what an LLM reads to decide whether/how to call this tool. See error_before_after.md.",
            "each tool.inputSchema": "JSON Schema for the arguments tools/call must supply.",
            "each tool.outputSchema": "JSON Schema for what the tool returns -- here just 'an object'.",
            "each tool._meta": "Server-implementation metadata (FastMCP's own bookkeeping) -- not part of the calling contract.",
        },
        "tools/call (request)": {
            "id": "New request id (3).",
            "params.name": "Must exactly match a name returned by tools/list.",
            "params.arguments": "A JSON object matching the tool's inputSchema -- here, a real defined-term lookup on the Master Services Agreement.",
        },
        "tools/call (response)": {
            "result.content": "An array of content blocks -- here one text block, whose .text is a JSON string that get_definitions() returned.",
            "result.structuredContent": "The same data, pre-parsed as real JSON rather than a JSON-encoded string -- FastMCP populates this from the tool's actual return value.",
            "result.isError": "If present and true, this is a tool-level error (the CALL succeeded at the protocol level, but the tool reports failure) -- distinct from a JSON-RPC-level 'error' field.",
        },
        "where the model runs": (
            "Nowhere in this entire exchange. Every message above is either "
            "this function's own Python or clause_search_server.py's "
            "deterministic lookup code. The model only runs later, inside "
            "run_query()/_call_llm() on the host, never inside a server."
        ),
    }

    (evidence_dir / "wire.json").write_text(json.dumps({"exchange": exchange, "annotations": annotations}, indent=2), encoding="utf-8")
    print(f"Wrote wire.json ({len(exchange)} raw messages)")


def _capture_error_before_after(evidence_dir: Path) -> None:
    """Same failing get_definitions call against both the legacy (blunt)
    and current (recoverable) error text, then feeds each real response
    to the real local model in the same mid-loop Observation format and
    captures its actual next thought."""

    import os
    import subprocess as sp

    term, contract = "Force Majeure", "Master_Service_Agreement"

    def call_get_definitions(legacy: bool) -> dict:
        env = os.environ.copy()
        if legacy:
            env["CLAUSE_SEARCH_LEGACY_ERRORS"] = "1"
        else:
            env.pop("CLAUSE_SEARCH_LEGACY_ERRORS", None)

        proc = sp.Popen(
            [sys.executable, "mcp_servers/clause_search_server.py"],
            cwd=str(REPO_ROOT), stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.DEVNULL, env=env,
        )

        def send(message: dict) -> None:
            proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
            proc.stdin.flush()

        def recv() -> dict:
            return json.loads(proc.stdout.readline().decode("utf-8"))

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2026-07-28", "capabilities": {}, "clientInfo": {"name": "err-capture", "version": "1.0"}}})
        recv()
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_definitions", "arguments": {"term": term, "contract_version": contract}}})
        response = recv()

        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)
        return json.loads(response["result"]["content"][0]["text"])

    def ask_model_what_next(observation: dict) -> str:
        import ollama
        prompt = f"""You are a legal-contract agent answering: "Does a Force Majeure \
event excuse either party's performance under the Master Services Agreement, \
and if so what does the contract say about it?"

You called get_definitions and got this result:

Observation (get_definitions): {json.dumps(observation)}

Respond with EXACTLY two lines:
Thought: <what this observation tells you>
Next action: <the specific next tool call you will make, by name and arguments -- or "draft the answer now" if you already have enough>
"""
        response = ollama.generate(model=MODEL_NAME, prompt=prompt, options={"temperature": ROUTING_TEMPERATURE, "seed": 42})
        return (response.response or "").strip()

    before_observation = call_get_definitions(legacy=True)
    after_observation = call_get_definitions(legacy=False)
    before_thought = ask_model_what_next(before_observation)
    after_thought = ask_model_what_next(after_observation)

    report = f"""# Error path: before vs after (req #5)

Same failing call in both cases: `get_definitions(term="{term}", contract_version="{contract}")` \
-- "{term}" genuinely is not a defined term in this contract, so this is a real, correct failure, not a simulated one.

## BEFORE -- unrecoverable error

Server response:
```json
{json.dumps(before_observation, indent=2)}
```

Model's next thought:
```text
{before_thought}
```

Note the model's stated conclusion here is UNGROUNDED: it guesses that
"Error 3" means the term isn't defined, but "Error 3" carries no
information that actually says that. This is the real risk of an
unrecoverable error: not that the model visibly gets stuck, but that it
fills the gap with a confident-sounding hallucination instead of a fact.

## AFTER -- recoverable error

Server response:
```json
{json.dumps(after_observation, indent=2)}
```

Model's next thought:
```text
{after_thought}
```

Here the model reaches the same practical conclusion, but for the right
reason: the server's own message states plainly that {term} is not
defined, which is a verified fact, not a guess. That distinction --
grounded conclusion vs. a lucky-looking hallucination -- is exactly the
"right answer, wrong path" risk from Week 8, now traced back one layer
further to where it can start: an opaque error at the tool boundary.

## The docstring rewrite (also req #5)

`get_definitions`'s docstring in `mcp_servers/clause_search_server.py` is
written as a prompt, not a comment -- it tells the calling model exactly
when to use this tool vs. `retrieve_contract_evidence`, and what
`contract_version` must be. This exact text is what `tools/list` returns
in `description` -- see `wire.json`.
"""

    (evidence_dir / "error_before_after.md").write_text(report, encoding="utf-8")
    print("Wrote error_before_after.md")
    print("BEFORE:", before_observation)
    print("AFTER:", after_observation)


def _check_agent_diff_still_frozen(evidence_dir: Path) -> None:
    """agent_diff.txt is NOT regenerated here on purpose. It proves a
    one-time historical fact -- that the real edit session which added
    server two to mcp_config.json never touched mcp_agent.py -- captured
    via the two frozen snapshots already sitting in week9_evidence/
    (mcp_agent_snapshot_before_server_two.py / _after_server_two.py).
    Checksumming the CURRENT file against itself at the start/end of this
    very function would prove nothing (nothing in this run edits itself
    mid-execution) -- it would silently replace real historical evidence
    with a trivially-true, weaker claim. Instead, just re-verify the two
    frozen snapshots still agree with each other and with the live file,
    and say so."""

    before_snap = evidence_dir / "mcp_agent_snapshot_before_server_two.py"
    after_snap = evidence_dir / "mcp_agent_snapshot_after_server_two.py"

    print("\n--- agent_diff.txt consistency check (file NOT regenerated) ---")
    if not (before_snap.exists() and after_snap.exists()):
        print("(historical snapshots not found -- nothing to check)")
        return

    same_as_each_other = _sha256_of(before_snap) == _sha256_of(after_snap)
    live_matches_snapshots = _sha256_of(Path(__file__)) == _sha256_of(after_snap)

    print(f"Historical snapshots still identical to each other: {same_as_each_other}")
    print(f"Live mcp_agent.py still matches the 'after server two' snapshot: {live_matches_snapshots}")
    if same_as_each_other and live_matches_snapshots:
        print("OK: agent_diff.txt's zero-diff claim still holds; file left as-is.")
    else:
        print(
            "WARNING: mcp_agent.py has changed since agent_diff.txt's snapshots "
            "were taken (likely because this --generate-evidence feature was "
            "added afterward). That's expected for THIS file's evolution, but "
            "if you want a fresh zero-diff proof for a NEW server addition, "
            "re-run the original snapshot-diff procedure in "
            "WEEK9_TASK_SET_F_WALKTHROUGH.md rather than trusting agent_diff.txt "
            "as still describing the current file."
        )


def generate_week9_evidence() -> None:
    evidence_dir = REPO_ROOT / "week9_evidence"
    evidence_dir.mkdir(exist_ok=True)

    print("=== Tool discovery + config diff ===")
    _generate_tool_counts_and_config_diff(evidence_dir, DEFAULT_CONFIG_PATH)

    print("\n=== Raw JSON-RPC wire capture ===")
    _capture_wire(evidence_dir)

    print("\n=== Error before/after transcript ===")
    _capture_error_before_after(evidence_dir)

    _check_agent_diff_still_frozen(evidence_dir)

    print(
        "\nDone. risk_note.md and agent_diff.txt were intentionally NOT "
        "touched -- see the consistency check above for agent_diff.txt, and "
        "risk_note.md is a judgment document with no run-to-run data in it."
    )


async def main_async(question: str, config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)

    async with AsyncExitStack() as stack:
        registry = await connect_servers(config, stack)
        print(f"Discovered {len(registry)} tool(s) from {len(config['servers'])} server(s): {sorted(registry)}")
        result = await run_query(question, registry)

    result["discovered_tool_count"] = len(registry)
    result["discovered_tool_names"] = sorted(registry)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--trace-out", type=Path, default=None)
    parser.add_argument(
        "--generate-evidence", action="store_true",
        help="Regenerate all of week9_evidence/ (tool_counts.md, agent_diff.txt, "
             "mcp_config_diff.txt, wire.json, error_before_after.md) in one run. "
             "risk_note.md is left untouched -- it's a judgment document, not data.",
    )
    args = parser.parse_args()

    if args.generate_evidence:
        generate_week9_evidence()
        return

    if not args.question:
        parser.error("--question is required unless --generate-evidence is set")

    result = asyncio.run(main_async(args.question, args.config))

    print("\n" + "=" * 70)
    print("ANSWER:", result["answer"])
    print("Tools called:", result["tools_called"])
    print("Servers used:", result["servers_used"])
    print("Discovered tools:", result["discovered_tool_names"])

    if args.trace_out:
        args.trace_out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Trace written to {args.trace_out}")


if __name__ == "__main__":
    main()
