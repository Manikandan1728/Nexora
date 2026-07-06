# Nexora — Multi-Dataset Validation Report

Generated automatically by `scripts/validate_all_datasets.py`.

---

## Per-Dataset Results

### WhatsApp Chat with annie.zip

| Field | Value |
|---|---|
| ZIP size | 226.4 MB |
| Collection | `nexora_val_whatsapp_chat_with_annie` |
| Participants | 2 |
| Messages | 8552 |
| Date range | 7/29/24, 17:20 to 7/5/26, 17:53 |
| Unicode/emoji messages | 1402 |
| Tamil script messages | 1 |
| Deleted refs | 5 |
| System messages | 2 |
| Documents (chunks) | 241 |
| Avg tokens/chunk | 433.6 |
| Embeddings | 241 |
| Embedding dimension | 1024 |
| Stored vectors | 241 |
| Queries executed | 20 |
| Successful retrievals | 20 |
| Total results returned | 100 |
| Phase 6 status | SKIPPED |
| Total time | 28m 46s |
| **Overall** | **PASS** |

### WhatsApp Chat with DATA SORCERERS.zip

| Field | Value |
|---|---|
| ZIP size | 150.0 MB |
| Collection | `nexora_val_whatsapp_chat_with_data_sorcerers` |
| Participants | 66 |
| Messages | 5728 |
| Date range | 7/29/24, 15:46 to 7/4/26, 08:23 |
| Unicode/emoji messages | 909 |
| Tamil script messages | 10 |
| Deleted refs | 314 |
| System messages | 90 |
| Documents (chunks) | 453 |
| Avg tokens/chunk | 391.0 |
| Embeddings | 453 |
| Embedding dimension | 1024 |
| Stored vectors | 453 |
| Queries executed | 20 |
| Successful retrievals | 20 |
| Total results returned | 100 |
| Phase 6 status | SKIPPED |
| Total time | 9m 22s |
| **Overall** | **PASS** |

### WhatsApp Chat with Janani.zip

| Field | Value |
|---|---|
| ZIP size | 216.8 MB |
| Collection | `nexora_val_whatsapp_chat_with_janani` |
| Participants | 2 |
| Messages | 9818 |
| Date range | 7/31/24, 14:39 to 7/5/26, 19:21 |
| Unicode/emoji messages | 1437 |
| Tamil script messages | 0 |
| Deleted refs | 4 |
| System messages | 1 |
| Documents (chunks) | 254 |
| Avg tokens/chunk | 441.6 |
| Embeddings | 254 |
| Embedding dimension | 1024 |
| Stored vectors | 254 |
| Queries executed | 20 |
| Successful retrievals | 20 |
| Total results returned | 100 |
| Phase 6 status | SKIPPED |
| Total time | 5m 22s |
| **Overall** | **PASS** |

---

### WhatsApp Chat with Dharshini ND.zip

| Field | Value |
|---|---|
| ZIP size | 283.7 MB |
| Collection | `nexora_val_whatsapp_chat_with_dharshini_nd` |
| Participants | 2 |
| Messages | 13777 |
| Date range | 3/31/24, 14:11 to 7/5/26, 17:35 |
| Unicode/emoji messages | 1398 |
| Tamil script messages | 1 |
| Deleted refs | 50 |
| System messages | 5 |
| Attachment messages | 0 |
| Documents (chunks) | 542 |
| Avg tokens/chunk | 435.4 |
| Embeddings | 542 |
| Embedding dimension | 1024 |
| Stored vectors | 542 |
| Queries executed | 20 |
| Successful retrievals | 20 |
| Total results returned | 100 |
| Phase 6 status | SKIPPED |
| Total time | 15m 5s |
| **Overall** | **PASS** |

---

## Benchmark Comparison

| Dataset | Size | Messages | Chunks | Embeddings | Retrieval | Phase 6 | Time | Status |
|---|---|---|---|---|---|---|---|---|
| WhatsApp Chat with annie.zip | 226.4 MB | 8552 | 241 | 241 | 20/20 | SKIPPED | 28m 46s | PASS |
| WhatsApp Chat with DATA SORCERERS.zip | 150.0 MB | 5728 | 453 | 453 | 20/20 | SKIPPED | 9m 22s | PASS |
| WhatsApp Chat with Janani.zip | 216.8 MB | 9818 | 254 | 254 | 20/20 | SKIPPED | 5m 22s | PASS |
| WhatsApp Chat with Dharshini ND.zip | 283.7 MB | 13777 | 542 | 542 | 20/20 | SKIPPED | 15m 5s | PASS |

---

_Nexora validation suite — all phases tested, no production code modified._
