# Tasks — Telegram Multi-Chunk Edit Handling

- [x] 1. Audit existing edit flow + capture Phase-0 contract snapshot — Requirements: 10
- [x] 2. Create `edit_classifier.py` with `classify_edit()` and `EditDecision` — Requirements: 1
- [x] 3. Create `replacement_builder.py` with `PreparedVectorChunk`, `PreparedMessageReplacement`, `TelegramReplacementContentBuilder` — Requirements: 2, 3, 4
- [x] 4. Implement content-type chunk generation for all types (text, link, pdf, docx, pptx, image, voice, video) inside builder — Requirements: 3
- [x] 5. Implement vector set diffing (reused/new/stale) — Requirements: 5
- [x] 6. Extend `EditSyncResult` with new fields (additive only) — Requirements: 5, 7
- [x] 7. Refactor `TelegramEditSynchronizationService` to use classifier + builder (REFACTOR-SAFE) — Requirements: 1, 2, 5, 6, 7
- [x] 8. Implement caption-only detection and reuse logic — Requirements: 8
- [x] 9. Extend reconciliation for edit-specific partial states — Requirements: 9
- [x] 10. Add unit tests for classifier, builder, set diffing, caption-only, failure modes — Requirements: 1–8
- [x] 11. Add end-to-end integration tests (all content types + failure + reconciliation) — Requirements: 1–10
- [x] 12. Run full test suite and verify Phase-0 snapshot regression — Requirements: 10
- [x] 13. Update CHANGELOG.md and documentation — Requirements: all
