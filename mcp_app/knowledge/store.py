# mcp_app/knowledge/store.py
import chromadb
import os
from chromadb.utils import embedding_functions

# ── Initialize ChromaDB ───────────────────────────────────────
_client     = None
_collection = None

def get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection

    # Store on disk — persists between restarts
    _client = chromadb.PersistentClient(
        path=os.path.join(os.path.dirname(__file__), "chroma_db")
    )

    # Use sentence-transformers for embeddings (free, local)
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"  # small, fast, good quality
    )

    _collection = _client.get_or_create_collection(
        name              = "pinky_tarot_knowledge",
        embedding_function = embedding_fn,
        metadata          = {"description": "Pinky Tarot business knowledge base"},
    )

    return _collection


def add_knowledge(documents: list[dict]):
    """
    Add knowledge to ChromaDB.
    Each doc: { id, text, metadata }
    """
    collection = get_collection()
    collection.upsert(
        ids        = [d["id"]       for d in documents],
        documents  = [d["text"]     for d in documents],
        metadatas  = [d.get("metadata", {}) for d in documents],
    )
    print(f"✅ Added {len(documents)} knowledge entries")


def search_knowledge(query: str, n_results: int = 3) -> list[str]:
    """
    Search for relevant knowledge based on user query.
    Returns list of relevant text chunks.
    """
    collection = get_collection()

    # Skip if collection is empty
    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts = [query],
        n_results   = min(n_results, collection.count()),
    )

    return results["documents"][0] if results["documents"] else []


def get_all_knowledge() -> list[dict]:
    """Get all stored knowledge"""
    collection = get_collection()
    results    = collection.get()
    return [
        {"id": id_, "text": doc, "metadata": meta}
        for id_, doc, meta in zip(
            results["ids"],
            results["documents"],
            results["metadatas"],
        )
    ]


def delete_knowledge(id: str):
    """Delete a knowledge entry"""
    get_collection().delete(ids=[id])


def clear_all_knowledge():
    """Clear entire knowledge base"""
    collection = get_collection()
    all_ids    = collection.get()["ids"]
    if all_ids:
        collection.delete(ids=all_ids)
    print("🗑️ Knowledge base cleared")