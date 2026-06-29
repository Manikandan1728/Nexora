import zipfile
import os
from pathlib import Path
from exceptions.exceptions import ExtractionError


class Extractor:
    """
    Extracts ZIP contents safely while preserving folder structure.
    """

    @staticmethod
    def extract_zip(zip_path: str, extract_to: str, overwrite: bool = False) -> str:
        """
        Extracts the contents of a ZIP file to a specified directory.
        Prevents overwriting existing files unless explicitly allowed.
        Raises ExtractionError if extraction fails.
        Returns the path to the extraction directory.
        """
        try:
            extract_path = Path(extract_to)
            extract_path.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path) as zip_file:
                for member in zip_file.namelist():
                    target = extract_path / member
                    if target.exists() and not overwrite:
                        continue
                    zip_file.extract(member, extract_path)

            return str(extract_path)
        except zipfile.BadZipFile as exc:
            raise ExtractionError(f"Failed to extract '{zip_path}': {exc}") from exc
        except OSError as exc:
            raise ExtractionError(
                f"OS error while extracting '{zip_path}' to '{extract_to}': {exc}"
            ) from exc
