"""
Tests for the Phase 1 pipeline.

The test suite uses only in-memory / tmp-directory fixtures — no real
WhatsApp exports are required.  Every test is fully self-contained.
"""

import os
import zipfile
import pytest
from pathlib import Path

from pipeline.phase1_pipeline import Phase1Pipeline
from exceptions.exceptions import (
    InvalidInputError,
    ZipValidationError,
    DatasetValidationError,
    ParsingError,
)


# ---------------------------------------------------------------------------
# Helpers / shared sample data
# ---------------------------------------------------------------------------

SAMPLE_CHAT = (
    "1/1/2024, 9:00 AM - Alice: Hello!\n"
    "1/1/2024, 9:01 AM - Bob: Hi there!\n"
    "1/1/2024, 9:02 AM - Alice: How are you?\n"
    "1/1/2024, 9:03 AM - Bob: image omitted\n"
    "1/2/2024, 10:00 AM - Alice: Goodbye!\n"
)


def _make_chat_folder(tmp_path: Path, chat_text: str = SAMPLE_CHAT) -> Path:
    """Creates a minimal WhatsApp export folder in *tmp_path*."""
    folder = tmp_path / "whatsapp_export"
    folder.mkdir()
    (folder / "WhatsApp Chat.txt").write_text(chat_text, encoding="utf-8")
    return folder


def _make_chat_zip(tmp_path: Path, chat_text: str = SAMPLE_CHAT) -> Path:
    """Creates a valid WhatsApp export ZIP in *tmp_path*."""
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("WhatsApp Chat.txt", chat_text)
    return zip_path


# ---------------------------------------------------------------------------
# Input detection tests
# ---------------------------------------------------------------------------

class TestInputDetection:
    def test_invalid_path_raises_invalid_input_error(self, tmp_path):
        with pytest.raises(InvalidInputError):
            Phase1Pipeline(str(tmp_path / "nonexistent")).run()

    def test_non_zip_file_raises_invalid_input_error(self, tmp_path):
        bad_file = tmp_path / "chat.txt"
        bad_file.write_text("not a zip")
        with pytest.raises(InvalidInputError):
            Phase1Pipeline(str(bad_file)).run()


# ---------------------------------------------------------------------------
# ZIP validation tests
# ---------------------------------------------------------------------------

class TestZipValidation:
    def test_corrupted_zip_raises_zip_validation_error(self, tmp_path):
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_bytes(b"this is not a zip file at all")
        with pytest.raises(ZipValidationError):
            Phase1Pipeline(str(bad_zip)).run()

    def test_empty_zip_raises_zip_validation_error(self, tmp_path):
        empty_zip = tmp_path / "empty.zip"
        with zipfile.ZipFile(empty_zip, "w"):
            pass  # creates a ZIP with no entries
        with pytest.raises(ZipValidationError):
            Phase1Pipeline(str(empty_zip)).run()

    def test_valid_zip_runs_successfully(self, tmp_path):
        zip_path = _make_chat_zip(tmp_path)
        pipeline = Phase1Pipeline(
            str(zip_path),
            extract_root=str(tmp_path / "extracted"),
        )
        chat = pipeline.run()
        assert chat is not None


# ---------------------------------------------------------------------------
# Folder input tests
# ---------------------------------------------------------------------------

class TestFolderInput:
    def test_folder_without_txt_raises_dataset_validation_error(self, tmp_path):
        empty_folder = tmp_path / "empty_export"
        empty_folder.mkdir()
        with pytest.raises(DatasetValidationError):
            Phase1Pipeline(str(empty_folder)).run()

    def test_valid_folder_runs_successfully(self, tmp_path):
        folder = _make_chat_folder(tmp_path)
        chat = Phase1Pipeline(str(folder)).run()
        assert chat is not None


# ---------------------------------------------------------------------------
# Chat object content tests
# ---------------------------------------------------------------------------

class TestChatObject:
    def test_participants_extracted(self, tmp_path):
        folder = _make_chat_folder(tmp_path)
        chat = Phase1Pipeline(str(folder)).run()
        assert set(chat.participants) == {"Alice", "Bob"}

    def test_message_count(self, tmp_path):
        folder = _make_chat_folder(tmp_path)
        chat = Phase1Pipeline(str(folder)).run()
        assert chat.metadata.total_messages == 5

    def test_attachment_count(self, tmp_path):
        folder = _make_chat_folder(tmp_path)
        chat = Phase1Pipeline(str(folder)).run()
        assert chat.metadata.attachment_count == 1

    def test_date_range(self, tmp_path):
        folder = _make_chat_folder(tmp_path)
        chat = Phase1Pipeline(str(folder)).run()
        assert "2024" in chat.metadata.chat_start_date
        assert "2024" in chat.metadata.chat_end_date

    def test_messages_list_populated(self, tmp_path):
        folder = _make_chat_folder(tmp_path)
        chat = Phase1Pipeline(str(folder)).run()
        assert len(chat.messages) > 0

    def test_message_has_required_fields(self, tmp_path):
        folder = _make_chat_folder(tmp_path)
        chat = Phase1Pipeline(str(folder)).run()
        msg = chat.messages[0]
        assert msg.id is not None
        assert msg.timestamp
        assert msg.sender
        assert msg.message is not None
        assert msg.message_type in ('text', 'attachment')

    def test_metadata_object_type(self, tmp_path):
        from models.metadata import ChatMetadata
        folder = _make_chat_folder(tmp_path)
        chat = Phase1Pipeline(str(folder)).run()
        assert isinstance(chat.metadata, ChatMetadata)


# ---------------------------------------------------------------------------
# Parsing edge-case tests
# ---------------------------------------------------------------------------

class TestParsing:
    def test_multiline_messages(self, tmp_path):
        chat_text = (
            "1/1/2024, 9:00 AM - Alice: Line one\n"
            "continuation of line one\n"
            "1/1/2024, 9:01 AM - Bob: Second message\n"
        )
        folder = _make_chat_folder(tmp_path, chat_text)
        chat = Phase1Pipeline(str(folder)).run()
        assert len(chat.messages) == 2
        assert "continuation" in chat.messages[0].message

    def test_attachment_message_type(self, tmp_path):
        chat_text = (
            "1/1/2024, 9:00 AM - Alice: image omitted\n"
            "1/1/2024, 9:01 AM - Bob: Hey\n"
        )
        folder = _make_chat_folder(tmp_path, chat_text)
        chat = Phase1Pipeline(str(folder)).run()
        attachment_msgs = [m for m in chat.messages if m.message_type == 'attachment']
        assert len(attachment_msgs) == 1
