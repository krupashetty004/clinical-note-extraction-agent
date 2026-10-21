"""Parsing utilities for the official ICD-10-CM code-description file."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9]{2,6}\Z")


@dataclass(frozen=True, slots=True)
class ICDCode:
    """One normalized ICD-10-CM code and its source description."""

    code: str
    description: str


def parse_icd10_code_line(
    line: str,
    *,
    line_number: int | None = None,
) -> ICDCode:
    """Parse one fixed-width code-description record.

    The source uses a seven-character code field, one separator
    character, and then the official description.

    The code and description are normalized by removing surrounding
    whitespace. The description's wording and punctuation are retained.

    Raises:
        TypeError: If line is not a string.
        ValueError: If the record does not contain a valid code and
            non-empty description.
    """
    if not isinstance(line, str):
        raise TypeError("ICD-10 record must be a string.")

    record = line.rstrip("\r\n")
    prefix = f"Line {line_number}: " if line_number else ""

    if not record.strip():
        raise ValueError(f"{prefix}blank ICD-10 record.")

    if len(record) < 9:
        raise ValueError(f"{prefix}record is shorter than expected.")

    code = record[:7].strip()
    description = record[8:].strip()

    if not _CODE_PATTERN.fullmatch(code):
        raise ValueError(f"{prefix}invalid ICD-10 code field.")

    if not description:
        raise ValueError(f"{prefix}missing ICD-10 description.")

    return ICDCode(code=code, description=description)


def iter_icd10_code_file(
    path: str | Path,
) -> Iterator[ICDCode]:
    """Stream records from a fixed-width ICD-10 code file.

    Uses UTF-8 with an optional byte-order mark. Duplicate detection
    across the entire file is intentionally handled separately.
    """
    source_path = Path(path)

    with source_path.open(
        "r",
        encoding="utf-8-sig",
        newline=None,
    ) as source:
        for line_number, line in enumerate(source, start=1):
            try:
                yield parse_icd10_code_line(
                    line,
                    line_number=line_number,
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Failed to parse ICD-10 file record "
                    f"at line {line_number}."
                ) from exc