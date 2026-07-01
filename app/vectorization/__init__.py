"""
app/vectorization — Phase 3 embedding sub-package.

Transforms a ``List[Document]`` produced by Phase 2 into a
``List[EmbeddedDocument]`` using the BAAI/bge-m3 embedding model via
SentenceTransformers.

Public re-exports:

    from app.vectorization import EmbeddingPipeline
"""

from app.vectorization.embedding_pipeline import EmbeddingPipeline

__all__ = ["EmbeddingPipeline"]
