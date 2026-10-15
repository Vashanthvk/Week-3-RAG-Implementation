import asyncio
from pathlib import Path

import streamlit as st

from rag import answer_question
from agent_loops import run_agent
from multi_agent import run_orchestrator
from multi_agent_race import write_evidence
from mcp_agent import DEFAULT_CONFIG_PATH, load_config, main_async
# from week11 import EVIDENCE_DIR, write_evidence as write_week11_evidence


# ============================================================
# Page Configuration
# ============================================================

st.set_page_config(
    page_title="Legal Contract Assistant",
    page_icon="⚖️",
    layout="wide"
)

st.markdown("""
<style>
    .block-container { max-width: 1180px; padding-top: 2rem; }
    .eyebrow { color: #6b7280; font-size: .78rem; font-weight: 700;
               letter-spacing: .12em; text-transform: uppercase; }
    .trace-event { border-left: 3px solid #d1d5db; padding: .35rem .75rem;
                   margin: .35rem 0; background: #f8fafc; border-radius: 0 .35rem .35rem 0; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# Header
# ============================================================

st.title(
    "⚖️ Legal Contract Assistant"
)

st.write("Select a course week to view and run that week’s deliverable independently.")

mode = st.sidebar.radio(
    "Course week",
    [
        "Week 4 · Hybrid RAG assistant",
        "Week 5 · Evaluation and traces",
        "Week 6 · Controlled benchmark",
        "Week 7 · Agent loop",
        "Week 8 · Trajectory evaluation",
        "Week 9 · MCP agent",
        "Week 10 · Multi-agent and A2A",
        # "Week 11 · Production observability",
    ],
    help="Each documented week has its own independent UI section.",
)
st.sidebar.caption("Weeks 1–3 are not represented by project docs or runnable deliverables.")


def render_trace(events):
    """Render the host-side MCP trace without hiding tool failures."""
    if not events:
        st.info("No trace events were returned.")
        return
    for event in events:
        details = event.get("message", "")
        if event.get("tool"):
            details += f" · {event['tool']}"
        if event.get("server"):
            details += f" · {event['server']}"
        with st.container(border=True):
            st.caption(f"{event.get('phase', 'EVENT')} · step {event.get('step', '?')}")
            st.write(details)


def render_report(title, description, report_path, extra_paths=()):
    st.markdown(f"<div class='eyebrow'>{title.split('·')[0].strip()}</div>", unsafe_allow_html=True)
    st.header(title)
    st.write(description)
    report = Path(__file__).parent / report_path
    if report.exists():
        if report.suffix.lower() == ".json":
            st.json(report.read_text(encoding="utf-8"))
        else:
            st.markdown(report.read_text(encoding="utf-8"))
    else:
        st.info(f"Evidence file not found yet: {report_path}")
    for label, relative_path in extra_paths:
        path = Path(__file__).parent / relative_path
        with st.expander(label, expanded=False):
            if path.exists():
                if path.suffix.lower() == ".json":
                    st.json(path.read_text(encoding="utf-8"))
                else:
                    st.markdown(path.read_text(encoding="utf-8"))
            else:
                st.info(f"Not generated yet: {relative_path}")


if mode == "Week 5 · Evaluation and traces":
    render_report("Week 5 · Evaluation and traces", "Review the evaluation report and trace artifacts from the original RAG workflow.", "WEEK_5_REPORT.md", [("Trace log", "traces/traces.jsonl")])
    st.stop()

if mode == "Week 6 · Controlled benchmark":
    render_report("Week 6 · Controlled benchmark", "Review the controlled 20-case benchmark and its evaluation output.", "EVAL_REPORT.md", [("Benchmark output", "evaluation_results/week6_benchmark.json")])
    st.stop()

if mode == "Week 8 · Trajectory evaluation":
    render_report("Week 8 · Trajectory evaluation", "Inspect the outcome-versus-trajectory gap, mitigation, and regression evidence.", "week8_evidence/trajectory_eval_after_mitigation.md", [("Baseline report", "week8_evidence/trajectory_eval_baseline.md"), ("Mitigation diff", "week8_evidence/mitigation_diff.md"), ("Regression check", "week8_evidence/regression_check.md")])
    st.stop()


def render_mcp_mode():
    config = load_config(DEFAULT_CONFIG_PATH)
    servers = config.get("servers", [])
    st.markdown("<div class='eyebrow'>Week 9 · Module 5</div>", unsafe_allow_html=True)
    st.header("MCP contract assistant")
    st.write("The host discovers tools from the configured MCP servers, calls them over stdio, and drafts the answer locally.")

    with st.expander("Connected servers and configured capabilities", expanded=True):
        cols = st.columns(max(1, len(servers)))
        known_tools = {
            "clause_search": ["retrieve_contract_evidence", "get_definitions"],
            "contract_repository": ["lookup_contract", "get_effective_date", "get_amendment_chain"],
        }
        for column, server in zip(cols, servers):
            with column:
                st.subheader(server.get("name", "server"))
                st.caption(f"{server.get('command', '')} {' '.join(server.get('args', []))}")
                for tool in known_tools.get(server.get("name"), []):
                    st.code(tool, language=None)
        st.caption("The MCP agent discovers the live tool inventory through tools/list when you submit a question.")

    question = st.text_input(
        "Ask the MCP agent about a contract",
        placeholder="What is the effective date of contract MSA-2021-0142?",
        key="mcp_question",
    )
    if st.button("Ask MCP agent", type="primary", key="ask_mcp"):
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            try:
                with st.spinner("Discovering tools and querying MCP servers..."):
                    st.session_state["mcp_result"] = asyncio.run(main_async(question.strip(), DEFAULT_CONFIG_PATH))
            except Exception as error:
                st.error("The MCP workflow could not complete.")
                st.caption(f"Error: {error}")

    result = st.session_state.get("mcp_result")
    if result:
        st.subheader("Answer")
        st.write(result.get("answer", "No answer returned."))
        metrics = st.columns(4)
        metrics[0].metric("Tools discovered", result.get("discovered_tool_count", 0))
        metrics[1].metric("Steps", result.get("steps", 0))
        metrics[2].metric("Elapsed", f"{result.get('elapsed_seconds', 0):.2f}s")
        metrics[3].metric("Stop reason", result.get("stop_reason", "—"))
        st.caption("Tools called: " + (", ".join(result.get("tools_called", [])) or "none") + " · Servers used: " + (", ".join(result.get("servers_used", [])) or "none"))
        with st.expander("Discovered tools", expanded=False):
            st.write(", ".join(result.get("discovered_tool_names", [])) or "None")
        with st.expander("ACT / OBSERVE trace", expanded=True):
            render_trace(result.get("events", []))


if mode == "Week 9 · MCP agent":
    render_mcp_mode()
    st.stop()

if mode == "Week 10 · Multi-agent and A2A":
    st.markdown("<div class='eyebrow'>Week 10 · Module 5</div>", unsafe_allow_html=True)
    st.header("Week 10 · Multi-agent and A2A")
    st.caption("Runs the same 10-case benchmark and writes race_evidence/.")
    week10_view = st.radio("Week 10 view", ["Contract squad", "Race evidence"], horizontal=True)
    if week10_view == "Contract squad":
        question = st.text_input("Ask the contract squad", key="week10_question")
        if st.button("Ask contract squad", type="primary", key="week10_ask"):
            if not question.strip():
                st.warning("Please enter a question.")
                st.stop()
            with st.spinner("Delegating to the contract squad..."):
                st.session_state["week10_squad_result"] = run_orchestrator(question.strip())
        result = st.session_state.get("week10_squad_result")
        if result:
            st.subheader("Answer")
            st.write(result.get("answer", "No answer returned."))
            st.caption(f"Stop reason: {result.get('stop_reason', '—')} · Handoffs: {len(result.get('handoffs', []))}")
            with st.expander("Agent handoffs", expanded=True):
                st.json(result.get("handoffs", []))
        st.stop()
    if st.button("Run Week 10 race", type="primary"):
        with st.spinner("Running both arms on the 10 fixed cases..."):
            st.session_state["race_summary"] = write_evidence()
    summary = st.session_state.get("race_summary")
    if summary:
        st.success("Evidence generated in race_evidence/")
        st.table([
            {"Metric": "Pass rate", "Single agent": summary["single"]["pass_rate"], "Contract squad": summary["multi"]["pass_rate"]},
            {"Metric": "p50 latency (s)", "Single agent": summary["single"]["p50_latency_s"], "Contract squad": summary["multi"]["p50_latency_s"]},
            {"Metric": "p99 latency (s)", "Single agent": summary["single"]["p99_latency_s"], "Contract squad": summary["multi"]["p99_latency_s"]},
            {"Metric": "Total tokens", "Single agent": summary["single"]["total_tokens"], "Contract squad": summary["multi"]["total_tokens"]},
            {"Metric": "Cost / question", "Single agent": summary["single"]["cost_per_question"], "Contract squad": summary["multi"]["cost_per_question"]},
        ])
    st.stop()


# if mode == "Week 11 · Production observability":
#     st.markdown("<div class='eyebrow'>Week 11 · Module 6</div>", unsafe_allow_html=True)
#     st.header("Production observability and failure-to-test loop")
#     st.write("Inspect per-request spans, cost attribution, retrieved context IDs, and the termination-clause support drill.")

#     if st.button("Generate / refresh support-drill evidence", type="primary"):
#         st.session_state["week11_trace"] = write_week11_evidence()
#         st.success("Week 11 evidence generated in week11_evidence/.")

#     trace = st.session_state.get("week11_trace")
#     trace_path = EVIDENCE_DIR / "trace.json"
#     if trace is None and trace_path.exists():
#         import json
#         trace = json.loads(trace_path.read_text(encoding="utf-8"))
#     if trace:
#         metrics = st.columns(4)
#         metrics[0].metric("Trace", trace.get("trace_id", "—"))
#         metrics[1].metric("Prompt version", trace.get("prompt_version", "—"))
#         metrics[2].metric("Spans", len(trace.get("spans", [])))
#         metrics[3].metric("Cost / query", f"${sum(trace.get('cost_by_stage_usd', {}).values()):.8f}")
#         st.subheader("Trace spans")
#         st.dataframe(trace.get("spans", []), use_container_width=True, hide_index=True)
#         st.subheader("Retrieved context IDs")
#         st.code("\n".join(trace.get("retrieved_context_ids", [])), language=None)
#     for label, name in [
#         ("Support drill", "drill.md"),
#         ("Cost by stage", "cost_by_stage.md"),
#         ("10× capacity assessment", "tenx.md"),
#         ("Canary and rollback", "canary_rollback.md"),
#         ("Termination regression case", "termination_clause_eval.json"),
#         ("RED / GREEN reproduction", "red_green.md"),
#     ]:
#         path = EVIDENCE_DIR / name
#         with st.expander(label):
#             if path.exists():
#                 if path.suffix == ".json":
#                     st.json(path.read_text(encoding="utf-8"))
#                 else:
#                     st.markdown(path.read_text(encoding="utf-8"))
#             else:
#                 st.info("Generate the support-drill evidence to create this artifact.")
#     st.stop()


if mode == "Week 7 · Agent loop":
    st.markdown("<div class='eyebrow'>Week 7 · Task Set F</div>", unsafe_allow_html=True)
    st.header("Week 7 · Agent loop")
    st.write("Run the model-directed PLAN → ACT → OBSERVE contract agent with bounded budgets.")

if mode in {"Week 4 · Hybrid RAG assistant", "Week 7 · Agent loop"}:
    question = st.text_input("Enter your legal contract question:", key=f"question_{mode}")
    if st.button("Ask Question", type="primary", key=f"ask_{mode}"):
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            try:
                with st.spinner("Searching contracts and generating answer..."):
                    if mode == "Week 7 · Agent loop":
                        result = run_agent(question.strip())
                        answer, sources = result["answer"], result["sources"]
                    else:
                        answer, sources = answer_question(question.strip())
                        result = None
                st.subheader("Answer")
                st.write(answer)
                if sources:
                    st.subheader("Retrieved Context Sources")
                    for source in sources:
                        st.write(f"📄 {source['source']} — Page {source['page']}")
                else:
                    st.info("No document source was retrieved.")
                if result:
                    with st.expander("PLAN / ACT / OBSERVE trace", expanded=True):
                        render_trace(result.get("events", []))
            except Exception as error:
                st.error("Unable to process the question.")
                st.caption(f"Error: {error}")
