"""
app/integrations/telegram/models/telegram_models.py

[ADDITIVE] — New file. No existing code is modified.

Operational database models for Telegram integration.
These are Pydantic models used as in-memory representations;
SQLAlchemy ORM mappings live in app/integrations/telegram/repositories/.

All models use string IDs (not integers) for Telegram identifiers because
Telegram IDs can exceed int32 range and are treated as opaque strings
throughout the application. Phone numbers are stored encrypted; they are
never stored in plaintext.

Uniqueness constraints (enforced at DB level, documented here):
- TelegramAccount: unique on (owner_id, telegram_user_id)
- TelegramChat:    unique on (owner_id, telegram_account_id, telegram_chat_id)
- TelegramMessage: unique on (telegram_account_id, telegram_chat_id, telegram_message_id)
- TelegramAttachment: unique on (telegram_message_record_id, telegram_file_id)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AuthorizationStatus(str, Enum):
    """Current authorization state for a Telegram account."""
    DISCONNECTED = "disconnected"
    WAITING_PHONE = "waiting_phone"
    WAITING_CODE = "waiting_code"
    WAITING_PASSWORD = "waiting_password"
    READY = "ready"
    CLOSED = "closed"
    ERROR = "error"


class ChatType(str, Enum):
    """Telegram chat type."""
    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"
    BOT = "bot"
    UNKNOWN = "unknown"


class MessageType(str, Enum):
    """Telegram message content type."""
    TEXT = "text"
    LINK = "link"
    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE = "voice"
    DOCUMENT = "document"
    STICKER = "sticker"
    ANIMATION = "animation"
    VIDEO_NOTE = "video_note"
    CONTACT = "contact"
    LOCATION = "location"
    POLL = "poll"
    FORWARDED = "forwarded"
    REPLY = "reply"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class DownloadStatus(str, Enum):
    """Download state for a Telegram file attachment."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ProcessingStatus(str, Enum):
    """Processing state for a message or attachment."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    DELETED = "deleted"


# ---------------------------------------------------------------------------
# TelegramAccount
# ---------------------------------------------------------------------------

class TelegramAccount(BaseModel):
    """
    Represents a Telegram account connected to Nexora by a specific owner.

    Security notes:
    - phone_number_encrypted stores the phone number encrypted at rest.
      Never store plaintext phone numbers.
    - session_reference is an opaque reference to the TDLib session storage.
      It must never contain OTP codes or 2FA passwords.
    - No OTP codes or 2FA passwords are ever persisted in any field.

    Unique constraint: (owner_id, telegram_user_id)
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str
    telegram_user_id: str           # Stable Telegram user ID (opaque string)
    display_name: Optional[str] = None
    username: Optional[str] = None  # @username without @
    phone_number_encrypted: Optional[str] = None  # Encrypted; never plaintext
    authorization_status: AuthorizationStatus = AuthorizationStatus.DISCONNECTED
    session_status: str = "absent"

    # Encrypted session bundle
    session_reference_encrypted: Optional[str] = None
    tdlib_database_key_encrypted: Optional[str] = None
    tdlib_files_database_key_encrypted: Optional[str] = None
    session_locator_encrypted: Optional[str] = None

    connected_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    session_created_at: Optional[datetime] = None
    session_updated_at: Optional[datetime] = None
    session_last_restored_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# TelegramChat
# ---------------------------------------------------------------------------

class TelegramChat(BaseModel):
    """
    Represents a Telegram chat that may be indexed by Nexora.

    Indexing is opt-in per chat. Only chats with indexing_enabled=True
    and a message timestamp >= indexing_enabled_at are processed.

    last_processed_message_id is a stable cursor — used for idempotency
    and to resume processing after restarts without relying solely on
    timestamps (which can be imprecise across time zones).

    Unique constraint: (owner_id, telegram_account_id, telegram_chat_id)
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str
    telegram_account_id: str        # FK → TelegramAccount.id
    telegram_chat_id: str           # Stable Telegram chat ID
    chat_title: Optional[str] = None
    chat_type: ChatType = ChatType.UNKNOWN
    indexing_enabled: bool = False
    indexing_enabled_at: Optional[datetime] = None
    last_processed_message_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# TelegramUser
# ---------------------------------------------------------------------------

class TelegramUser(BaseModel):
    """
    A Telegram user observed in indexed chats.

    Separate from TelegramAccount — a TelegramUser is any participant in
    an observed conversation, not necessarily the account owner.

    sender_id (telegram_user_id) is the stable retrieval key.
    display_name is for UI display only and must not be used as a filter.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str
    telegram_account_id: str
    telegram_user_id: str           # Stable Telegram user ID
    display_name: Optional[str] = None
    username: Optional[str] = None
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# TelegramMessage
# ---------------------------------------------------------------------------

class TelegramMessage(BaseModel):
    """
    A single Telegram message record in the operational database.

    This is the source-of-truth record for a message as received from
    Telegram. It tracks edit/delete lifecycle and processing status.

    Unique constraint: (telegram_account_id, telegram_chat_id, telegram_message_id)

    Edit handling: when is_edited=True, the old indexed chunks are
    deactivated and new chunks are generated from raw_text.

    Delete handling: when is_deleted=True, indexed chunks are removed and
    the message is no longer retrievable.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str
    telegram_account_id: str
    telegram_chat_id: str
    telegram_message_id: str        # Stable Telegram message ID
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None  # Display only; not used for retrieval
    message_type: MessageType = MessageType.TEXT
    raw_text: Optional[str] = None
    timestamp: Optional[datetime] = None
    reply_to_message_id: Optional[str] = None
    forwarded_from: Optional[str] = None
    is_edited: bool = False
    is_deleted: bool = False
    edit_count: int = 0
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    processing_error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# TelegramAttachment
# ---------------------------------------------------------------------------

class TelegramAttachment(BaseModel):
    """
    A file attachment associated with a TelegramMessage.

    Downloads are tracked separately from message processing — a message
    may be recorded before its attachment is downloaded.

    checksum (SHA-256) is generated after download for integrity verification
    and deduplication of identical files.

    Unique constraint: (telegram_message_record_id, telegram_file_id)
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    telegram_message_record_id: str  # FK → TelegramMessage.id
    telegram_file_id: str            # Stable Telegram file ID
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None  # bytes
    local_path: Optional[str] = None # Relative to media root; never absolute
    download_status: DownloadStatus = DownloadStatus.PENDING
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    checksum: Optional[str] = None   # SHA-256 hex after download
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# TelegramIndexingPreference
# ---------------------------------------------------------------------------

class TelegramIndexingPreference(BaseModel):
    """
    Per-chat indexing preferences set by the owner.

    Separating preferences from TelegramChat allows the preference
    schema to evolve independently. Future fields: include_media,
    include_voice, max_message_age_days, etc.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str
    telegram_chat_id: str
    indexing_enabled: bool = False
    indexing_enabled_at: Optional[datetime] = None
    index_text: bool = True
    index_images: bool = False
    index_voice: bool = False
    index_documents: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# TelegramProcessingState
# ---------------------------------------------------------------------------

class TelegramProcessingState(BaseModel):
    """
    Tracks the overall processing state for a Telegram account/chat pair.

    Used by the ingestion policy to decide whether processing is active,
    paused, or needs recovery.

    is_paused: set True by the user or by error recovery logic.
    error_message: last error encountered, if any.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str
    telegram_account_id: str
    telegram_chat_id: Optional[str] = None  # None = account-level state
    is_paused: bool = False
    messages_processed: int = 0
    messages_failed: int = 0
    last_processed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
