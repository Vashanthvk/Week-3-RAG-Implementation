from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
import os


# ============================================================
# Configuration
# ============================================================

CHROMA_PATH = "./chroma_db"

COLLECTION_NAME = "legal_contracts"

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

TOP_K = 3


# ============================================================
# Evaluation Questions
# ============================================================

TEST_CASES = [

    {
        "question": "What is the notice period for an employee?",
        "expected_source": "Employment_Agreement.pdf"
    },

    {
        "question": "How many annual leave days does the employee receive?",
        "expected_source": "Employment_Agreement.pdf"
    },

    {
        "question": "How many sick leave days does the employee receive?",
        "expected_source": "Employment_Agreement.pdf"
    },

    {
        "question": "How long must the employee maintain confidentiality after leaving?",
        "expected_source": "Employment_Agreement.pdf"
    },

    {
        "question": "What is the monthly rent in the lease agreement?",
        "expected_source": "Lease_Agreement.pdf"
    },

    {
        "question": "What is the security deposit?",
        "expected_source": "Lease_Agreement.pdf"
    },

    {
        "question": "What is the lease termination notice period?",
        "expected_source": "Lease_Agreement.pdf"
    },

    {
        "question": "What is the employee's medical insurance coverage?",
        "expected_source": "Employment_Agreement.pdf"
    }
]


# ============================================================
# Load Embedding Model
# ============================================================

def create_embeddings():

    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL
    )


# ============================================================
# Load ChromaDB
# ============================================================

def load_vector_store():

    embeddings = create_embeddings()

    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_PATH
    )

    return vector_store


# ============================================================
# Get Filename
# ============================================================

def get_filename(source):

    if not source:
        return "Unknown"

    source = source.replace("\\", "/")

    return os.path.basename(source)


# ============================================================
# Inspect One Question
# ============================================================

def inspect_question(
    vector_store,
    question,
    expected_source
):

    print("\n")
    print("=" * 80)
    print("QUESTION")
    print("=" * 80)

    print(question)

    print("\nEXPECTED DOCUMENT")
    print("=" * 80)

    print(expected_source)

    print("\nTOP 3 RETRIEVED DOCUMENTS")
    print("=" * 80)

    results = vector_store.similarity_search_with_score(
        question,
        k=TOP_K
    )

    expected_found = False

    for rank, (document, score) in enumerate(
        results,
        start=1
    ):

        source = get_filename(
            document.metadata.get("source")
        )

        page = document.metadata.get(
            "page_label"
        )

        if page is None:

            page = (
                document.metadata.get(
                    "page",
                    0
                ) + 1
            )

        print(f"\nRank {rank}")

        print(f"Document : {source}")

        print(f"Page     : {page}")

        print(f"Distance : {score:.6f}")

        print("\nChunk:")

        print(
            document.page_content[:500]
        )

        if source.lower() == expected_source.lower():

            expected_found = True

    print("\n" + "-" * 80)

    if expected_found:

        print("RETRIEVAL RESULT: PASS")

        print(
            f"{expected_source} appeared in Top-{TOP_K}"
        )

    else:

        print("RETRIEVAL RESULT: FAIL")

        print(
            f"{expected_source} was NOT found in Top-{TOP_K}"
        )

    return expected_found


# ============================================================
# Main Evaluation
# ============================================================

def main():

    print("\n")
    print("=" * 80)
    print("WEEK 4 — RETRIEVAL INSPECTION")
    print("=" * 80)

    print(f"Vector Database : {CHROMA_PATH}")
    print(f"Embedding Model : {EMBEDDING_MODEL}")
    print(f"Top-K           : {TOP_K}")

    print("=" * 80)

    vector_store = load_vector_store()

    passed = 0
    total = len(TEST_CASES)

    failures = []

    for test in TEST_CASES:

        result = inspect_question(
            vector_store,
            test["question"],
            test["expected_source"]
        )

        if result:

            passed += 1

        else:

            failures.append(
                {
                    "question": test["question"],
                    "expected_source": test["expected_source"]
                }
            )

    hit_rate = (
        passed / total
    ) * 100

    print("\n")
    print("=" * 80)
    print("BASELINE RETRIEVAL RESULT")
    print("=" * 80)

    print(
        f"Correct documents in Top-{TOP_K}: "
        f"{passed}/{total}"
    )

    print(
        f"Hit-rate@{TOP_K}: "
        f"{hit_rate:.2f}%"
    )

    print("\n")
    print("=" * 80)
    print("RETRIEVAL FAILURES")
    print("=" * 80)

    if not failures:

        print("No retrieval failures found.")

    else:

        for index, failure in enumerate(
            failures,
            start=1
        ):

            print(f"\nFailure {index}")

            print(
                f"Question: "
                f"{failure['question']}"
            )

            print(
                f"Expected document: "
                f"{failure['expected_source']}"
            )

    print("\n" + "=" * 80)

    

if __name__ == "__main__":

    main()