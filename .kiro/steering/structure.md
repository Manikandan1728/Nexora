# Nexora — Key Existing Components (do not duplicate — extend)

- KnowledgeObject: models/knowledge_object.py
- Telegram domain models: app/integrations/telegram/models/telegram_models.py
- TelegramNormalizer: app/integrations/telegram/mapping/telegram_normalizer.py
- ContentTypeMapper: app/integrations/telegram/mapping/content_type_mapper.py
- SenderResolver: app/integrations/telegram/mapping/sender_resolver.py
- TelegramIngestionPolicy: app/integrations/telegram/services/ingestion_policy.py
- TelegramDeduplicationService: app/integrations/telegram/services/deduplication_service.py
- TelegramClient protocol: app/integrations/telegram/client/base_telegram_client.py
- MockTelegramClient: app/integrations/telegram/client/mock_telegram_client.py
- TDLib stub: app/integrations/telegram/client/tdlib_client.py
- Telegram API endpoints: api/routes/telegram.py
- Frontend Telegram types/service: frontend/src/types/telegram.ts, frontend/src/api/telegram.service.ts
- Frontend Telegram pages: frontend/src/features/telegram/
- Existing chunking: app/documents/chunker.py, app/documents/phase2_pipeline.py
- Existing embedding: app/vectorization/embedding_pipeline.py
- ChromaDB integration: app/storage/vector_store/
- Similarity search: app/retrieval/similarity_search.py
- Metadata filter (existing): app/retrieval/metadata_filter.py
- RAG query service: api/services/query_service.py
- FastAPI query endpoint: api/routes/query.py
- React search interface: frontend/src/features/search/SearchPage.tsx

Run the repo audit in Requirement 0 before writing new files — most needed
scaffolding already exists and must be extended, not replaced.
