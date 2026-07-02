"""
app/storage/vector_store — Phase 4 vector storage sub-package.

Stores ``List[EmbeddedDocument]`` objects into a persistent ChromaDB
collection, preserving embeddings, document text, and all metadata.

Public re-exports:

    from app.storage.vector_store import Phase4Pipeline, ChromaVectorStore
"""

from app.storage.vector_store.chroma_store import ChromaVectorStore
from app.storage.vector_store.phase4_pipeline import Phase4Pipeline

__all__ = ["ChromaVectorStore", "Phase4Pipeline"]
