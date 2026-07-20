"""
app/integrations/telegram/db/orm_models.py

[ADDITIVE] — SQLAlchemy ORM table definitions for Telegram persistence.

All tables are prefixed with tg_ to avoid collisions with any future
additional table sets. Every table has:
  - UUID string primary key
  - created_at / updated_at timestamps
  - Appropriate indexes for query patterns
  - Foreign keys with explicit ON DELETE behavior

Phase 2 — Migration: create_all_tables() in engine.py handles schema creation.
Down-migration SQL (run manually to revert):
  DROP TABLE IF EXISTS tg_deletion_tombstones;
  DROP TABLE IF EXISTS tg_processing_states;
  DROP TABLE IF EXISTS tg_message_chunks;
  DROP TABLE IF EXISTS tg_attachments;
  DROP TABLE IF EXISTS tg_messages;
  DROP TABLE IF EXISTS tg_chats;
  DROP TABLE IF EXISTS tg_accounts;
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# TelegramAccount
# ---------------------------------------------------------------------------

class TelegramAccountORM(Base):
    __tablename__ = "tg_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    telegram_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    authorization_status: Mapped[str] = mapped_column(String(32), nullable=False, default="disconnected")
    session_status: Mapped[str] = mapped_column(String(32), nullable=False, default="absent")
    
    # Encrypted session bundle
    session_reference_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    tdlib_database_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    tdlib_files_database_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_locator_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    telethon_session_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)


    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_last_restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    chats: Mapped[list["TelegramChatORM"]] = relationship("TelegramChatORM", back_populates="account", passive_deletes=True)

    __table_args__ = (
        UniqueConstraint("owner_id", "telegram_user_id", name="uq_tg_account_owner_user"),
        Index("ix_tg_accounts_owner_active", "owner_id", "is_active"),
    )


# ---------------------------------------------------------------------------
# TelegramChat
# ---------------------------------------------------------------------------

class TelegramChatORM(Base):
    __tablename__ = "tg_chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    telegram_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("tg_accounts.id", ondelete="RESTRICT"), nullable=False, index=True)
    telegram_chat_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chat_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    chat_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    indexing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    indexing_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_processed_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    account: Mapped["TelegramAccountORM"] = relationship(
        "TelegramAccountORM", back_populates="chats", foreign_keys="[TelegramChatORM.telegram_account_id]"
    )
    # messages relationship not defined here because TelegramMessageORM uses
    # telegram_chat_id (the Telegram string ID) rather than the DB UUID primary key.
    # Access messages via: session.query(TelegramMessageORM).filter_by(telegram_chat_id=chat.telegram_chat_id)

    __table_args__ = (
        UniqueConstraint("telegram_account_id", "telegram_chat_id", name="uq_tg_chat_account_chat"),
        Index("ix_tg_chats_owner_deleted", "owner_id", "is_deleted"),
        Index("ix_tg_chats_owner_account", "owner_id", "telegram_account_id"),
    )


# ---------------------------------------------------------------------------
# TelegramMessage
# ---------------------------------------------------------------------------

class TelegramMessageORM(Base):
    __tablename__ = "tg_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    telegram_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("tg_accounts.id", ondelete="RESTRICT"), nullable=False, index=True)
    telegram_chat_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    telegram_message_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sender_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    reply_to_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    forwarded_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Note: no direct SQLAlchemy relationship to TelegramChatORM here because
    # the FK is on telegram_account_id (→ tg_accounts), not to tg_chats.
    # Access the chat via: session.query(TelegramChatORM).filter_by(telegram_chat_id=msg.telegram_chat_id)
    attachments: Mapped[list["TelegramAttachmentORM"]] = relationship("TelegramAttachmentORM", back_populates="message", passive_deletes=True)
    chunks: Mapped[list["TelegramMessageChunkORM"]] = relationship("TelegramMessageChunkORM", back_populates="message", passive_deletes=True)
    processing_states: Mapped[list["TelegramProcessingStateORM"]] = relationship("TelegramProcessingStateORM", back_populates="message", passive_deletes=True)

    __table_args__ = (
        UniqueConstraint("telegram_account_id", "telegram_chat_id", "telegram_message_id", name="uq_tg_message_identity"),
        Index("ix_tg_messages_owner_deleted", "owner_id", "is_deleted"),
        Index("ix_tg_messages_chat_ts", "telegram_chat_id", "timestamp"),
    )


# ---------------------------------------------------------------------------
# TelegramAttachment
# ---------------------------------------------------------------------------

class TelegramAttachmentORM(Base):
    __tablename__ = "tg_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_message_record_id: Mapped[str] = mapped_column(String(36), ForeignKey("tg_messages.id", ondelete="RESTRICT"), nullable=False, index=True)
    telegram_file_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    download_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    message: Mapped["TelegramMessageORM"] = relationship("TelegramMessageORM", back_populates="attachments")

    __table_args__ = (
        UniqueConstraint("telegram_message_record_id", "telegram_file_id", name="uq_tg_attachment_msg_file"),
    )


# ---------------------------------------------------------------------------
# TelegramMessageChunk — maps message → vector IDs
# ---------------------------------------------------------------------------

class TelegramMessageChunkORM(Base):
    __tablename__ = "tg_message_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_message_record_id: Mapped[str] = mapped_column(String(36), ForeignKey("tg_messages.id", ondelete="RESTRICT"), nullable=False, index=True)
    vector_id: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    content_part: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slide_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript_segment: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    message_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    message: Mapped["TelegramMessageORM"] = relationship("TelegramMessageORM", back_populates="chunks")

    __table_args__ = (
        Index("ix_tg_chunks_msg_active", "telegram_message_record_id", "is_active"),
        Index("ix_tg_chunks_active_version", "is_active", "message_version"),
    )


# ---------------------------------------------------------------------------
# TelegramProcessingState
# ---------------------------------------------------------------------------

class TelegramProcessingStateORM(Base):
    __tablename__ = "tg_processing_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_message_record_id: Mapped[str] = mapped_column(String(36), ForeignKey("tg_messages.id", ondelete="RESTRICT"), nullable=False, index=True)
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    message: Mapped["TelegramMessageORM"] = relationship("TelegramMessageORM", back_populates="processing_states")


# ---------------------------------------------------------------------------
# TelegramDeletionTombstone — Phase 10
# ---------------------------------------------------------------------------

class TelegramDeletionTombstoneORM(Base):
    __tablename__ = "tg_deletion_tombstones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_message_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    source_update_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint(
            "source_account_id", "conversation_id", "source_message_id",
            name="uq_tg_tombstone_identity"
        ),
        Index("ix_tg_tombstone_owner", "owner_id"),
    )


# ---------------------------------------------------------------------------
# TelegramCheckpoint — Phase 3B
# ---------------------------------------------------------------------------

class TelegramCheckpointORM(Base):
    __tablename__ = "tg_checkpoints"

    # Use the Telegram user ID as the primary key/account identifier
    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_processed_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_processed_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

