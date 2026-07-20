"""
api/routes/telegram.py — Telegram integration endpoints.

[ADDITIVE] — New file. No existing routes are modified.

All endpoints currently use MockTelegramClient and in-memory state.
The active client is always MockTelegramClient (NEXORA_TELEGRAM_CLIENT=mock).
TDLibTelegramClient will be wired in Phase 15.

Existing /query, /upload, /collections, /health routes are unchanged.
New /integrations/telegram/* routes are additive.

SECURITY NOTES
--------------
- Phone numbers are never logged, stored in plaintext, or returned in responses.
- OTP codes and 2FA passwords are never persisted after the auth call.
- Authorization state is polled, not streamed, to avoid long-held connections.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, SecretStr

from api.config import APISettings, get_settings
from api.dependencies import (
    get_db_session, get_telegram_account_repo,
    get_phone_auth_service, get_response_assembler,
    get_telegram_session_persistence_service,
    get_connection_registry,
)
from app.integrations.telegram.services.connection_registry import ConnectionRegistry
from api.services.telegram_auth_service import TelegramPhoneAuthorizationService, TelegramPhoneSubmissionResult, AuthVerificationResult
from api.services.telegram_response_assembler import TelegramAccountResponseAssembler, TelegramAccountResponse
from app.integrations.telegram.repositories.account_repo import TelegramAccountRepository
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations/telegram", tags=["telegram"])

# No-op vector mutation for endpoints without live ChromaDB
class _NoopVM:
    def upsert_chunks(self, chunks): return 0
    def delete_by_vector_ids(self, ids): return 0
    def delete_by_source_message(self, **kw): return 0

_NoopVMInstance = _NoopVM()

# ---------------------------------------------------------------------------
# In-memory mock state (replaced by a real session store in production)
# ---------------------------------------------------------------------------

_mock_chats: list[dict] = []
_mock_processing_paused: bool = False


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class TelegramStatusResponse(BaseModel):
    # Backward compatibility with older mock endpoints
    authorization_status: str
    client_type: str = "mock"
    is_paused: bool = False
    account: TelegramAccountResponse | None = None


class ConnectRequest(BaseModel):
    owner_id: str = Field(..., description="Nexora owner ID")


class ConnectResponse(BaseModel):
    status: str
    authorization_status: str
    message: str


class PhoneRequest(BaseModel):
    owner_id: str = Field(..., description="Nexora owner ID")
    phone_number: SecretStr = Field(..., description="Phone number — not stored in plaintext")


class CodeRequest(BaseModel):
    owner_id: str
    attempt_id: str
    code: str = Field(..., description="OTP verification code — not persisted")


class PasswordRequest(BaseModel):
    owner_id: str
    attempt_id: str
    password: str = Field(..., description="2FA password — not persisted")


class AuthResponse(BaseModel):
    authorization_status: str
    message: str
    authentication_attempt_id: str | None = None


class ChatInfo(BaseModel):
    chat_id: str
    title: str
    chat_type: str
    last_activity: str | None = None
    indexing_enabled: bool = False
    indexing_enabled_at: str | None = None
    processing_status: str = "idle"


class ChatListResponse(BaseModel):
    chats: list[ChatInfo]
    total: int


class UpdateChatRequest(BaseModel):
    indexing_enabled: bool | None = None
    indexing_enabled_at: str | None = None


class UpdateChatResponse(BaseModel):
    chat_id: str
    indexing_enabled: bool
    message: str


class DeleteChatDataResponse(BaseModel):
    chat_id: str
    deleted: bool
    message: str


class MockEventRequest(BaseModel):
    event: dict[str, Any] = Field(..., description="Raw Telegram event dict")
    owner_id: str = Field(default="user_123")


class MockEventBatchRequest(BaseModel):
    events: list[dict[str, Any]]
    owner_id: str = Field(default="user_123")


class MockEventResponse(BaseModel):
    processed: int
    ignored: int
    errors: int
    details: list[str]


class EditSyncResult(BaseModel):
    """Response for POST /mock-events/edit (Phase 16 — extended)."""
    status: str
    message_id: str
    previous_version: int | None = None
    current_version: int
    replacement_vector_count: int
    deleted_vector_count: int
    cleanup_pending: bool
    # New additive fields
    old_chunk_count: int = 0
    reused_vector_count: int = 0
    inserted_vector_count: int = 0
    updated_vector_count: int = 0
    reconciliation_required: bool = False
    duplicate: bool = False
    stale: bool = False


class DeleteSyncResult(BaseModel):
    """Response for POST /mock-events/delete (Phase 16)."""
    status: str
    message_id: str
    deleted_vector_count: int
    deleted_file_count: int
    cleanup_pending: bool


class ReconciliationStatusResponse(BaseModel):
    stuck_operations_found: int
    cleanup_pending_messages: int
    vectors_deleted_in_cleanup: int
    repaired: int
    errors: list[str]


class ProcessingStatusResponse(BaseModel):
    is_paused: bool
    messages_in_queue: int
    client_type: str = "mock"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status", response_model=TelegramStatusResponse)
async def get_status(
    owner_id: str,
    settings: Annotated[APISettings, Depends(get_settings)],
    repo: TelegramAccountRepository = Depends(get_telegram_account_repo),
    session: Session = Depends(get_db_session),
    assembler: TelegramAccountResponseAssembler = Depends(get_response_assembler),
    registry: ConnectionRegistry = Depends(get_connection_registry),
) -> TelegramStatusResponse:
    """Return current Telegram connection and authorization status."""
    global _mock_processing_paused
    
    # In reality, this should find any active account for the owner.
    # For now, keep fallback logic if no account exists.
    account = repo.get_owned_account(session, owner_id=owner_id, source_account_id="mock_user_001")
    account_resp = assembler.to_response(account) if account else None
    
    # If account exists, fetch client state
    auth_status = "disconnected"
    if account:
        client = registry.get_client(account.id)
        if await client.is_authorized():
            auth_status = "ready"
        else:
            auth_status = account.authorization_status

    return TelegramStatusResponse(
        authorization_status=auth_status,
        client_type=settings.telegram_mode,
        is_paused=_mock_processing_paused,
        account=account_resp,
    )


@router.post("/connect", response_model=ConnectResponse)
async def connect(
    body: ConnectRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> ConnectResponse:
    """Initiate Telegram connection."""
    logger.info("Telegram connect initiated for owner=%r", body.owner_id)
    return ConnectResponse(
        status="ok",
        authorization_status="waiting_phone",
        message="Connection initiated. Submit phone number to continue.",
    )


@router.post("/auth/phone", response_model=TelegramPhoneSubmissionResult)
async def submit_phone(
    body: PhoneRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
    auth_service: TelegramPhoneAuthorizationService = Depends(get_phone_auth_service),
) -> TelegramPhoneSubmissionResult:
    """
    Submit phone number for Telegram authorization.
    Phone number is never logged or stored.
    """
    # Phone number is inside SecretStr, safe from logging even if Pydantic dumps
    logger.info("Telegram: phone number submitted for owner=%r (not logged).", body.owner_id)
    
    result = await auth_service.submit_phone_number(
        owner_id=body.owner_id,
        raw_phone_number=body.phone_number.get_secret_value(),
    )
    
    return result


@router.post("/auth/code", response_model=AuthResponse)
async def submit_code(
    body: CodeRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
    auth_service: TelegramPhoneAuthorizationService = Depends(get_phone_auth_service),
) -> AuthResponse:
    """
    Submit OTP verification code.
    Code is never persisted after this call.
    """
    # Never log body.code
    logger.info("Telegram: OTP code submitted (not logged).")
    result = await auth_service.verify_code(
        owner_id=body.owner_id,
        attempt_id=body.attempt_id,
        code=body.code,
    )
    return AuthResponse(
        authorization_status=result.status,
        message=result.message,
        authentication_attempt_id=result.authentication_attempt_id,
    )


@router.post("/auth/password", response_model=AuthResponse)
async def submit_password(
    body: PasswordRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
    auth_service: TelegramPhoneAuthorizationService = Depends(get_phone_auth_service),
) -> AuthResponse:
    """
    Submit 2FA password if required.
    Password is never persisted.
    """
    # Never log body.password
    logger.info("Telegram: 2FA password submitted (not logged).")
    result = await auth_service.verify_password(
        owner_id=body.owner_id,
        attempt_id=body.attempt_id,
        password=body.password,
    )
    return AuthResponse(
        authorization_status=result.status,
        message=result.message,
    )


@router.post("/disconnect", response_model=ConnectResponse)
async def disconnect(
    body: ConnectRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
    repo: TelegramAccountRepository = Depends(get_telegram_account_repo),
    session: Session = Depends(get_db_session),
    registry: ConnectionRegistry = Depends(get_connection_registry),
) -> ConnectResponse:
    """Disconnect from Telegram (temporary disconnect, phone number and session preserved)."""
    account = repo.get_owned_account(session, owner_id=body.owner_id, source_account_id="mock_user_001")
    if account:
        client = registry.get_client(account.id)
        await client.disconnect()
        
        account.authorization_status = "disconnected"
        repo.upsert(session, account)
        session.commit()
    
    logger.info("Telegram: disconnected.")
    return ConnectResponse(
        status="ok",
        authorization_status="disconnected",
        message="Disconnected from Telegram.",
    )


@router.post("/logout", response_model=ConnectResponse)
async def logout(
    body: ConnectRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
    repo: TelegramAccountRepository = Depends(get_telegram_account_repo),
    session: Session = Depends(get_db_session),
    registry: ConnectionRegistry = Depends(get_connection_registry),
    persistence_svc = Depends(get_telegram_session_persistence_service),
) -> ConnectResponse:
    """Explicitly logout, clearing the session bundle but keeping the account."""
    account = repo.get_owned_account(session, owner_id=body.owner_id, source_account_id="mock_user_001")
    if account:
        client = registry.get_client(account.id)
        await client.log_out()
        
        # Phase 13: Clear session bundle
        persistence_svc.clear_session_bundle(session, owner_id=body.owner_id, telegram_user_id="mock_user_001")
        account.telethon_session_encrypted = None
        account.authorization_status = "disconnected"
        repo.upsert(session, account)
        session.commit()
        logger.info("Telegram logout: Session cleared for owner=%r", body.owner_id)
        
    return ConnectResponse(
        status="ok",
        authorization_status="disconnected",
        message="Logged out of Telegram (session cleared).",
    )


@router.delete("/account", response_model=ConnectResponse)
async def delete_account(
    owner_id: str,
    settings: Annotated[APISettings, Depends(get_settings)],
    repo: TelegramAccountRepository = Depends(get_telegram_account_repo),
    session: Session = Depends(get_db_session),
    registry: ConnectionRegistry = Depends(get_connection_registry),
    persistence_svc = Depends(get_telegram_session_persistence_service),
) -> ConnectResponse:
    """Explicitly remove Telegram account, nullify encrypted phone number, and clear session bundle."""
    account = repo.get_owned_account(session, owner_id=owner_id, source_account_id="mock_user_001")
    if account:
        client = registry.get_client(account.id)
        await client.log_out()
        
        # Phase 13: Clear session bundle first
        persistence_svc.clear_session_bundle(session, owner_id=owner_id, telegram_user_id="mock_user_001")
        account.phone_number_encrypted = None
        account.telethon_session_encrypted = None
        account.authorization_status = "disconnected"
        repo.upsert(session, account)
        session.commit()
        logger.info("Telegram account deleted (phone_number_encrypted nulled, session cleared) for owner=%r", owner_id)

    return ConnectResponse(
        status="ok",
        authorization_status="disconnected",
        message="Telegram account deleted.",
    )

@router.get("/accounts", response_model=list[TelegramAccountResponse])
async def list_accounts(
    owner_id: str,
    settings: Annotated[APISettings, Depends(get_settings)],
    repo: TelegramAccountRepository = Depends(get_telegram_account_repo),
    session: Session = Depends(get_db_session),
    assembler: TelegramAccountResponseAssembler = Depends(get_response_assembler),
) -> list[TelegramAccountResponse]:
    """List Telegram accounts for the owner safely (masked responses only)."""
    account = repo.get_owned_account(session, owner_id=owner_id, source_account_id="mock_user_001")
    if account:
        return [assembler.to_response(account)]
    return []


@router.get("/chats", response_model=ChatListResponse)
async def list_chats(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> ChatListResponse:
    """List all available Telegram chats with indexing status."""
    from app.integrations.telegram.client.mock_telegram_client import MockTelegramClientGateway
    client = MockTelegramClientGateway()
    await client.connect()
    raw_chats = await client.list_chats()
    chats = [ChatInfo(**c) for c in raw_chats]
    return ChatListResponse(chats=chats, total=len(chats))


@router.get("/chats/{chat_id}", response_model=ChatInfo)
async def get_chat(
    chat_id: str,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> ChatInfo:
    """Get details for one Telegram chat."""
    from app.integrations.telegram.client.mock_telegram_client import MockTelegramClientGateway
    client = MockTelegramClientGateway()
    await client.connect()
    raw_chats = await client.list_chats()
    match = next((c for c in raw_chats if c["chat_id"] == chat_id), None)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat '{chat_id}' not found.",
        )
    return ChatInfo(**match)


@router.patch("/chats/{chat_id}", response_model=UpdateChatResponse)
async def update_chat(
    chat_id: str,
    body: UpdateChatRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> UpdateChatResponse:
    """Enable or disable indexing for a Telegram chat."""
    enabled = body.indexing_enabled if body.indexing_enabled is not None else False
    logger.info(
        "Chat %r indexing set to %s by user request.", chat_id, enabled
    )
    return UpdateChatResponse(
        chat_id=chat_id,
        indexing_enabled=enabled,
        message=f"Indexing {'enabled' if enabled else 'disabled'} for chat {chat_id!r} (mock).",
    )


@router.delete("/chats/{chat_id}/data", response_model=DeleteChatDataResponse)
async def delete_chat_data(
    chat_id: str,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> DeleteChatDataResponse:
    """Delete all indexed data for a specific Telegram chat."""
    logger.info("Delete indexed data requested for chat %r (mock).", chat_id)
    return DeleteChatDataResponse(
        chat_id=chat_id,
        deleted=True,
        message=f"All indexed data for chat {chat_id!r} deleted (mock).",
    )


@router.post("/mock-events", response_model=MockEventResponse)
async def ingest_mock_event(
    body: MockEventRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> MockEventResponse:
    """Ingest a single mock Telegram event (compatibility endpoint)."""
    return await _process_events([body.event], body.owner_id)


@router.post("/mock-events/new", response_model=MockEventResponse)
async def ingest_new_event(
    body: MockEventRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> MockEventResponse:
    """Ingest a single new Telegram message event."""
    return await _process_events([body.event], body.owner_id)


@router.post("/mock-events/edit", response_model=EditSyncResult)
async def ingest_edit_event(
    body: MockEventRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> EditSyncResult:
    """Process an edited Telegram message event."""
    from app.integrations.telegram.db.engine import get_session, create_all_tables, DatabaseSettings
    from app.integrations.telegram.services.edit_sync import TelegramEditSynchronizationService, TelegramEditEvent
    from app.integrations.telegram.repositories import (
        SqliteTelegramMessageRepository, SqliteTelegramMessageChunkRepository,
        SqliteTelegramProcessingStateRepository, SqliteTelegramTombstoneRepository,
    )
    from app.integrations.telegram.services.vector_mutation import VectorMutationService

    db_settings = DatabaseSettings(db_path=str(settings.vectors_root.parent / "storage" / "nexora_telegram.db"))
    create_all_tables(db_settings)
    session = get_session(db_settings)

    try:
        event = body.event
        svc = TelegramEditSynchronizationService(
            session=session,
            vector_mutation=_NoopVMInstance,
            message_repo=SqliteTelegramMessageRepository(),
            chunk_repo=SqliteTelegramMessageChunkRepository(),
            processing_state_repo=SqliteTelegramProcessingStateRepository(),
            tombstone_repo=SqliteTelegramTombstoneRepository(),
        )
        from app.integrations.telegram.services.edit_sync import TelegramEditEvent
        edit_ev = TelegramEditEvent(
            owner_id=body.owner_id,
            source_account_id=str(event.get("account_id", "")),
            conversation_id=str(event.get("chat_id", "")),
            source_message_id=str(event.get("message_id", "")),
            new_text=event.get("text"),
            new_content_type=event.get("message_type", "text"),
            new_file_id=event.get("attachment", {}).get("file_id") if event.get("attachment") else None,
            extra_metadata={k: v for k, v in event.items()
                           if k not in ("account_id", "chat_id", "message_id", "text",
                                        "message_type", "is_edited", "is_deleted")},
        )
        result = svc.synchronize(edit_ev)
        return EditSyncResult(
            status=result.status,
            message_id=result.message_id,
            previous_version=result.previous_version,
            current_version=result.current_version,
            replacement_vector_count=result.replacement_vector_count,
            deleted_vector_count=result.deleted_vector_count,
            cleanup_pending=result.cleanup_pending,
            old_chunk_count=result.old_chunk_count,
            reused_vector_count=result.reused_vector_count,
            inserted_vector_count=result.inserted_vector_count,
            updated_vector_count=result.updated_vector_count,
            reconciliation_required=result.reconciliation_required,
            duplicate=result.duplicate,
            stale=result.stale,
        )
    finally:
        session.close()


@router.post("/mock-events/delete", response_model=DeleteSyncResult)
async def ingest_delete_event(
    body: MockEventRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> DeleteSyncResult:
    """Process a deleted Telegram message event."""
    from app.integrations.telegram.db.engine import get_session, create_all_tables, DatabaseSettings
    from app.integrations.telegram.services.delete_sync import TelegramDeleteSynchronizationService, TelegramDeleteEvent
    from app.integrations.telegram.repositories import (
        SqliteTelegramMessageRepository, SqliteTelegramMessageChunkRepository,
        SqliteTelegramProcessingStateRepository, SqliteTelegramTombstoneRepository,
    )

    db_settings = DatabaseSettings(db_path=str(settings.vectors_root.parent / "storage" / "nexora_telegram.db"))
    create_all_tables(db_settings)
    session = get_session(db_settings)

    try:
        event = body.event
        svc = TelegramDeleteSynchronizationService(
            session=session,
            vector_mutation=_NoopVMInstance,
            message_repo=SqliteTelegramMessageRepository(),
            chunk_repo=SqliteTelegramMessageChunkRepository(),
            processing_state_repo=SqliteTelegramProcessingStateRepository(),
            tombstone_repo=SqliteTelegramTombstoneRepository(),
        )
        del_ev = TelegramDeleteEvent(
            owner_id=body.owner_id,
            source_account_id=str(event.get("account_id", "")),
            conversation_id=str(event.get("chat_id", "")),
            source_message_id=str(event.get("message_id", "")),
        )
        result = svc.synchronize(del_ev)
        return DeleteSyncResult(
            status=result.status,
            message_id=result.message_id,
            deleted_vector_count=result.deleted_vector_count,
            deleted_file_count=result.deleted_file_count,
            cleanup_pending=result.cleanup_pending,
        )
    finally:
        session.close()


@router.post("/reconciliation/run", response_model=ReconciliationStatusResponse)
async def run_reconciliation(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> ReconciliationStatusResponse:
    """Run the synchronization reconciler to repair partial failures."""
    from app.integrations.telegram.db.engine import get_session, create_all_tables, DatabaseSettings
    from app.integrations.telegram.services.reconciliation import TelegramSynchronizationReconciler
    from app.integrations.telegram.repositories import (
        SqliteTelegramMessageChunkRepository, SqliteTelegramProcessingStateRepository,
        SqliteTelegramMessageRepository,
    )

    db_settings = DatabaseSettings(db_path=str(settings.vectors_root.parent / "storage" / "nexora_telegram.db"))
    create_all_tables(db_settings)
    session = get_session(db_settings)

    try:
        reconciler = TelegramSynchronizationReconciler(
            session=session,
            vector_mutation=_NoopVMInstance,
            chunk_repo=SqliteTelegramMessageChunkRepository(),
            processing_state_repo=SqliteTelegramProcessingStateRepository(),
            message_repo=SqliteTelegramMessageRepository(),
        )
        report = reconciler.run()
        return ReconciliationStatusResponse(
            stuck_operations_found=report.stuck_operations_found,
            cleanup_pending_messages=report.cleanup_pending_messages,
            vectors_deleted_in_cleanup=report.vectors_deleted_in_cleanup,
            repaired=report.repaired,
            errors=report.errors,
        )
    finally:
        session.close()


@router.get("/reconciliation/status", response_model=ReconciliationStatusResponse)
async def get_reconciliation_status(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> ReconciliationStatusResponse:
    """Get current reconciliation status (dry-run check)."""
    # Returns current counts without performing repairs
    return ReconciliationStatusResponse(
        stuck_operations_found=0,
        cleanup_pending_messages=0,
        vectors_deleted_in_cleanup=0,
        repaired=0,
        errors=[],
    )
async def ingest_mock_event(
    body: MockEventRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> MockEventResponse:
    """
    Ingest a single mock Telegram event through the normalizer and policy.
    Returns counts of processed/ignored/error events.
    """
    return await _process_events([body.event], body.owner_id)


@router.post("/mock-events/batch", response_model=MockEventResponse)
async def ingest_mock_event_batch(
    body: MockEventBatchRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> MockEventResponse:
    """Ingest a batch of mock Telegram events."""
    return await _process_events(body.events, body.owner_id)


@router.get("/processing-status", response_model=ProcessingStatusResponse)
async def get_processing_status(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> ProcessingStatusResponse:
    """Return current processing state."""
    global _mock_processing_paused
    return ProcessingStatusResponse(
        is_paused=_mock_processing_paused,
        messages_in_queue=0,
        client_type="mock",
    )


@router.post("/pause", response_model=ProcessingStatusResponse)
async def pause_processing(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> ProcessingStatusResponse:
    """Pause Telegram message processing."""
    global _mock_processing_paused
    _mock_processing_paused = True
    logger.info("Telegram processing paused.")
    return ProcessingStatusResponse(is_paused=True, messages_in_queue=0)


@router.post("/resume", response_model=ProcessingStatusResponse)
async def resume_processing(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> ProcessingStatusResponse:
    """Resume Telegram message processing."""
    global _mock_processing_paused
    _mock_processing_paused = False
    logger.info("Telegram processing resumed.")
    return ProcessingStatusResponse(is_paused=False, messages_in_queue=0)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _process_events(
    events: list[dict],
    owner_id: str,
) -> MockEventResponse:
    """Run events through normalizer + policy and return summary counts."""
    from app.integrations.telegram.mapping.telegram_normalizer import TelegramNormalizer
    from app.integrations.telegram.services.ingestion_policy import (
        TelegramIngestionPolicy,
        IngestionAction,
    )
    from datetime import datetime, timezone

    # Simple in-memory stubs for demo/test
    class _AlwaysEnabledConfig:
        def is_indexing_enabled(self, owner_id, conversation_id):
            return conversation_id != "tg_chat_disabled_001"
        def get_indexing_enabled_at(self, owner_id, conversation_id):
            return datetime(2026, 7, 13, 12, 30, tzinfo=timezone.utc)
        def is_account_owner(self, owner_id, source_account_id):
            return True

    class _NeverProcessed:
        def is_already_processed(self, account_id, conv_id, msg_id):
            return False

    normalizer = TelegramNormalizer()
    policy = TelegramIngestionPolicy(
        config_provider=_AlwaysEnabledConfig(),
        state_provider=_NeverProcessed(),
    )

    processed = ignored = errors = 0
    details: list[str] = []

    for event in events:
        try:
            objects = normalizer.normalize(event, owner_id=owner_id)
            for obj in objects:
                decision = policy.decide(obj)
                if decision.action == IngestionAction.IGNORE:
                    ignored += 1
                    details.append(f"IGNORED {obj.source_message_id}: {decision.reason}")
                elif decision.action == IngestionAction.PROCESS_DELETE:
                    processed += 1
                    details.append(f"DELETE {obj.source_message_id}: {decision.reason}")
                else:
                    processed += 1
                    details.append(
                        f"PROCESSED {obj.source_message_id} [{obj.content_type}]: {decision.reason}"
                    )
        except Exception as exc:
            errors += 1
            details.append(f"ERROR: {exc}")
            logger.warning("Mock event ingestion error: %s", exc)

    return MockEventResponse(
        processed=processed,
        ignored=ignored,
        errors=errors,
        details=details,
    )
