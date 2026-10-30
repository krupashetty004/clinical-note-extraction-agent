#!/usr/bin/env python3
"""Canonical entry point for running the Clinical Note Extraction and Coding Workspace.

Starts the Django application server on host 0.0.0.0 and port 3000 (or PORT env var).
Automatically applies SQLite migrations and creates the demo doctor account.
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import execute_from_command_line


def bootstrap():
    # 1. Apply any pending database migrations
    print("Checking database migrations...")
    execute_from_command_line(["manage.py", "migrate", "--noinput"])

    # 2. Ensure default workspace roles and demo doctor account exist
    User = get_user_model()
    doctor_group, _ = Group.objects.get_or_create(name="Doctor")
    admin_group, _ = Group.objects.get_or_create(name="Admin")

    if not User.objects.filter(username="doctor").exists():
        user = User.objects.create_user(
            username="doctor",
            password="password123",
            email="doctor@mirai.internal",
            first_name="Dr.",
            last_name="Mirai",
        )
        user.is_staff = True
        user.save()
        user.groups.add(doctor_group, admin_group)
        print("Created demo account: doctor (password: password123)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Mirai Clinical Workspace Server")
    parser.add_argument("--port", type=str, default=os.environ.get("DEFAULT_APP_PORT", "3000"))
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args, _ = parser.parse_known_args()

    bootstrap()

    # Nginx listens on 8080 and proxies to 3000.
    # If port 8080 is passed, override with port 3000 to prevent port conflict.
    port = args.port
    if port == "8080":
        port = os.environ.get("DEFAULT_APP_PORT", "3000")
    host = args.host or "0.0.0.0"

    print(f"Starting server on {host}:{port}...")
    execute_from_command_line(["manage.py", "runserver", f"{host}:{port}", "--noreload"])
