# Nexora Telegram Reconciliation

## Purpose

The `TelegramSynchronizationReconciler` detects and repairs partial failures
that leave the database and ChromaDB in an inconsistent state.

## Scenarios Handled

| Scenario | Detection | Repair |
|---|---|---|
| Processing state stuck in `processing` beyond threshold | `started_at < cutoff AND status=processing` | Mark `failed` |
| Deleted message with lingering active chunks | `is_deleted=True AND chunks.is_active=True` | Deactivate chunks, delete vectors |
| Attachment deleted but file remains | Future: add file-existence check | Delete file |

## Running Reconciliation

```bash
POST /integrations/telegram/reconciliation/run
```

Returns `ReconciliationStatusResponse` with counts of repaired items and any
errors encountered.

## Reconciliation is Idempotent

Running reconciliation twice on the same state produces the same result.
Already-repaired items are not double-processed.

## Stuck Operation Threshold

Default: 15 minutes. Configurable via `TelegramSynchronizationReconciler`
constructor parameter `stuck_threshold_minutes`.
