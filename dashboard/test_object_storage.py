"""Synthetic tests for storage configuration and smoke-check behaviour."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from config.storage import (
    LOCAL_STORAGE_BACKEND,
    NEON_STORAGE_BACKEND,
    build_default_storage_config,
    neon_object_storage_enabled,
)


VALID_ENVIRONMENT = {
    "MIRAI_ENABLE_NEON_OBJECT_STORAGE": "1",
    "NEON_STORAGE_BUCKET": "mirai-private-test",
    "AWS_ENDPOINT_URL_S3": "https://storage.example.invalid",
    "AWS_REGION": "us-east-2",
    "AWS_ACCESS_KEY_ID": "synthetic-access-key",
    "AWS_SECRET_ACCESS_KEY": "synthetic-secret-key",
}


class NeonStorageConfigurationTests(SimpleTestCase):
    def test_local_filesystem_remains_the_default(self):
        self.assertFalse(neon_object_storage_enabled({}))
        self.assertEqual(
            build_default_storage_config({}),
            {"BACKEND": LOCAL_STORAGE_BACKEND},
        )

    def test_invalid_enable_flag_fails_clearly(self):
        with self.assertRaisesRegex(RuntimeError, "must be set to 1 or 0"):
            neon_object_storage_enabled(
                {"MIRAI_ENABLE_NEON_OBJECT_STORAGE": "sometimes"}
            )

    def test_neon_storage_requires_all_credentials_and_endpoint_settings(self):
        with self.assertRaisesRegex(RuntimeError, "AWS_SECRET_ACCESS_KEY"):
            build_default_storage_config(
                {
                    "MIRAI_ENABLE_NEON_OBJECT_STORAGE": "true",
                    "NEON_STORAGE_BUCKET": "mirai-private-test",
                }
            )

    def test_neon_storage_uses_private_signed_path_style_configuration(self):
        result = build_default_storage_config(VALID_ENVIRONMENT)

        self.assertEqual(result["BACKEND"], NEON_STORAGE_BACKEND)
        options = result["OPTIONS"]
        self.assertEqual(options["bucket_name"], "mirai-private-test")
        self.assertEqual(options["addressing_style"], "path")
        self.assertEqual(options["signature_version"], "s3v4")
        self.assertIsNone(options["default_acl"])
        self.assertTrue(options["querystring_auth"])
        self.assertEqual(options["querystring_expire"], 300)
        self.assertFalse(options["file_overwrite"])
        self.assertEqual(options["endpoint_url"], "https://storage.example.invalid")

    def test_http_or_credential_bearing_endpoint_is_rejected(self):
        for endpoint in (
            "http://storage.example.invalid",
            "https://user:password@storage.example.invalid",
            "https://storage.example.invalid/path",
            "https://storage.example.invalid?token=secret",
        ):
            environment = {
                **VALID_ENVIRONMENT,
                "AWS_ENDPOINT_URL_S3": endpoint,
            }
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesRegex(RuntimeError, "HTTPS endpoint URL"):
                    build_default_storage_config(environment)


class NeonStorageSmokeCommandTests(SimpleTestCase):
    @override_settings(NEON_OBJECT_STORAGE_ENABLED=False)
    @patch("dashboard.management.commands.check_neon_storage.default_storage")
    def test_command_is_blocked_when_remote_storage_is_not_enabled(self, storage):
        with self.assertRaises(CommandError):
            call_command("check_neon_storage")
        storage.save.assert_not_called()
        storage.open.assert_not_called()

    @override_settings(NEON_OBJECT_STORAGE_ENABLED=True)
    @patch("dashboard.management.commands.check_neon_storage.default_storage")
    def test_command_uploads_reads_and_deletes_only_synthetic_content(self, storage):
        storage.save.return_value = "mirai-storage-smoke/synthetic.txt"
        storage.open.return_value = BytesIO(
            b"mirai-object-storage-smoke-test-v1"
        )
        storage.exists.return_value = False

        from io import StringIO

        output = StringIO()
        call_command("check_neon_storage", stdout=output)

        storage.save.assert_called_once()
        self.assertIn(
            b"mirai-object-storage-smoke-test-v1",
            storage.save.call_args.args[1].read(),
        )
        storage.open.assert_called_once_with(
            "mirai-storage-smoke/synthetic.txt",
            "rb",
        )
        storage.delete.assert_called_once_with(
            "mirai-storage-smoke/synthetic.txt"
        )
        storage.exists.assert_called_once_with(
            "mirai-storage-smoke/synthetic.txt"
        )
        self.assertIn("synthetic test object uploaded, read, and deleted", output.getvalue())

    @override_settings(NEON_OBJECT_STORAGE_ENABLED=True)
    @patch("dashboard.management.commands.check_neon_storage.default_storage")
    def test_command_cleans_up_after_content_mismatch(self, storage):
        storage.save.return_value = "mirai-storage-smoke/synthetic.txt"
        storage.open.return_value = BytesIO(b"unexpected synthetic content")

        with self.assertRaises(CommandError):
            call_command("check_neon_storage")

        storage.delete.assert_called_once_with(
            "mirai-storage-smoke/synthetic.txt"
        )
