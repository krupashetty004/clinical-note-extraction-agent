"""Read-only validation of the official ICD-10-CM reference file."""

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.extraction.icd10 import iter_icd10_code_file


def validate_reference_file(path: Path) -> int:
    """Validate records and uniqueness without writing any files."""
    if not path.is_file():
        print(f"Error: reference file not found: {path}", file=sys.stderr)
        return 1

    total_records = 0
    seen_codes: set[str] = set()
    duplicate_codes: set[str] = set()
    first_code: str | None = None
    last_code: str | None = None

    try:
        for record in iter_icd10_code_file(path):
            total_records += 1

            if first_code is None:
                first_code = record.code

            last_code = record.code

            if record.code in seen_codes:
                duplicate_codes.add(record.code)
            else:
                seen_codes.add(record.code)

    except (OSError, UnicodeError, ValueError) as exc:
        print(
            f"Validation failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"File: {path.name}")
    print(f"Records parsed: {total_records}")
    print(f"Unique codes: {len(seen_codes)}")
    print(f"Duplicate codes: {len(duplicate_codes)}")
    print(f"First code: {first_code}")
    print(f"Last code: {last_code}")

    if not total_records:
        print("Validation failed: the file contains no records.")
        return 1

    if duplicate_codes:
        print(
            "Duplicate code samples: "
            + ", ".join(sorted(duplicate_codes)[:10])
        )
        print("Validation failed: duplicate codes were found.")
        return 1

    if total_records != len(seen_codes):
        print("Validation failed: record counts do not match.")
        return 1

    print("Validation result: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an ICD-10-CM code-description file."
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Path to the official fixed-width code-description file.",
    )
    args = parser.parse_args()

    return validate_reference_file(args.source)


if __name__ == "__main__":
    raise SystemExit(main())