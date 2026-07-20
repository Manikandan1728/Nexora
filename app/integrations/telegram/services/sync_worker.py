"""
app/integrations/telegram/services/sync_worker.py
[ADDITIVE] Background worker for processing live Telegram updates.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Callable, Optional
from datetime import datetime
import dateutil.parser

from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.integrations.telegram.client.base_telegram_client import TelegramClient
from app.integrations.telegram.updates.update_router import TelegramUpdateRouter
from app.integrations.telegram.repositories.checkpoint_repo import TelegramCheckpointRepository
from app.integrations.telegram.db.orm_models import TelegramAccountORM

logger = logging.getLogger(__name__)


class TelegramSyncWorker:
    """
    Background worker that connects to a TelegramClient, continuously consumes updates,
    routes them via TelegramUpdateRouter, and maintains a persistence checkpoint.
    """

    def __init__(
        self,
        client: TelegramClient,
        router: TelegramUpdateRouter,
        checkpoint_repo: TelegramCheckpointRepository,
        session_factory: Callable[[], Session],
    ) -> None:
        self._client = client
        self._router = router
        self._checkpoint_repo = checkpoint_repo
        self._session_factory = session_factory
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the synchronization loop in the background."""
        if self._running:
            return
        self._running = True
        logger.info("TelegramSyncWorker: starting.")
        # Start in current task if awaited, or we can just run the loop
        while self._running:
            try:
                await self._client.connect()
                logger.info("TelegramSyncWorker: Connected to Telegram. Streaming updates...")
                async for event in self._client.updates():
                    if not self._running:
                        break
                    await self._process_update_with_retry(event)
                
                # If the updates stream completes (e.g. Mock client finishes), 
                # sleep to prevent a tight infinite loop. A real client should block forever.
                if self._running:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("TelegramSyncWorker: task cancelled.")
                break
            except Exception as exc:
                logger.warning("TelegramSyncWorker: Connection lost or fatal error: %s. Reconnecting in 5s...", exc)
                if self._running:
                    await asyncio.sleep(5)

        logger.info("TelegramSyncWorker: stopping.")
        await self._client.disconnect()

    async def stop(self) -> None:
        """Gracefully stop the synchronization loop."""
        logger.info("TelegramSyncWorker: shutting down gracefully.")
        self._running = False

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def _process_update_with_retry(self, event: dict) -> None:
        """Process an update with exponential backoff for transient failures."""
        # Use a blocking wrapper inside an executor since router is synchronous
        await asyncio.to_thread(self._process_update, event)

    def _process_update(self, event: dict) -> None:
        """Synchronously route the event and update the checkpoint."""
        account_id = event.get("account_id")
        if not account_id:
            logger.debug("TelegramSyncWorker: Skipping event with no account_id")
            return

        session = self._session_factory()
        try:
            # 1. Resolve owner_id
            account_record = (
                session.query(TelegramAccountORM)
                .filter_by(telegram_user_id=account_id)
                .first()
            )
            # If we can't map the account, we skip or use a dummy owner for mock testing
            owner_id = account_record.owner_id if account_record else "default_owner"

            # 2. Route the update
            result = self._router.handle(event, owner_id)
            if result.status == "error":
                logger.error(
                    "TelegramSyncWorker: Update processing error msg_id=%s: %s",
                    result.message_id,
                    result.details.get("error")
                )
                # If we raise an Exception here, tenacity will retry it.
                # However, since the router catches most exceptions and returns status="error",
                # if we want to retry transient failures, the router shouldn't mask them, or
                # we should raise an error if it's transient. 
                # For now, we trust the router. If it's a permanent error, we just continue.
                # If we want to retry, we can raise a RuntimeError.
                # Since the router intercepts all exceptions and returns "error", we can raise here to trigger retry.
                # In a robust system, we would distinguish transient vs permanent. We'll retry 5 times then move on.
                raise RuntimeError(f"Update failed: {result.details.get('error')}")

            # 3. Checkpoint
            msg_id = result.message_id or event.get("message_id")
            timestamp_str = event.get("timestamp")
            dt = None
            if timestamp_str:
                try:
                    dt = dateutil.parser.isoparse(timestamp_str)
                except Exception:
                    pass

            self._checkpoint_repo.update_checkpoint(
                session=session,
                account_id=account_id,
                timestamp=dt,
                message_id=str(msg_id) if msg_id else None,
            )
            session.commit()

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
