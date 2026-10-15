venv\Scripts\activate
Python eval.py
Python eval.py --benchmark
Python agent_loop_eval.py
streamlit run app.py

Week 10 Task Set F:

- `venv\Scripts\activate`
- Start Ollama and ensure the configured model is available (`ollama serve`, then `ollama pull llama3.2` if needed).
- `python multi_agent_race.py` runs the same 10 cases from `race_questions.json` through the single agent and contract squad, then writes `race_evidence/race_table.md`, `handoffs.log`, `multiplier.md`, `failure_case.md`, `verdict.md`, `agent_card.json`, and `a2a_failure_mapping.md`.
- `streamlit run app.py` opens the UI. Existing assistant is the default; select `Contract squad` for a single question or `Week 10 race` for the evidence dashboard.
- `python -m unittest discover -s tests -p "test*.py"` runs regression tests.
- `python -m unittest discover -s tests -p "test_multi_agent.py"` runs the multi-agent tests.

Week 7 agent-loop deliverable:

- `agent_loops.py` implements a visible PLAN -> ACT -> OBSERVE loop.
- `agent_loop_eval.py` compares the agent against the fixed retrieval -> answer workflow.
- Both workflows use `evaluation_questions.json`.
- The agent is bounded by step, time, and estimated-cost budgets.
- The fixed workflow is the recommended production path for this known contract-QA task.


report :

Metric	Baseline	Hybrid
Retrieval method	Semantic	Semantic + BM25 + RRF
Top-K	3	3
Correct documents	6/8	8/8
Hit-rate@3	75%	100%
Improvement	—	+25 percentage points



week 4 final architecture

                    LEGAL CONTRACT RAG
                           │
                           ▼
                    Contract PDFs
                           │
                           ▼
                    Document Chunking
                      500 / 100
                           │
                           ▼
                  HuggingFace Embeddings
                           │
                           ▼
                       ChromaDB
                           │
                           │
                    USER QUESTION
                           │
                           ▼
                 ┌────────────────────┐
                 │ Hybrid Retrieval   │
                 └─────────┬──────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       Semantic Search                BM25
              │                         │
              └────────────┬────────────┘
                           ▼
                    RRF Fusion
                           │
                           ▼
                  Retrieval Quality
                      Check
                    /         \
                  Good        Weak
                   │            │
                   │          Retry
                   │            │
                   │     Broader Retrieval
                   │            │
                   │       Reranking
                   │            │
                   └─────┬──────┘
                         ▼
                  Relevant Chunks
                         │
                         ▼
                  Context Building
                         │
                         ▼
                    Llama 3.2
                         │
                         ▼
                   Final Answer
                         │
                         ▼
                      Sources



week 8 :

ollama serve - to run ollama
