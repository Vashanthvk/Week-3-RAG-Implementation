from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama


# ============================================================
# Configuration
# ============================================================

CHROMA_PATH = "./chroma_db_1000"

COLLECTION_NAME = "legal_contracts"

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

OLLAMA_MODEL = "llama3.2"

RETRIEVAL_K = 5


# ============================================================
# Test Cases
# ============================================================

TEST_CASES = [

    {
        "question":
            "What is the notice period for an employee?",

        "expected":
            "30 calendar days",

        "expected_source":
            "Employment_Agreement.pdf"
    },

    {
        "question":
            "How many annual leave days does the employee receive?",

        "expected":
            "18 paid annual leave days",

        "expected_source":
            "Employment_Agreement.pdf"
    },

    {
        "question":
            "How many sick leave days does the employee receive?",

        "expected":
            "10 sick leave days",

        "expected_source":
            "Employment_Agreement.pdf"
    },

    {
        "question":
            "How long must the employee maintain confidentiality after leaving?",

        "expected":
            "2 years",

        "expected_source":
            "Employment_Agreement.pdf"
    },

    {
        "question":
            "What is the monthly rent in the lease agreement?",

        "expected":
            "USD 1,500",

        "expected_source":
            "Lease_Agreement.pdf"
    },

    {
        "question":
            "What is the security deposit?",

        "expected":
            "USD 3,000",

        "expected_source":
            "Lease_Agreement.pdf"
    },

    {
        "question":
            "What is the lease termination notice period?",

        "expected":
            "60 days",

        "expected_source":
            "Lease_Agreement.pdf"
    },

    {
        "question":
            "What is the employee's medical insurance coverage?",

        "expected":
            "I don't know",

        "expected_source":
            None
    }
]


# ============================================================
# Create Embeddings
# ============================================================

def create_embedding_model():

    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL
    )


# ============================================================
# Load Experimental Database
# ============================================================

def load_vector_database():

    embeddings = create_embedding_model()

    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_PATH
    )


# ============================================================
# Create LLM
# ============================================================

def create_llm():

    return ChatOllama(
        model=OLLAMA_MODEL,
        temperature=0
    )


# ============================================================
# Build Context
# ============================================================

def build_context(results):

    context_parts = []

    for index, document in enumerate(
        results,
        start=1
    ):

        metadata = document.metadata

        source = metadata.get(
            "source",
            "Unknown"
        )

        page = metadata.get(
            "page_label"
        )

        if page is None:

            page = (
                metadata.get(
                    "page",
                    0
                ) + 1
            )

        context_parts.append(
            f"""
SOURCE {index}
Document: {source}
Page: {page}

Content:
{document.page_content}
"""
        )

    return "\n\n".join(
        context_parts
    )


# ============================================================
# Generate Answer
# ============================================================

def generate_answer(
    llm,
    context,
    question
):

    prompt = f"""
You are a legal contract question-answering assistant.

Answer the user's question using ONLY the provided
contract context.

Rules:

1. Do not use outside knowledge.
2. Do not invent information.
3. If the answer is not present in the context, respond:

"I don't know based on the provided contracts."

4. If multiple contracts contain relevant information,
distinguish between them.

CONTRACT CONTEXT:
{context}

QUESTION:
{question}

ANSWER:
"""

    response = llm.invoke(
        prompt
    )

    return response.content.strip()


# ============================================================
# Format Sources
# ============================================================

def format_sources(results):

    sources = []

    displayed = set()

    for document in results:

        metadata = document.metadata

        source = metadata.get(
            "source",
            "Unknown"
        )

        source = source.replace(
            "\\",
            "/"
        )

        source_name = source.split("/")[-1]

        page = metadata.get(
            "page_label"
        )

        if page is None:

            page = (
                metadata.get(
                    "page",
                    0
                ) + 1
            )

        key = (
            source_name,
            str(page)
        )

        if key in displayed:

            continue

        displayed.add(key)

        sources.append(
            {
                "source": source_name,
                "page": page
            }
        )

    return sources


# ============================================================
# Answer Question
# ============================================================

def answer_question(
    vector_store,
    llm,
    question
):

    results = vector_store.similarity_search(
        question,
        k=RETRIEVAL_K
    )

    context = build_context(
        results
    )

    answer = generate_answer(
        llm,
        context,
        question
    )

    sources = format_sources(
        results
    )

    return answer, sources


# ============================================================
# Evaluation
# ============================================================

def run_evaluation():

    vector_store = load_vector_database()

    llm = create_llm()

    passed = 0

    total = len(
        TEST_CASES
    )

    print("\n" + "=" * 70)

    print(
        "CHUNK SIZE EXPERIMENT"
    )

    print("=" * 70)

    print(
        "Chunk Size   : 1000"
    )

    print(
        "Chunk Overlap: 200"
    )

    print(
        "Top-K        : 5"
    )

    print("=" * 70)

    for index, test in enumerate(
        TEST_CASES,
        start=1
    ):

        question = test["question"]

        expected = test["expected"]

        expected_source = test[
            "expected_source"
        ]

        print(
            f"\nTEST {index}"
        )

        print(
            "-" * 70
        )

        print(
            f"Question: {question}"
        )

        answer, sources = answer_question(
            vector_store,
            llm,
            question
        )

        answer_correct = (
            expected.lower()
            in answer.lower()
        )

        source_correct = True

        if expected_source:

            source_correct = any(
                expected_source.lower()
                in source["source"].lower()
                for source in sources
            )

        if (
            answer_correct
            and source_correct
        ):

            print(
                "Result: PASS"
            )

            passed += 1

        else:

            print(
                "Result: FAIL"
            )

        print(
            f"Expected: {expected}"
        )

        print(
            f"Actual: {answer}"
        )

        print(
            "Sources:"
        )

        for source in sources:

            print(
                f"  - {source['source']} "
                f"(Page {source['page']})"
            )

    accuracy = (
        passed / total
    ) * 100

    print("\n" + "=" * 70)

    print(
        "EXPERIMENT SUMMARY"
    )

    print("=" * 70)

    print(
        f"Passed: {passed}/{total}"
    )

    print(
        f"Accuracy: {accuracy:.2f}%"
    )

    print("=" * 70)


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":

    run_evaluation()