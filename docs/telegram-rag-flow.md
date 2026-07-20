# Nexora Telegram RAG Flow

## End-to-End Flow (Mock Stage)

```
Mock Fixture Event (JSON)
  ↓
MockTelegramClient.updates()
  ↓
TelegramNormalizer.normalize(event, owner_id)
  → Produces List[KnowledgeObject]
  ↓
TelegramIngestionPolicy.decide(obj)
  → PROCESS / PROCESS_EDIT / PROCESS_DELETE / IGNORE
  ↓  (if PROCESS)
TelegramDeduplicationService.is_duplicate(vector_id)
  → skip if already indexed
  ↓  (if not duplicate)
Content Processor (routing by content_type)
  text/link  → text processor
  pdf        → PDF extractor
  docx       → DOCX extractor
  pptx       → PPTX extractor
  image      → OCR processor
  voice      → speech-to-text
  video      → caption + audio
  ↓
MessageChunker (token-bounded, 450 tokens, 50-token overlap)
  ↓
EmbeddingPipeline (BAAI/bge-m3, 1024-dim)
  ↓
Phase4Pipeline → ChromaDB (with Telegram metadata)
  ↓
TelegramDeduplicationService.mark_processed(vector_id)
```

## Query Flow

```
POST /query
  {
    "question": "What deadline did Anu mention?",
    "filters": {
      "owner_id": "user_123",
      "source": "telegram",
      "conversation_id": "tg_chat_anu_001"
    }
  }
  ↓
QueryPreprocessor → QueryEmbedder (BGE-M3)
  ↓
MetadataFilter.build(filters) → ChromaDB where-clause
  ↓
SimilaritySearch → top-k RetrievedDocuments
  ↓
SnippetExtraction (Phase 5B) → focused_snippet
  ↓
Phase6Pipeline → ContextBuilder + PromptBuilder + LLM
  ↓
QueryResponse {
  answer: "Anu said the project report must be submitted before Monday.",
  citations: [{ source_chat: "tg_chat_anu_001", sender_id: "tg_user_anu_001", ... }],
  retrieved_documents: [...]
}
```

## Future-Message Filtering

Only messages received **after** `indexing_enabled_at` are indexed:

```python
if message.timestamp < indexing_enabled_at:
    return IngestionDecision(action=IGNORE, reason="Before activation time")
```

Historical messages are **never** indexed. This is a hard rule, not a soft default.

## Contact-Filtered Queries

Retrieve only Anu's messages:
```json
{ "owner_id": "user_123", "source": "telegram",
  "conversation_id": "tg_chat_anu_001" }
```

Retrieve only Arun's messages in a group:
```json
{ "owner_id": "user_123", "source": "telegram",
  "conversation_id": "tg_group_project_001",
  "sender_id": "tg_user_arun_001" }
```

Queries are **never** filtered by `sender_name` — only by `sender_id`.
Display names can collide; stable IDs cannot.
