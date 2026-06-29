import logging
import os
from pathlib import Path
from typing import Optional

from app.input_detector import InputDetector
from app.zip_validator import ZipValidator
from app.extractor import Extractor
from app.dataset_validator import DatasetValidator
from parser.chat_parser import ChatParser
from parser.attachment_detector import AttachmentDetector
from parser.metadata_parser import MetadataParser
from models.chat import Chat
from utils.file_utils import FileUtils

logger = logging.getLogger(__name__)


class Phase1Pipeline:
    """
    Orchestrates the complete Phase 1 ingestion workflow:

        User Input
          → Input Detection
          → ZIP Validation  (if ZIP)
          → ZIP Extraction  (if ZIP)
          → Dataset Validation
          → Locate Chat File
          → Locate Media Files
          → Chat Parsing
          → Attachment Detection
          → Metadata Extraction
          → Chat Object
    """

    def __init__(self, input_path: str, extract_root: Optional[str] = None):
        """
        Args:
            input_path:   Path to a WhatsApp ZIP export or extracted folder.
            extract_root: Directory where ZIP contents will be extracted.
                          Defaults to 'data/extracted' relative to the project root.
        """
        self.input_path = input_path
        self.extract_root = extract_root or str(
            Path(__file__).resolve().parent.parent / 'data' / 'extracted'
        )
        self.chat: Optional[Chat] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> Chat:
        """
        Executes the entire Phase 1 ingestion pipeline.

        Returns:
            A fully populated Chat object.

        Raises:
            InvalidInputError        – bad / non-existent input path
            ZipValidationError       – corrupted / empty ZIP
            ExtractionError          – ZIP extraction failure
            DatasetValidationError   – not a valid WhatsApp export folder
            ParsingError             – chat text unreadable or unparseable
        """
        logger.info("Phase 1 pipeline starting.  Input: %s", self.input_path)

        # ── Step 1: Detect input type ────────────────────────────────
        input_type = InputDetector.detect_input_type(self.input_path)
        logger.info("Input type detected: %s", input_type)

        # ── Step 2 & 3: Validate + extract ZIP (if needed) ──────────
        if input_type == 'ZIP':
            ZipValidator.validate_zip(self.input_path)
            logger.info("ZIP validation passed.")

            # Derive a stable sub-folder name from the ZIP stem
            zip_stem = Path(self.input_path).stem
            extract_path = str(Path(self.extract_root) / zip_stem)
            FileUtils.ensure_directory_exists(extract_path)

            working_dir = Extractor.extract_zip(self.input_path, extract_path)
            logger.info("ZIP extracted to: %s", working_dir)
        else:
            working_dir = self.input_path

        # ── Step 4: Validate dataset structure ───────────────────────
        dataset_summary = DatasetValidator.validate_dataset(working_dir)
        chat_file_path = dataset_summary['chat_file']
        media_files = dataset_summary['media_files']
        logger.info(
            "Dataset validated.  Chat file: %s  Media files: %d",
            chat_file_path,
            len(media_files),
        )

        # ── Step 5: Read chat text ────────────────────────────────────
        chat_text = FileUtils.read_file(chat_file_path)
        logger.info("Chat file read (%d characters).", len(chat_text))

        # ── Step 6: Parse messages ────────────────────────────────────
        messages = ChatParser(chat_text).parse_messages()
        logger.info("Parsed %d messages.", len(messages))

        # ── Step 7: Detect attachments ────────────────────────────────
        attachments = AttachmentDetector(chat_text).detect_attachments(
            media_files=media_files
        )
        logger.info("Detected %d attachment references.", len(attachments))

        # ── Step 8: Extract metadata ──────────────────────────────────
        metadata = MetadataParser(messages).parse_metadata()
        logger.info(
            "Metadata extracted.  Participants: %s  Messages: %d",
            metadata.participants,
            metadata.total_messages,
        )

        # ── Step 9: Build Chat object ─────────────────────────────────
        self.chat = Chat(
            participants=metadata.participants,
            messages=messages,
            metadata=metadata,
        )

        logger.info("Phase 1 pipeline completed successfully.")
        return self.chat
