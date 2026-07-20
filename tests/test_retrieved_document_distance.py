import pytest
import math
from models.retrieved_document import RetrievedDocument

def test_distance_positive_unchanged():
    doc = RetrievedDocument(
        document_id="d1",
        text="text",
        metadata={},
        distance=0.5,
        similarity_score=0.5,
        rank=1,
        source_collection="col",
        query="q"
    )
    assert doc.distance == 0.5

def test_distance_zero_unchanged():
    doc = RetrievedDocument(
        document_id="d1",
        text="text",
        metadata={},
        distance=0.0,
        similarity_score=1.0,
        rank=1,
        source_collection="col",
        query="q"
    )
    assert doc.distance == 0.0

def test_distance_small_negative_normalized():
    doc = RetrievedDocument(
        document_id="d1",
        text="text",
        metadata={},
        distance=-1e-9,
        similarity_score=1.0,
        rank=1,
        source_collection="col",
        query="q"
    )
    assert doc.distance == 0.0

def test_distance_exact_tolerance_normalized():
    doc = RetrievedDocument(
        document_id="d1",
        text="text",
        metadata={},
        distance=-1e-8,
        similarity_score=1.0,
        rank=1,
        source_collection="col",
        query="q"
    )
    assert doc.distance == 0.0

def test_distance_large_negative_raises():
    with pytest.raises(ValueError, match="RetrievedDocument.distance must be >= 0"):
        RetrievedDocument(
            document_id="d1",
            text="text",
            metadata={},
            distance=-1.1e-8,
            similarity_score=1.0,
            rank=1,
            source_collection="col",
            query="q"
        )

def test_distance_nan_raises():
    with pytest.raises(ValueError, match="RetrievedDocument.distance must be finite"):
        RetrievedDocument(
            document_id="d1",
            text="text",
            metadata={},
            distance=math.nan,
            similarity_score=1.0,
            rank=1,
            source_collection="col",
            query="q"
        )

def test_distance_inf_raises():
    with pytest.raises(ValueError, match="RetrievedDocument.distance must be finite"):
        RetrievedDocument(
            document_id="d1",
            text="text",
            metadata={},
            distance=math.inf,
            similarity_score=1.0,
            rank=1,
            source_collection="col",
            query="q"
        )
