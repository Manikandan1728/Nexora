"""
main.py — Entry point for the AI Personal Knowledge Engine (Phase 1).

Usage:
    python main.py <input_path> [--extract-root <dir>] [--log-level <level>]

Examples:
    python main.py WhatsApp_Export.zip
    python main.py data/raw/my_chat_folder
    python main.py WhatsApp_Export.zip --extract-root data/extracted --log-level DEBUG
"""

import argparse
import logging
import sys
from pathlib import Path

from pipeline.phase1_pipeline import Phase1Pipeline
from exceptions.exceptions import (
    InvalidInputError,
    ZipValidationError,
    ExtractionError,
    DatasetValidationError,
    ParsingError,
)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _configure_logging(level_name: str) -> None:
    """Configures root logger with a consistent format."""
    numeric_level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s  %(levelname)-8s  %(name)s — %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='AI Personal Knowledge Engine — Phase 1 WhatsApp ingestion pipeline.',
    )
    parser.add_argument(
        'input_path',
        help='Path to a WhatsApp ZIP export file or an extracted export folder.',
    )
    parser.add_argument(
        '--extract-root',
        default=None,
        metavar='DIR',
        help=(
            'Directory where ZIP archives will be extracted. '
            'Defaults to data/extracted relative to the project root.'
        ),
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        metavar='LEVEL',
        help='Logging verbosity level (default: INFO).',
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """
    Execute Phase 1 pipeline.

    Returns:
        0  — success
        1  — user / input error (invalid path, bad ZIP, etc.)
        2  — pipeline / parsing error
        3  — unexpected error
    """
    args = _parse_args(argv)
    _configure_logging(args.log_level)

    logger = logging.getLogger(__name__)
    logger.info("AI Personal Knowledge Engine — Phase 1")
    logger.info("Input: %s", args.input_path)

    try:
        pipeline = Phase1Pipeline(
            input_path=args.input_path,
            extract_root=args.extract_root,
        )
        chat = pipeline.run()

        # ── Success summary ──────────────────────────────────────────
        print("\n✓  Phase 1 complete")
        print(f"   Participants  : {', '.join(chat.participants)}")
        print(f"   Messages      : {chat.metadata.total_messages}")
        print(f"   Attachments   : {chat.metadata.attachment_count}")
        print(f"   Date range    : {chat.metadata.chat_start_date}  →  {chat.metadata.chat_end_date}")
        return 0

    except (InvalidInputError, ZipValidationError) as exc:
        logger.error("Input error: %s", exc)
        print(f"\n✗  Input error: {exc}", file=sys.stderr)
        return 1

    except (ExtractionError, DatasetValidationError) as exc:
        logger.error("Pipeline error: %s", exc)
        print(f"\n✗  Pipeline error: {exc}", file=sys.stderr)
        return 1

    except ParsingError as exc:
        logger.error("Parsing error: %s", exc)
        print(f"\n✗  Parsing error: {exc}", file=sys.stderr)
        return 2

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error: %s", exc)
        print(f"\n✗  Unexpected error: {exc}", file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
