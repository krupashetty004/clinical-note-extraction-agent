"""Security regression tests for public login and local bootstrap behavior."""
from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

import app as local_app


class PublicDemoSecurityTests(TestCase):
    def test_login_page_does_not_publish_default_demo_credentials(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        for legacy_value in (
            "mirai-doctor-2026",
            "mirai-admin-2026",
            "password123",
        ):
            with self.subTest(value=legacy_value):
                self.assertNotContains(response, legacy_value)

        self.assertContains(response, "Use your own authorized account")

    def test_local_app_bootstrap_only_runs_migrations(self):
        with patch.object(local_app, "execute_from_command_line") as execute:
            local_app.bootstrap()

        execute.assert_called_once_with(
            ["manage.py", "migrate", "--noinput"],
        )
        user_model = get_user_model()
        self.assertFalse(
            user_model.objects.filter(
                username__in={"doctor", "admin"},
            ).exists()
        )

    def test_migrations_create_correct_workspace_roles(self):
        self.assertTrue(Group.objects.filter(name="Doctor").exists())
        self.assertTrue(Group.objects.filter(name="Administrator").exists())
        self.assertFalse(Group.objects.filter(name="Admin").exists())
