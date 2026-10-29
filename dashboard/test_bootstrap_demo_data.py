"""Tests for safe ICD-10 demo database initialization."""

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase

from dashboard.management.commands import bootstrap_demo_data
from dashboard.models import ICDCode


class BootstrapDemoDataTests(TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.source = Path(self.temp_dir.name) / "codes.txt"

        self.records = (
            ("TST001", "Type 2 diabetes mellitus"),
            ("TST002", "Headache, unspecified"),
        )

        # The parser expects a seven-character code field, a separator,
        # and then the description.
        content = "".join(
            f"{code:<7} {description}\n"
            for code, description in self.records
        ).encode("utf-8")

        self.source.write_bytes(content)

        settings_patches = [
            patch.object(
                bootstrap_demo_data,
                "SOURCE_RELATIVE_PATH",
                self.source,
            ),
            patch.object(
                bootstrap_demo_data,
                "EXPECTED_RECORD_COUNT",
                len(self.records),
            ),
            patch.object(
                bootstrap_demo_data,
                "EXPECTED_SOURCE_SHA256",
                sha256(content).hexdigest().upper(),
            ),
        ]

        for settings_patch in settings_patches:
            settings_patch.start()
            self.addCleanup(settings_patch.stop)

    def _run_command(self):
        return call_command(
            "bootstrap_demo_data",
            stdout=StringIO(),
            stderr=StringIO(),
        )

    def _insert_reference_rows(self):
        ICDCode.objects.bulk_create(
            [
                ICDCode(code=code, description=description)
                for code, description in self.records
            ]
        )

    def test_imports_data_when_table_is_empty(self):
        self._run_command()

        self.assertEqual(ICDCode.objects.count(), 2)

        self.assertEqual(
            dict(
                ICDCode.objects.values_list("code", "description")
            ),
            dict(self.records),
        )

    def test_skips_import_when_database_matches_source(self):
        self._insert_reference_rows()

        with patch.object(
            bootstrap_demo_data,
            "call_command",
        ) as import_command:
            self._run_command()

        import_command.assert_not_called()
        self.assertEqual(ICDCode.objects.count(), 2)

    def test_refuses_partially_populated_table(self):
        ICDCode.objects.create(
            code="TST001",
            description="Type 2 diabetes mellitus",
        )

        with self.assertRaises(CommandError):
            self._run_command()

        self.assertEqual(ICDCode.objects.count(), 1)

    def test_refuses_existing_table_with_mismatched_contents(self):
        ICDCode.objects.bulk_create(
            [
                ICDCode(
                    code="TST001",
                    description="Incorrect description",
                ),
                ICDCode(
                    code="TST002",
                    description="Headache, unspecified",
                ),
            ]
        )

        with self.assertRaises(CommandError):
            self._run_command()

        self.assertEqual(ICDCode.objects.count(), 2)

    def test_refuses_source_with_wrong_checksum(self):
        with patch.object(
            bootstrap_demo_data,
            "EXPECTED_SOURCE_SHA256",
            "0" * 64,
        ):
            with self.assertRaises(CommandError):
                self._run_command()

        self.assertEqual(ICDCode.objects.count(), 0)