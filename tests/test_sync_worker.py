"""
tests/test_sync_worker.py
Tests for TelegramSyncWorker.
"""
import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from app.integrations.telegram.services.sync_worker import TelegramSyncWorker

@pytest.fixture
def mock_client():
    client = AsyncMock()
    # Provide a simple update generator
    async def updates():
        yield {"account_id": "test_acc", "message_id": "msg_1", "timestamp": "2026-07-13T18:30:00+05:30"}
        yield {"account_id": "test_acc", "message_id": "msg_2", "timestamp": "2026-07-13T18:31:00+05:30"}
    client.updates = updates
    return client

@pytest.fixture
def mock_router():
    router = MagicMock()
    router.handle.return_value = MagicMock(status="processed", message_id="msg_1")
    return router

@pytest.fixture
def mock_checkpoint_repo():
    return MagicMock()

@pytest.fixture
def mock_session_factory():
    session = MagicMock()
    # mock account resolution
    account_record = MagicMock(owner_id="test_owner")
    session.query().filter_by().first.return_value = account_record
    return lambda: session

@pytest.mark.asyncio
async def test_worker_graceful_shutdown(mock_client, mock_router, mock_checkpoint_repo, mock_session_factory):
    worker = TelegramSyncWorker(mock_client, mock_router, mock_checkpoint_repo, mock_session_factory)
    
    task = asyncio.create_task(worker.start())
    # give it a moment to run and process the two updates
    await asyncio.sleep(0.1)
    await worker.stop()
    await task
    
    assert mock_router.handle.call_count == 2
    assert mock_checkpoint_repo.update_checkpoint.call_count == 2
    # Verify the first update sets msg_1
    args, kwargs = mock_checkpoint_repo.update_checkpoint.call_args_list[0]
    assert kwargs["message_id"] == "msg_1"

@pytest.mark.asyncio
async def test_worker_retry_on_exception(mock_client, mock_router, mock_checkpoint_repo, mock_session_factory):
    # Mock router to fail once then succeed
    call_count = [0]
    def failing_handle(event, owner_id):
        call_count[0] += 1
        if call_count[0] == 1:
            return MagicMock(status="error", message_id="msg_1", details={"error": "Transient failure"})
        return MagicMock(status="processed", message_id="msg_1")

    mock_router.handle = failing_handle
    worker = TelegramSyncWorker(mock_client, mock_router, mock_checkpoint_repo, mock_session_factory)
    
    # Speed up tenacity retries for the test
    from tenacity import wait_fixed
    worker._process_update_with_retry.retry.wait = wait_fixed(0.1)
    
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.5)  # wait for tenacity to retry
    await worker.stop()
    await task
    
    assert call_count[0] > 1
    assert mock_checkpoint_repo.update_checkpoint.call_count == 2 # 1 successful from msg_1 (after retry), 1 successful from msg_2
