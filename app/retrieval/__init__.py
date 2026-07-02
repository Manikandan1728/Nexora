"""
app/retrieval — Phase 5 semantic retrieval sub-package.

Converts a user query string into a ``List[RetrievedDocument]`` by:
  1. Preprocessing the query text
  2. Embedding the query with the same BGE-M3 model used in Phase 3
  3. Optionally building a ChromaDB metadata filter
  4. Executing a similarity search against the Phase 4 collection
  5. Converting results into ranked ``RetrievedDocument`` objects

Public re-exports:

    from app.retrieval import RetrievalPipeline
"""

# Lazy import to avoid triggering SentenceTransformers model loading at
# collection time.  The import only resolves when RetrievalPipeline is
# actually used.
def __getattr__(name: str):
    if name == "RetrievalPipeline":
        from app.retrieval.retrieval_pipeline import RetrievalPipeline
        return RetrievalPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["RetrievalPipeline"]
