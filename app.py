#!/usr/bin/env python3
"""Local convenience entry point for the Django Clinical Workspace.

This script may apply migrations before starting the development server.
It never creates users, assigns privileged roles, or provisions passwords.
Create accounts explicitly with Django's createsuperuser command.
"""
import argparse
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.core.management import execute_from_command_line


def bootstrap() -> None:
    """Apply pending migrations without creating any default accounts."""
    print("Checking database migrations...")
    execute_from_command_line(["manage.py", "migrate", "--noinput"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Mirai Clinical Workspace development server",
    )
    parser.add_argument(
        "--port",
        type=str,
        default=os.environ.get("DEFAULT_APP_PORT", "3000"),
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
    )
    args = parser.parse_args()

    bootstrap()

    print(f"Starting local development server on {args.host}:{args.port}...")
    execute_from_command_line(
        ["manage.py", "runserver", f"{args.host}:{args.port}", "--noreload"]
    )
