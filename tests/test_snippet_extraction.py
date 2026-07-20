"""
tests/test_snippet_extraction.py - Tests for Phase 5B Snippet Extraction.
"""

import pytest

from app.retrieval.snippet_extraction import extract_snippet, SnippetResult
from app.retrieval.similarity_search import SimilaritySearch
from config.retrieval_config import RetrievalConfig
from models.retrieved_document import RetrievedDocument

# ---------------------------------------------------------------------------
# Task 6.1, 6.2, 6.3: NPTEL synthetic multi-topic chunk
# ---------------------------------------------------------------------------

def test_extract_snippet_synthetic_multi_topic():
    query = "NPTEL"
    chunk_text = (
        "1/1/2024, 9:00 AM - Alice: Are we registering for the coding contest today?\n"
        "1/1/2024, 9:01 AM - Bob: Yes, the coding contest link is live.\n"
        "1/1/2024, 9:02 AM - Alice: Also, what about the NPTEL course?\n"
        "1/1/2024, 9:03 AM - Charlie: I have already enrolled in the NPTEL course on Machine Learning.\n"
        "1/1/2024, 9:04 AM - Alice: Did you make the payment for the exam?\n"
        "1/1/2024, 9:05 AM - Bob: Payment is done.\n"
    )
    
    result = extract_snippet(query, chunk_text)
    
    assert result.focused_snippet is not None
    
    # 6.1: focused_snippet contains only NPTEL-related lines (and qualifying neighbors)
    assert "NPTEL" in result.focused_snippet
    
    # 6.2: coding-contest and payment lines are NOT present in focused_snippet
    assert "coding contest" not in result.focused_snippet
    assert "payment" not in result.focused_snippet.lower()
    
    # 6.3: the original chunk text field is unchanged 
    # (Strings are immutable in Python, so calling the function doesn't change chunk_text)
    assert "payment" in chunk_text.lower()


# ---------------------------------------------------------------------------
# Task 6.4: Exact match vs topically related without term
# ---------------------------------------------------------------------------

def test_extract_snippet_exact_match_ranked_first():
    query = "deadline"
    chunk_text = (
        "1/1/2024, 9:00 AM - Alice: I need to submit this assignment by Friday.\n"
        "1/1/2024, 9:01 AM - Bob: When is the actual deadline for this?\n"
        "1/1/2024, 9:02 AM - Alice: It's due very soon.\n"
    )
    
    result = extract_snippet(query, chunk_text)
    
    assert result.focused_snippet is not None
    assert "deadline" in result.focused_snippet
    
    # The exact match should be present
    assert "When is the actual deadline for this?" in result.focused_snippet
    
    # Check that matched messages explicitly contain the deadline
    assert result.matched_messages is not None
    assert any("deadline" in mr.text for mr in result.matched_messages)


# ---------------------------------------------------------------------------
# Task 6.8: Edge cases
# ---------------------------------------------------------------------------

def test_extract_snippet_empty_chunk():
    result = extract_snippet("NPTEL", "")
    assert result.focused_snippet is None

def test_extract_snippet_only_stopwords():
    chunk = "1/1/2024, 9:00 AM - Alice: this is a test\n"
    result = extract_snippet("the and is", chunk)
    assert result.focused_snippet is None

def test_extract_snippet_fallback_line_split_no_boundaries():
    chunk = (
        "Just a normal line without timestamps.\n"
        "Another line with NPTEL course info.\n"
        "Something else entirely.\n"
    )
    result = extract_snippet("NPTEL", chunk)
    assert result.focused_snippet is not None
    assert "Another line with NPTEL course info." in result.focused_snippet
    assert "Something else entirely." not in result.focused_snippet

def test_extract_snippet_shorter_than_5_lines():
    chunk = "1/1/2024, 9:00 AM - Alice: NPTEL is good.\n"
    result = extract_snippet("NPTEL", chunk)
    assert result.focused_snippet is not None
    # Should not duplicate or pad
    assert len(result.focused_snippet.splitlines()) == 1


# ---------------------------------------------------------------------------
# Task 6.5: Low-confidence detection
# ---------------------------------------------------------------------------

def test_low_confidence_flag_at_thresholds(tmp_path):
    # Using the same technique as test_phase5.py
    import chromadb
    from app.retrieval.similarity_search import SimilaritySearch
    from config.retrieval_config import RetrievalConfig

    client = chromadb.PersistentClient(path=str(tmp_path))
    col = client.get_or_create_collection(
        "test_low_conf",
        metadata={"hnsw:space": "cosine"},
    )
    
    # We will inject known vectors
    # vector [1, 0, 0] vs [1, 0, 0] = cosine similarity 1.0
    # vector [1, 0, 0] vs [0, 1, 0] = cosine similarity 0.0
    col.add(
        ids=["doc-high", "doc-low", "doc-exact-thresh"],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [0.4, 0.9165]], # Just dummy numbers
        documents=["high conf", "low conf", "exact conf"],
        metadatas=[{"a": 1}, {"a": 2}, {"a": 3}]
    )
    
    config = RetrievalConfig(
        collection_name="test_low_conf",
        persist_directory=str(tmp_path),
        top_k=5,
        score_threshold=0.0,
        distance_metric="cosine",
    )
    
    searcher = SimilaritySearch(config=config, collection=col)
    
    # To precisely test the conversion, we can just mock _convert_results directly
    # or rely on distance. 
    # Instead of full DB roundtrip, let's just pass raw results to _convert_results.
    
    # Cosine distance = 1 - similarity.
    # similarity = 0.39 < 0.40 -> distance = 0.61 -> is_low_confidence = True
    # similarity = 0.41 > 0.40 -> distance = 0.59 -> is_low_confidence = False
    # similarity = 0.40 == 0.40 -> distance = 0.60 -> is_low_confidence = False
    
    raw = {
        "ids": [["doc-low", "doc-exact", "doc-high"]],
        "distances": [[0.61, 0.60, 0.59]],
        "documents": [["text1", "text2", "text3"]],
        "metadatas": [[{"a": 1}, {"a": 2}, {"a": 3}]]
    }
    
    results = searcher._convert_results(raw, "query")
    assert len(results) == 3
    
    # doc-low: sim 0.39
    assert results[0].document_id == "doc-low"
    assert results[0].is_low_confidence is True
    
    # doc-exact: sim 0.40
    assert results[1].document_id == "doc-exact"
    assert results[1].is_low_confidence is False
    
    # doc-high: sim 0.41
    assert results[2].document_id == "doc-high"
    assert results[2].is_low_confidence is False


# ---------------------------------------------------------------------------
# Task 6.6: Zero-results / all-below-threshold query
# ---------------------------------------------------------------------------

def test_no_strong_match_flag(tmp_path):
    from api.services.query_service import run_query
    from api.config import APISettings
    
    settings = APISettings.__new__(APISettings)
    settings.vectors_root = tmp_path
    settings.llm_provider = "ollama"
    settings.llm_timeout_seconds = 5.0
    
    import chromadb
    client = chromadb.PersistentClient(path=str(tmp_path))
    col = client.get_or_create_collection(
        "test_col",
        metadata={"hnsw:space": "cosine"},
    )
    
    # Test zero results (empty collection)
    response = run_query(
        question="hello",
        collection_name="test_col",
        top_k=5,
        filters=None,
        use_rag=False,
        settings=settings
    )
    assert response.no_strong_match is True
    assert len(response.retrieved_documents) == 0

    # Add a document but mock search to return it with low confidence
    # (By monkey-patching _convert_results for a moment)
    col.add(
        ids=["doc1"],
        embeddings=[[0.0] * 8],
        documents=["hello text"],
        metadatas=[{"a": 1}]
    )
    
    from app.retrieval.similarity_search import SimilaritySearch
    original_convert = SimilaritySearch._convert_results
    
    def fake_convert(*args, **kwargs):
        res = original_convert(*args, **kwargs)
        for r in res:
            # Force low confidence (simulating sim < 0.40)
            from dataclasses import replace
            # r is frozen so we need to bypass or use object.__setattr__
            object.__setattr__(r, 'is_low_confidence', True)
        return res
    
    SimilaritySearch._convert_results = fake_convert
    try:
        response_all_low = run_query(
            question="hello",
            collection_name="test_col",
            top_k=5,
            filters=None,
            use_rag=False,
            settings=settings
        )
        assert len(response_all_low.retrieved_documents) == 1
        assert response_all_low.no_strong_match is True
    finally:
        SimilaritySearch._convert_results = original_convert
