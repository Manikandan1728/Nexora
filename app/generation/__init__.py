"""
app/generation — Phase 6 grounded answer generation sub-package.

Converts a user question + List[RetrievedDocument] into a GroundedAnswer
by building a context string, assembling a grounded prompt, calling an
LLM provider, and attaching citations.

Public exports:

    from app.generation import (
        ContextBuilder,
        PromptBuilder,
        CitationBuilder,
        AnswerGenerator,
        Phase6Pipeline,
    )

Note: imports are kept at the module level but each submodule defers any
heavy initialisation (e.g. LLM client construction) to the first method
call, so importing this package never triggers network I/O or model loads.
"""

from app.generation.context_builder import ContextBuilder
from app.generation.prompt_builder import PromptBuilder
from app.generation.citation_builder import CitationBuilder
from app.generation.answer_generator import AnswerGenerator
from app.generation.phase6_pipeline import Phase6Pipeline

__all__ = [
    "ContextBuilder",
    "PromptBuilder",
    "CitationBuilder",
    "AnswerGenerator",
    "Phase6Pipeline",
]
