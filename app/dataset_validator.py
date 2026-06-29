import os
from pathlib import Path
from exceptions.exceptions import DatasetValidationError


class DatasetValidator:
    """
    Validates the dataset structure of a WhatsApp export.
    """

    @staticmethod
    def validate_dataset(folder_path: str) -> dict:
        """
        Verifies that the folder represents a WhatsApp export,
        locates the exported chat text file, and detects media files.
        Returns a dataset summary dict with keys 'chat_file' and 'media_files'.
        Raises DatasetValidationError for invalid or incomplete exports.
        """
        folder = Path(folder_path)

        if not folder.exists() or not folder.is_dir():
            raise DatasetValidationError(f"'{folder_path}' is not a valid directory.")

        # WhatsApp exports always contain a single .txt chat file at the root
        txt_files = list(folder.glob('*.txt'))
        if not txt_files:
            raise DatasetValidationError(
                f"No chat text file found in '{folder_path}'. "
                "Expected a WhatsApp export with a .txt file."
            )

        chat_file = txt_files[0]

        # Media files may live directly in the folder or in a 'media' subfolder
        media_files: list[Path] = []
        media_subdir = folder / 'media'
        if media_subdir.is_dir():
            media_files.extend(media_subdir.iterdir())

        # Also collect media files that sit directly in the root (common in some exports)
        direct_media_extensions = {
            '.jpg', '.jpeg', '.png', '.gif', '.webp',
            '.mp4', '.mkv', '.mov', '.avi',
            '.mp3', '.ogg', '.aac', '.m4a', '.opus',
            '.pdf', '.docx', '.xlsx', '.pptx',
        }
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() in direct_media_extensions:
                media_files.append(f)

        return {
            'chat_file': str(chat_file),
            'media_files': [str(m) for m in media_files],
        }
