venv\Scripts\activate
Python eval.py
Python eval.py --benchmark
Python agent_loop_eval.py
streamlit run app.py

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