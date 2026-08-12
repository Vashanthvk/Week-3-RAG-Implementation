from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma


# ============================================================
# Configuration
# ============================================================

DOCUMENT_PATH = "contracts"

CHUNK_SIZE = 500

CHUNK_OVERLAP = 100

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

CHROMA_PATH = "./chroma_db"

COLLECTION_NAME = "legal_contracts"


# ============================================================
# Load Documents
# ============================================================

def load_documents():

    loader = PyPDFDirectoryLoader(
        DOCUMENT_PATH
    )

    documents = loader.load()

    print(f"\nLoaded {len(documents)} pages.")

    return documents


# ============================================================
# Split Documents
# ============================================================

def split_documents(documents):

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )

    chunks = splitter.split_documents(
        documents
    )

    print(f"Created {len(chunks)} chunks.")

    return chunks


# ============================================================
# Create Embedding Model
# ============================================================

def create_embedding_model():

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL
    )

    return embeddings


# ============================================================
# Test Embedding
# ============================================================

def test_embedding(
    chunks,
    embedding_model
):

    vector = embedding_model.embed_query(
        chunks[0].page_content
    )

    print("\nEmbedding Test")

    print("-" * 50)

    print(
        f"Vector Length : {len(vector)}"
    )

    print("\nFirst 10 Values")

    print(vector[:10])


# ============================================================
# Create Vector Database
# ============================================================

def create_vector_database(
    chunks,
    embedding_model
):

    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embedding_model,
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_PATH
    )

    print(
        "\nVector database created successfully."
    )

    print(
        f"Database location: {CHROMA_PATH}"
    )

    return vector_store


# ============================================================
# Main
# ============================================================

def main():

    documents = load_documents()

    if not documents:

        print(
            "No documents found in the contracts folder."
        )

        return

    chunks = split_documents(
        documents
    )

    embedding_model = create_embedding_model()

    test_embedding(
        chunks,
        embedding_model
    )

    create_vector_database(
        chunks,
        embedding_model
    )


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":

    main()