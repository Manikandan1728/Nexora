import re
from pathlib import Path
from typing import List
from models.attachment import Attachment
from models.message import Message


class AttachmentDetector:
    """
    Detects attachment references inside parsed messages and resolves
    them against actual media files on disk.
    """

    # WhatsApp attachment inline text patterns
    _OMITTED_PATTERN = re.compile(
        r'(?P<filetype>image|video|audio|document|sticker) omitted',
        re.IGNORECASE,
    )
    _ATTACHED_PATTERN = re.compile(r'<(?P<filename>.+?)>\s*\(file attached\)')

    def __init__(self, chat_text: str):
        self.chat_text = chat_text

    def detect_attachments(self, media_files: List[str] | None = None) -> List[Attachment]:
        """
        Scans the chat text for attachment placeholders and returns a list
        of Attachment objects.

        Args:
            media_files: Optional list of absolute file paths for known media.
                         When supplied, each attachment's `exists` flag and
                         `filepath` are resolved against this list.

        Returns:
            A list of Attachment objects (may be empty).
        """
        media_lookup: dict[str, str] = {}
        if media_files:
            for path in media_files:
                media_lookup[Path(path).name.lower()] = path

        attachments: List[Attachment] = []

        for line in self.chat_text.splitlines():
            line = line.strip()
            if not line:
                continue

            # Pattern 1: "<filename.ext> (file attached)"
            attached_match = self._ATTACHED_PATTERN.search(line)
            if attached_match:
                filename = attached_match.group('filename')
                filetype = Path(filename).suffix.lstrip('.').lower() or 'unknown'
                filepath = media_lookup.get(filename.lower(), '')
                attachments.append(Attachment(
                    filename=filename,
                    filetype=filetype,
                    filepath=filepath,
                    exists=bool(filepath),
                ))
                continue

            # Pattern 2: "<type> omitted"
            omitted_match = self._OMITTED_PATTERN.search(line)
            if omitted_match:
                filetype = omitted_match.group('filetype').lower()
                attachments.append(Attachment(
                    filename=omitted_match.group(0),
                    filetype=filetype,
                    filepath='',
                    exists=False,
                ))

        return attachments

    @staticmethod
    def attach_to_messages(
        messages: List[Message],
        media_files: List[str] | None = None,
    ) -> List[Message]:
        """
        Resolves media file paths for messages that already have an
        `attachment` field set, updating the filepath on matching Attachment
        records (convenience method for the pipeline).

        Returns the same message list (mutated in place).
        """
        if not media_files:
            return messages

        media_lookup: dict[str, str] = {
            Path(p).name.lower(): p for p in media_files
        }

        for msg in messages:
            if msg.attachment and msg.message_type == 'attachment':
                resolved = media_lookup.get(msg.attachment.lower())
                if resolved:
                    msg.attachment = resolved

        return messages
