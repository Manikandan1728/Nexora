"""
app/documents — Phase 2 document conversion sub-package.

Converts a ``Chat`` object produced by Phase 1 into a ``List[Document]``
suitable for embedding by BAAI/bge-m3 (Phase 3).

Public re-exports (everything a caller needs):

    from app.documents import Phase2Pipeline, Document
"""

from app.documents.phase2_pipeline import Phase2Pipeline

__all__ = ["Phase2Pipeline"]
