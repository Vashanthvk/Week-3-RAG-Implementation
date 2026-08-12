from functools import lru_cache

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama


# ============================================================
# Configuration
# ============================================================

CHROMA_PATH = "./chroma_db"

COLLECTION_NAME = "legal_contracts"

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

OLLAMA_MODEL = "llama3.2"

# Top-K retrieval
RETRIEVAL_K = 5


# ============================================================
# Create Embedding Model
# ============================================================

@lru_cache(maxsize=1)
def create_embedding_model():

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL
    )

    return embeddings


# ============================================================
# Load ChromaDB
# ============================================================

@lru_cache(maxsize=1)
def load_vector_database():

    embedding_model = create_embedding_model()

    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embedding_model,
        persist_directory=CHROMA_PATH
    )

    return vector_store


# ============================================================
# Create LLM
# ============================================================

@lru_cache(maxsize=1)
def create_llm():

    llm = ChatOllama(
        model=OLLAMA_MODEL,
        temperature=0
    )

    return llm


# ============================================================
# Search Documents
# ============================================================

def search_documents(
    vector_store,
    question
):

    results = vector_store.similarity_search(
        question,
        k=RETRIEVAL_K
    )

    return results


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
            "Unknown document"
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
# Create RAG Prompt
# ============================================================

def create_prompt(
    context,
    question
):

    prompt = f"""
You are a legal contract question-answering assistant.

Your task is to answer the user's question using ONLY
the information contained in the provided contract context.

STRICT RULES:

1. Do not use outside knowledge.
2. Do not invent facts.
3. Do not assume information that is not explicitly stated.
4. If the answer cannot be found in the provided context,
   respond exactly with:

"I don't know based on the provided contracts."

5. When the context contains information from multiple
   contracts, distinguish between the contracts.
6. For ambiguous questions, explain the relevant answer
   for each applicable contract.
7. Keep the answer concise and factual.

CONTRACT CONTEXT
================

{context}

USER QUESTION
=============

{question}

ANSWER
======
"""

    return prompt


# ============================================================
# Generate Answer
# ============================================================

def generate_answer(
    llm,
    context,
    question
):

    prompt = create_prompt(
        context,
        question
    )

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
            "Unknown document"
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

        # Normalize path separators
        source = source.replace(
            "\\",
            "/"
        )

        # Display only filename
        source_name = source.split("/")[-1]

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

def answer_question(question):

    vector_store = load_vector_database()

    llm = create_llm()

    results = search_documents(
        vector_store,
        question
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
# Display Terminal Answer
# ============================================================

def display_answer(answer):

    print("\n" + "=" * 70)

    print("FINAL ANSWER")

    print("=" * 70)

    print(answer)


# ============================================================
# Display Terminal Sources
# ============================================================

def display_sources(sources):

    print("\n" + "=" * 70)

    print("RETRIEVED CONTEXT SOURCES")

    print("=" * 70)

    for source in sources:

        print(
            f"Document: {source['source']}"
        )

        print(
            f"Page: {source['page']}"
        )

        print()


# ============================================================
# Terminal Application
# ============================================================

def main():

    question = input(
        "\nEnter your legal contract question: "
    ).strip()

    if not question:

        print(
            "Please enter a question."
        )

        return

    answer, sources = answer_question(
        question
    )

    display_answer(
        answer
    )

    display_sources(
        sources
    )


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":

    main()