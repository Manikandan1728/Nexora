"""Check which ChromaDB 1.5.9 filter operators are actually supported."""
import chromadb, tempfile

client = chromadb.PersistentClient(path=tempfile.mkdtemp())
col = client.get_or_create_collection("test_filter_syntax", metadata={"hnsw:space": "cosine"})
col.add(
    ids=["d1", "d2", "d3"],
    embeddings=[[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]],
    documents=["a", "b", "c"],
    metadatas=[
        {"owner_id": "u1", "source": "telegram", "conv": "c1"},
        {"owner_id": "u1", "source": "telegram", "conv": "c2"},
        {"owner_id": "u2", "source": "telegram", "conv": "c1"},
    ],
)

# Test $or
try:
    r = col.get(where={"$or": [{"conv": {"$eq": "c1"}}, {"conv": {"$eq": "c2"}}]})
    print("$or supported, count:", len(r["ids"]))
except Exception as e:
    print("$or failed:", e)

# Test $in
try:
    r = col.get(where={"conv": {"$in": ["c1", "c2"]}})
    print("$in supported, count:", len(r["ids"]))
except Exception as e:
    print("$in failed:", e)

# Test $and with owner + source
try:
    r = col.get(where={"$and": [{"owner_id": {"$eq": "u1"}}, {"source": {"$eq": "telegram"}}]})
    print("$and ok, count:", len(r["ids"]))
except Exception as e:
    print("$and failed:", e)

# Test nested $and with $or inside
try:
    r = col.get(where={
        "$and": [
            {"owner_id": {"$eq": "u1"}},
            {"$or": [{"conv": {"$eq": "c1"}}, {"conv": {"$eq": "c2"}}]},
        ]
    })
    print("nested $and+$or ok, count:", len(r["ids"]))
except Exception as e:
    print("nested $and+$or failed:", e)
