import os
from pathlib import Path
from exceptions.exceptions import ParsingError


class FileUtils:
    """
    Utility functions for file operations.
    """

    @staticmethod
    def ensure_directory_exists(directory: str) -> None:
        """
        Ensures that a directory exists, creating it if necessary.
        """
        Path(directory).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def get_file_extension(file_path: str) -> str:
        """
        Returns the file extension for a given file path (including the dot).
        """
        return Path(file_path).suffix

    @staticmethod
    def read_file(file_path: str, encoding: str = 'utf-8') -> str:
        """
        Reads a text file and returns its contents as a string.
        Falls back to 'latin-1' encoding if UTF-8 decoding fails.
        Raises ParsingError if the file cannot be read.
        """
        path = Path(file_path)
        if not path.exists():
            raise ParsingError(f"File not found: '{file_path}'")
        if not path.is_file():
            raise ParsingError(f"Path is not a file: '{file_path}'")

        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            # Some exported chat files on Windows may use latin-1 encoding
            try:
                return path.read_text(encoding='latin-1')
            except Exception as exc:
                raise ParsingError(
                    f"Unable to read file '{file_path}': {exc}"
                ) from exc
        except OSError as exc:
            raise ParsingError(f"Unable to read file '{file_path}': {exc}") from exc
