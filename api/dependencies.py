"""
api/dependencies.py — FastAPI dependency providers for Phase 7.

All ``Depends(...)`` targets live here.  The app initialises expensive
resources once in ``lifespan`` and stores them in ``app.state``; these
functions retrieve them from state so routes and services never construct
new instances per-request.
"""

from __future__ import annotations

from fastapi import Request, Depends

from api.config import APISettings, get_settings


def get_api_settings(request: Request) -> APISettings:
    """
    Return the shared ``APISettings`` instance stored on ``app.state``.

    Falls back to the module-level singleton if state is not set (e.g.
    during unit tests that don't go through lifespan).

    Args:
        request: The current FastAPI ``Request`` (injected automatically).

    Returns:
        The shared ``APISettings`` singleton.
    """
    try:
        return request.app.state.settings
    except AttributeError:
        return get_settings()

def get_connection_registry(request: Request) -> 'ConnectionRegistry':
    from app.integrations.telegram.services.connection_registry import ConnectionRegistry
    try:
        return request.app.state.telegram_registry
    except AttributeError:
        # Fallback for tests/local scripts without lifespan
        return ConnectionRegistry(get_api_settings(request))


# ---------------------------------------------------------------------------
# Database and Secrets (Mission 3)
# ---------------------------------------------------------------------------

from typing import Iterator
from sqlalchemy.orm import Session
from app.integrations.telegram.db.engine import get_session as engine_get_session, DatabaseSettings

def get_db_session(
    settings: APISettings = Depends(get_api_settings),
) -> Iterator[Session]:
    """Provide a SQLAlchemy session per request."""
    # Build DB settings pointing to vectors_root parent just like in telegram.py
    db_path = str(settings.vectors_root.parent / "storage" / "nexora_telegram.db")
    db_settings = DatabaseSettings(db_path=db_path)
    session = engine_get_session(db_settings)
    try:
        yield session
    finally:
        session.close()


def get_secret_store():
    """
    Provide the application SecretStore.
    For local development/testing we use an Environment store with a static key.
    """
    import base64
    from app.security.secrets.factory import create_secret_store
    dummy_key = base64.urlsafe_b64encode(b"00000000000000000000000000000000").decode("ascii")
    return create_secret_store(provider="environment", raw_key=dummy_key, key_id="dev-key-1")


def get_phone_secret_service(
    store = Depends(get_secret_store),
):
    from app.integrations.telegram.security.phone_secret_service import TelegramPhoneSecretService
    return TelegramPhoneSecretService(secret_store=store)


def get_telegram_account_repo():
    from app.integrations.telegram.repositories.account_repo import SqliteTelegramAccountRepository
    return SqliteTelegramAccountRepository()





def get_response_assembler(
    phone_svc = Depends(get_phone_secret_service),
):
    from api.services.telegram_response_assembler import TelegramAccountResponseAssembler
    return TelegramAccountResponseAssembler(phone_secret_service=phone_svc)


def get_telegram_session_secret_service(
    store = Depends(get_secret_store),
):
    from app.integrations.telegram.security.session_secret_service import TelegramSessionSecretService
    return TelegramSessionSecretService(secret_store=store)


def get_telegram_session_persistence_service(
    secret_svc = Depends(get_telegram_session_secret_service),
    repo = Depends(get_telegram_account_repo),
):
    from app.integrations.telegram.services.session_persistence import TelegramSessionPersistenceService
    return TelegramSessionPersistenceService(secret_service=secret_svc, account_repo=repo)


def get_phone_auth_service(
    phone_svc = Depends(get_phone_secret_service),
    session_svc = Depends(get_telegram_session_secret_service),
    repo = Depends(get_telegram_account_repo),
    registry = Depends(get_connection_registry),
    session: Session = Depends(get_db_session),
):
    from api.services.telegram_auth_service import TelegramPhoneAuthorizationService
    return TelegramPhoneAuthorizationService(
        phone_secret_service=phone_svc,
        session_secret_service=session_svc,
        account_repo=repo,
        registry=registry,
        session=session,
    )
