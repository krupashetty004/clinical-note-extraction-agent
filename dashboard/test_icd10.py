"""Unit tests for ICD-10 fixed-width record parsing."""

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from dashboard.extraction.icd10 import (
    ICDCode,
    iter_icd10_code_file,
    parse_icd10_code_line,
)


class ICD10ParserTests(SimpleTestCase):
    def test_parses_code_and_official_description(self):
        record = (
            "A000    Cholera due to Vibrio cholerae "
            "01, biovar cholerae"
        )

        parsed = parse_icd10_code_line(record)

        self.assertEqual(
            parsed,
            ICDCode(
                code="A000",
                description=(
                    "Cholera due to Vibrio cholerae "
                    "01, biovar cholerae"
                ),
            ),
        )

    def test_parses_seven_character_code(self):
        description = "Example description"
        record = f"{'S52521A':<7} {description}"

        parsed = parse_icd10_code_line(record)

        self.assertEqual(parsed.code, "S52521A")
        self.assertEqual(parsed.description, description)

    def test_preserves_description_punctuation(self):
        description = "Example condition, unspecified."
        record = f"{'A000':<7} {description}"

        parsed = parse_icd10_code_line(record)

        self.assertEqual(parsed.description, description)

    def test_rejects_invalid_code(self):
        record = f"{'1ABC':<7} Example description"

        with self.assertRaisesRegex(ValueError, "invalid"):
            parse_icd10_code_line(record)

    def test_rejects_missing_description(self):
        # Keep the record long enough to pass the minimum-length check,
        # while leaving the description empty after whitespace stripping.
        record = f"{'A000':<7}  "

        with self.assertRaisesRegex(ValueError, "missing"):
            parse_icd10_code_line(record)

    def test_rejects_short_record(self):
        with self.assertRaisesRegex(ValueError, "shorter"):
            parse_icd10_code_line("A000")

    def test_rejects_blank_record(self):
        with self.assertRaisesRegex(ValueError, "blank"):
            parse_icd10_code_line("   ")

    def test_rejects_non_string_record(self):
        with self.assertRaises(TypeError):
            parse_icd10_code_line(None)

    def test_streams_records_from_a_file(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.txt"
            path.write_text(
                "A000    First example\n"
                "A001    Second example\n",
                encoding="utf-8",
            )

            parsed = list(iter_icd10_code_file(path))

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].code, "A000")
        self.assertEqual(parsed[1].code, "A001")

    def test_reports_line_number_for_invalid_file_record(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.txt"
            path.write_text(
                "A000    First example\n"
                "INVALID\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "line 2"):
                list(iter_icd10_code_file(path))