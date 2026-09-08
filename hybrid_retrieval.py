from rank_bm25 import BM25Okapi

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings


# ============================================================
# CONFIGURATION
# ============================================================

CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "legal_contracts"

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

FINAL_TOP_K = 5
NORMAL_CANDIDATE_K = 5
RETRY_CANDIDATE_K = 10

RRF_K = 60
MAX_RETRIES = 1


# ============================================================
# EMBEDDINGS
# ============================================================

def create_embeddings():

    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL
    )


# ============================================================
# LOAD VECTOR STORE
# ============================================================

def load_vector_store():

    embeddings = create_embeddings()

    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_PATH
    )


# ============================================================
# LOAD ALL DOCUMENTS
# ============================================================

def load_all_documents(vector_store):

    data = vector_store.get(
        include=[
            "documents",
            "metadatas"
        ]
    )

    documents = []

    contents = data.get(
        "documents",
        []
    )

    metadatas = data.get(
        "metadatas",
        []
    )

    for index, content in enumerate(contents):

        metadata = {}

        if index < len(metadatas):
            metadata = metadatas[index] or {}

        documents.append(
            {
                "content": content,
                "metadata": metadata
            }
        )

    return documents


# ============================================================
# TOKENIZATION
# ============================================================

def tokenize(text):

    return text.lower().split()


# ============================================================
# BM25 INDEX
# ============================================================

def create_bm25(documents):

    tokenized_documents = [
        tokenize(document["content"])
        for document in documents
    ]

    return BM25Okapi(
        tokenized_documents
    )


# ============================================================
# SOURCE HELPERS
# ============================================================

def get_filename(source):

    if not source:
        return "Unknown"

    source = str(source).replace(
        "\\",
        "/"
    )

    return source.split("/")[-1]


def get_page(metadata):

    if not metadata:
        return 1

    page_label = metadata.get(
        "page_label"
    )

    if page_label is not None:
        return page_label

    page = metadata.get(
        "page"
    )

    if page is None:
        return 1

    try:
        return int(page) + 1
    except (TypeError, ValueError):
        return page


# ============================================================
# SEMANTIC SEARCH
# ============================================================

def semantic_retrieve(
    vector_store,
    documents,
    question,
    k
):

    print(
        f"  Semantic search -> Top {k}"
    )

    results = vector_store.similarity_search_with_score(
        question,
        k=k
    )

    retrieved = []

    for document, distance in results:

        content = document.page_content

        matching_index = None

        for index, stored_document in enumerate(
            documents
        ):

            if stored_document["content"] == content:

                matching_index = index
                break

        if matching_index is not None:

            retrieved.append(
                {
                    "index": matching_index,
                    "distance": float(distance),
                    "document": documents[
                        matching_index
                    ]
                }
            )

    return retrieved


# ============================================================
# BM25 SEARCH
# ============================================================

def bm25_retrieve(
    bm25,
    documents,
    question,
    k
):

    print(
        f"  BM25 search -> Top {k}"
    )

    query_tokens = tokenize(
        question
    )

    scores = bm25.get_scores(
        query_tokens
    )

    ranked_indexes = sorted(
        range(len(scores)),
        key=lambda index: scores[index],
        reverse=True
    )

    retrieved = []

    for index in ranked_indexes[:k]:

        retrieved.append(
            {
                "index": index,
                "score": float(
                    scores[index]
                ),
                "document": documents[index]
            }
        )

    return retrieved


# ============================================================
# RRF FUSION
# ============================================================

def rrf_fusion(
    semantic_results,
    bm25_results
):

    print(
        "  RRF fusion -> Combining rankings"
    )

    rrf_scores = {}
    document_map = {}

    # Semantic results

    for rank, result in enumerate(
        semantic_results,
        start=1
    ):

        index = result["index"]

        document_map[index] = result[
            "document"
        ]

        rrf_scores[index] = (
            rrf_scores.get(
                index,
                0.0
            )
            +
            1.0 / (
                RRF_K + rank
            )
        )

    # BM25 results

    for rank, result in enumerate(
        bm25_results,
        start=1
    ):

        index = result["index"]

        document_map[index] = result[
            "document"
        ]

        rrf_scores[index] = (
            rrf_scores.get(
                index,
                0.0
            )
            +
            1.0 / (
                RRF_K + rank
            )
        )

    ranked_indexes = sorted(
        rrf_scores.keys(),
        key=lambda index: rrf_scores[index],
        reverse=True
    )

    results = []

    for rank, index in enumerate(
        ranked_indexes,
        start=1
    ):

        results.append(
            {
                "rank": rank,
                "index": index,
                "rrf_score": rrf_scores[index],
                "document": document_map[index]
            }
        )

    return results


# ============================================================
# HYBRID RETRIEVAL
# ============================================================

def hybrid_retrieve(
    vector_store,
    documents,
    bm25,
    question,
    candidate_k
):

    print(
        "\n  Starting hybrid retrieval..."
    )

    semantic_results = semantic_retrieve(
        vector_store,
        documents,
        question,
        candidate_k
    )

    bm25_results = bm25_retrieve(
        bm25,
        documents,
        question,
        candidate_k
    )

    results = rrf_fusion(
        semantic_results,
        bm25_results
    )

    # IMPORTANT:
    # Do not deduplicate chunks here.
    # Different chunks from the same contract
    # may contain different clauses.

    return results[:FINAL_TOP_K]


# ============================================================
# QUESTION WORDS
# ============================================================

def important_question_words(question):

    stop_words = {
        "what",
        "is",
        "the",
        "a",
        "an",
        "for",
        "does",
        "do",
        "how",
        "many",
        "much",
        "in",
        "of",
        "to",
        "and",
        "must",
        "can",
        "may",
        "are",
        "was",
        "were",
        "agreement",
        "contract",
        "please",
        "tell",
        "me"
    }

    words = tokenize(
        question
    )

    cleaned_words = set()

    for word in words:

        word = word.strip(
            "?,.!'\""
        )

        if (
            word
            and word not in stop_words
            and len(word) > 2
        ):

            cleaned_words.add(
                word
            )

    return cleaned_words


# ============================================================
# KEYWORD RELEVANCE
# ============================================================

def keyword_relevance_score(
    question,
    document
):

    question_words = (
        important_question_words(
            question
        )
    )

    if not question_words:
        return 0.0

    content = document[
        "content"
    ].lower()

    matched = 0

    for word in question_words:

        if word in content:
            matched += 1

    return (
        matched /
        len(question_words)
    )


# ============================================================
# PHRASE RELEVANCE
# ============================================================

def phrase_relevance_score(
    question,
    document
):

    question_lower = question.lower()

    content = document[
        "content"
    ].lower()

    phrases = [
        "confidentiality",
        "confidential information",
        "after leaving",
        "2 years",
        "notice period",
        "security deposit",
        "annual leave",
        "sick leave",
        "monthly rent",
        "termination"
    ]

    matched = 0

    for phrase in phrases:

        if phrase in question_lower:

            if phrase in content:
                matched += 1

    if matched > 0:
        return 1.0

    return 0.0


# ============================================================
# COMBINED RELEVANCE
# ============================================================

def combined_relevance_score(
    question,
    document
):

    keyword_score = keyword_relevance_score(
        question,
        document
    )

    phrase_score = phrase_relevance_score(
        question,
        document
    )

    return max(
        keyword_score,
        phrase_score
    )


# ============================================================
# RETRIEVAL QUALITY CHECK
# ============================================================

def retrieval_is_valid(
    question,
    results
):

    if not results:

        print(
            "  No retrieval results found."
        )

        return False

    best_score = 0.0

    for result in results:

        score = combined_relevance_score(
            question,
            result["document"]
        )

        result["keyword_score"] = score

        if score > best_score:
            best_score = score

    print(
        f"  Best retrieved chunk relevance: "
        f"{best_score:.2f}"
    )

    return best_score >= 0.50


# ============================================================
# RERANK RESULTS
# ============================================================

def rerank_results(
    question,
    results
):

    print(
        "  Applying keyword/phrase reranking..."
    )

    for result in results:

        result["keyword_score"] = (
            combined_relevance_score(
                question,
                result["document"]
            )
        )

    results.sort(
        key=lambda result: (
            result["keyword_score"],
            result["rrf_score"]
        ),
        reverse=True
    )

    for rank, result in enumerate(
        results,
        start=1
    ):

        result["rank"] = rank

    return results


# ============================================================
# RETRIEVAL WITH RETRY
# ============================================================

def retrieve_with_retry(
    vector_store,
    documents,
    bm25,
    question
):

    print("\n")
    print("=" * 70)
    print("RETRIEVAL PROCESS")
    print("=" * 70)

    # ========================================================
    # ATTEMPT 1
    # ========================================================

    print("\nATTEMPT 1")

    results = hybrid_retrieve(
        vector_store,
        documents,
        bm25,
        question,
        NORMAL_CANDIDATE_K
    )

    print(
        "\n  Checking retrieval relevance..."
    )

    # If the best chunk is relevant, rerank
    # so the relevant chunk appears first.

    if retrieval_is_valid(
        question,
        results
    ):

        results = rerank_results(
            question,
            results
        )

        print(
            "\n[OK] Retrieval successful on Attempt 1"
        )

        return {
            "results": results,
            "attempt": 1,
            "retry_used": False
        }

    # ========================================================
    # RETRY
    # ========================================================

    if MAX_RETRIES <= 0:

        return {
            "results": results,
            "attempt": 1,
            "retry_used": False
        }

    print(
        "\n[WARN] Initial retrieval was insufficient."
    )

    print(
        "[RETRY] RETRYING RETRIEVAL..."
    )

    # ========================================================
    # ATTEMPT 2
    # ========================================================

    print("\nATTEMPT 2")

    retry_results = hybrid_retrieve(
        vector_store,
        documents,
        bm25,
        question,
        RETRY_CANDIDATE_K
    )

    retry_results = rerank_results(
        question,
        retry_results
    )

    print(
        "\n  Checking retry retrieval relevance..."
    )

    if retrieval_is_valid(
        question,
        retry_results
    ):

        print(
            "\n[OK] Retrieval successful on Attempt 2"
        )

    else:

        print(
            "\n[WARN] Retry completed, but relevant "
            "content was not strongly detected."
        )

    return {
        "results": retry_results,
        "attempt": 2,
        "retry_used": True
    }


# ============================================================
# DISPLAY RETRIEVAL RESULTS
# ============================================================

def display_results(results):

    print("\n")
    print("=" * 70)
    print("RETRIEVED DOCUMENTS")
    print("=" * 70)

    for result in results:

        document = result[
            "document"
        ]

        metadata = document[
            "metadata"
        ]

        source = get_filename(
            metadata.get(
                "source"
            )
        )

        page = get_page(
            metadata
        )

        print(
            f"\nRank: {result['rank']}"
        )

        print(
            f"Document: {source}"
        )

        print(
            f"Page: {page}"
        )

        print(
            f"RRF Score: "
            f"{result['rrf_score']:.6f}"
        )

        print(
            f"Relevance Score: "
            f"{result.get('keyword_score', 0.0):.2f}"
        )

        print("\nContent:")

        print(
            document["content"][:500]
        )


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    print("\n")
    print("=" * 70)
    print("LEGAL CONTRACT HYBRID RETRIEVAL")
    print("=" * 70)

    vector_store = load_vector_store()

    documents = load_all_documents(
        vector_store
    )

    print(
        f"\nLoaded chunks: {len(documents)}"
    )

    bm25 = create_bm25(
        documents
    )

    question = input(
        "\nEnter your legal contract question: "
    ).strip()

    if not question:

        print(
            "\nQuestion cannot be empty."
        )

        raise SystemExit

    retrieval = retrieve_with_retry(
        vector_store,
        documents,
        bm25,
        question
    )

    print("\n")
    print("=" * 70)

    print(
        f"Retrieval attempt: "
        f"{retrieval['attempt']}"
    )

    print(
        f"Retry used: "
        f"{retrieval['retry_used']}"
    )

    print("=" * 70)

    display_results(
        retrieval["results"]
    )