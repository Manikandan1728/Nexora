# Nexora Repository Audit Report

> Generated before any Telegram transformation changes begin.  
> This is the single source of truth for component classification.

---

## Baseline Test Results (pre-transformation)

| Suite | Command | Result |
|---|---|---|
| Ignoring broken import test files | `pytest --ignore=test_phase2.py --ignore=test_phase3.py` | **436 passed, 2 failed (pre-existing)** |
| Full suite | `pytest` | Interrupted (import error in test_phase2/3 due to huggingface-hub version mismatch — pre-existing env issue, not a code bug) |

Pre-existing failures (NOT caused by this project):
1. `test_phase5.py::TestSimilaritySearch::test_score_threshold_filters_low_scores` — logic mismatch in test assertion, pre-existing
2. `test_snippet_extraction.py::test_no_strong_match_flag` — APISettings mock issue, pre-existing
3. `test_phase2.py`, `test_phase3.py` — collection errors due to `huggingface-hub==1.23.0` version conflict, pre-existing env issue

---

## Component Classification

### ✅ PRESERVE — Generic/Shared (no WhatsApp assumptions)

| Component | File(s) | Current Consumers | Notes |
|---|---|---|---|
| EmbeddingModel (BGE-M3) | `app/vectorization/embedding_model.py` | `EmbeddingPipeline`, `EmbeddingBatcher`, `EmbeddingGenerator` | No source assumptions |
| EmbeddingPipeline | `app/vectorization/embedding_pipeline.py` | `upload_service.py` | Accepts `List[Document]` — needs `Document` generalization |
| EmbeddingCache | `app/vectorization/embedding_cache.py` | `EmbeddingBatcher` | Pure text-keyed cache |
| EmbeddingBatcher | `app/vectorization/embedding_batcher.py` | `EmbeddingPipeline` | Source-independent |
| Phase4Pipeline (ChromaDB) | `app/storage/vector_store/phase4_pipeline.py` | `upload_service.py` | Accepts `List[EmbeddedDocument]` |
| ChromaVectorStore | `app/storage/vector_store/chroma_store.py` | `Phase4Pipeline` | Source-independent |
| StoragePersistence | `app/storage/vector_store/persistence.py` | `SimilaritySearch` | Source-independent |
| CollectionManager | `app/storage/vector_store/collection_manager.py` | Internal | Source-independent |
| VectorStoreInterfaces | `app/storage/vector_store/interfaces.py` | `Phase4Pipeline` | Source-independent |
| RetrievalPipeline | `app/retrieval/retrieval_pipeline.py` | `query_service.py` | Source-independent |
| SimilaritySearch | `app/retrieval/similarity_search.py` | `RetrievalPipeline` | Source-independent |
| QueryPreprocessor | `app/retrieval/query_preprocessor.py` | `RetrievalPipeline` | Source-independent |
| QueryEmbedder | `app/retrieval/query_embedder.py` | `RetrievalPipeline` | Source-independent |
| MetadataFilter | `app/retrieval/metadata_filter.py` | `RetrievalPipeline` | Needs new Telegram fields added |
| SnippetExtraction | `app/retrieval/snippet_extraction.py` | `query_service.py` | Source-independent |
| Phase6Pipeline (RAG) | `app/generation/phase6_pipeline.py` | `query_service.py` | Source-independent |
| ContextBuilder | `app/generation/context_builder.py` | `Phase6Pipeline` | Source-independent |
| CitationBuilder | `app/generation/citation_builder.py` | `Phase6Pipeline` | Source-independent |
| AnswerGenerator | `app/generation/answer_generator.py` | `Phase6Pipeline` | Source-independent |
| PromptBuilder | `app/generation/prompt_builder.py` | `AnswerGenerator` | Source-independent |
| MessageChunker | `app/documents/chunker.py` | `Phase2Pipeline` | Operates on Message — needs generic version |
| TokenizerService | `app/documents/tokenizer_service.py` | `MessageChunker`, `DocumentBuilder`, `Phase2Pipeline` | Source-independent |
| TextCleaner | `app/documents/cleaner.py` | `Phase2Pipeline` | Source-independent |
| TextNormalizer | `app/documents/normalizer.py` | `Phase2Pipeline` | Source-independent |
| MetadataEnricher | `app/documents/metadata_enricher.py` | `Phase2Pipeline` | Uses Document — needs generalization |
| DocumentBuilder | `app/documents/document_builder.py` | `Phase2Pipeline` | Uses Message/Document — needs generalization |
| EmbeddedDocument model | `models/embedded_document.py` | `EmbeddingPipeline`, `Phase4Pipeline` | Source-independent |
| RetrievedDocument model | `models/retrieved_document.py` | `RetrievalPipeline`, `query_service.py` | Source-independent |
| GroundedAnswer / Citation | `models/answer.py` | `Phase6Pipeline`, `query_service.py` | Source-independent |
| Document model | `models/document.py` | `Phase2Pipeline`, `EmbeddingPipeline` | Source-independent |
| Exceptions | `exceptions/exceptions.py` | All modules | Source-independent |
| RegexPatterns | `utils/regex_patterns.py` | `ChatParser`, `SnippetExtraction` | WhatsApp patterns — KEEP for legacy |
| DateTimeUtils | `utils/datetime_utils.py` | `MetadataEnricher` | Source-independent |
| FileUtils | `utils/file_utils.py` | `Phase1Pipeline` | Source-independent |
| LLMConfig | `config/llm_config.py` | `Phase6Pipeline`, `query_service.py` | Source-independent |
| VectorStoreConfig | `config/vector_config.py` | `Phase4Pipeline` | Source-independent |
| RetrievalConfig | `config/retrieval_config.py` | `RetrievalPipeline` | Source-independent |
| SnippetConfig | `config/snippet_config.py` | `SnippetExtraction` | Source-independent |
| LLM Providers | `llm/` | `Phase6Pipeline`, `query_service.py` | Source-independent |
| FastAPI app + routes | `api/` | Frontend | Needs Telegram routes added |
| Frontend (all pages) | `frontend/src/` | Users | Needs Telegram pages added |

### ⚠️ GENERALIZE — Shared but coupled to WhatsApp concepts

| Component | File(s) | Current Consumers | What Needs Changing |
|---|---|---|---|
| Document model | `models/document.py` | `Phase2Pipeline`, `DocumentBuilder`, `EmbeddingPipeline` | `source_chat` field is WhatsApp-flavored; needs `source`/`conversation_id` metadata |
| DocumentBuilder | `app/documents/document_builder.py` | `Phase2Pipeline` | Text format `"Sender: body"` is WhatsApp-specific; make configurable |
| Phase2Pipeline | `app/documents/phase2_pipeline.py` | `upload_service.py` | `_build_source_label()` assumes `participants` list (WhatsApp pattern) |
| MetadataEnricher | `app/documents/metadata_enricher.py` | `Phase2Pipeline` | Attachment classification uses WhatsApp omission keywords |
| MetadataFilter | `app/retrieval/metadata_filter.py` | `RetrievalPipeline` | Field allowlist doesn't include Telegram fields |

### 🔴 DEPRECATE — WhatsApp-specific (move to legacy in Phase 17)

| Component | File(s) | Current Consumers | Risk if Removed |
|---|---|---|---|
| ChatParser | `parser/chat_parser.py` | `Phase1Pipeline` | Phase1Pipeline breaks |
| AttachmentDetector | `parser/attachment_detector.py` | `Phase1Pipeline` | Phase1Pipeline breaks |
| MetadataParser | `parser/metadata_parser.py` | `Phase1Pipeline` | Phase1Pipeline breaks |
| ZipValidator | `app/zip_validator.py` | `Phase1Pipeline` | Phase1Pipeline breaks |
| DatasetValidator | `app/dataset_validator.py` | `Phase1Pipeline` | Phase1Pipeline breaks |
| Extractor | `app/extractor.py` | `Phase1Pipeline` | Phase1Pipeline breaks |
| InputDetector | `app/input_detector.py` | `Phase1Pipeline`, `upload_service.py` | Both break |
| Phase1Pipeline | `pipeline/phase1_pipeline.py` | `upload_service.py` | Upload endpoint breaks |
| Message model | `models/message.py` | `ChatParser`, `Phase1Pipeline`, `Phase2Pipeline`, `MessageChunker`, `DocumentBuilder` | Chain breaks |
| Chat model | `models/chat.py` | `Phase1Pipeline`, `Phase2Pipeline` | Phase1/2 break |
| ChatMetadata model | `models/metadata.py` | `Phase1Pipeline`, `MetadataParser` | Phase1 breaks |
| Attachment model | `models/attachment.py` | `AttachmentDetector`, `Phase1Pipeline` | Phase1 breaks |
| Upload route + service | `api/routes/upload.py`, `api/services/upload_service.py` | Frontend UploadPage | Frontend upload breaks |
| Upload frontend page | `frontend/src/features/upload/` | Router | Page disappears |
| WhatsApp ZIP files at root | `*.zip` at project root | Manual testing only | No code impact |
| WhatsApp scripts | `scripts/test_real_whatsapp_pipeline.py`, `scripts/validate_*.py` | Manual only | No code impact |

### 🆕 NEW — Required for Telegram integration

| Component | Location | Phase |
|---|---|---|
| KnowledgeObject model | `models/knowledge_object.py` | Phase 1 |
| TelegramAccount, TelegramChat, TelegramMessage, TelegramAttachment, TelegramIndexingPreference, TelegramProcessingState | `app/integrations/telegram/models/` | Phase 3 |
| Mock Telegram event fixtures | `tests/fixtures/telegram/` | Phase 4 |
| TelegramNormalizer | `app/integrations/telegram/mapping/telegram_normalizer.py` | Phase 5 |
| TelegramIngestionPolicy | `app/integrations/telegram/services/ingestion_policy.py` | Phase 6 |
| TelegramClient interface + MockTelegramClient | `app/integrations/telegram/client/` | Phases 5, 15 |
| TDLib abstraction stubs | `app/integrations/telegram/client/tdlib_client.py` | Phase 15 |
| Telegram API routes | `api/routes/telegram.py` | Phase 14 |
| Telegram frontend pages | `frontend/src/features/telegram/` | Phase 13 |
| CHANGELOG.md | root | All phases |

---

## Migration Risks

1. **huggingface-hub version conflict** — `transformers` requires `<1.0`, installed is `1.23.0`. This blocks `test_phase2.py` and `test_phase3.py` collection. Pre-existing, not introduced by this project. Cannot be fixed without `pip install transformers -U`.
2. **Message model coupling** — `Message`, `Chat`, `ChatMetadata` are deeply threaded through Phases 1-2. Any generalization must keep them working for the WhatsApp path while adding Telegram path.
3. **MetadataFilter allowlist** — adding Telegram fields must not break existing non-Telegram queries.
4. **`source_chat` in stored vectors** — existing ChromaDB collections have `source_chat` in metadata; any new metadata schema must not break retrieval of these collections.

---

## Recommended Implementation Order

1. ✅ Audit (this document)
2. Add `KnowledgeObject` model (additive only)
3. Add `app/integrations/telegram/` skeleton (additive only)
4. Add Telegram DB models (additive only)
5. Add mock fixtures (additive only)
6. Add TelegramNormalizer (additive only)
7. Add ingestion policy (additive only)
8. Add deduplication service (additive only)
9. Extend MetadataFilter to support Telegram fields (refactor-safe)
10. Add Telegram API routes (additive)
11. Add TDLib abstraction stubs (additive)
12. Add frontend Telegram pages (additive)
13. Add tests (additive)
14. Add documentation (additive)
15. Move WhatsApp code to legacy (deprecated — Phase 17)
