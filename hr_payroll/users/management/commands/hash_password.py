from __future__ import annotations

import getpass

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.core.management.base import CommandParser


class Command(BaseCommand):
    help = "Generate a Django-compatible password hash and print it"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--password",
            dest="password",
            help="Plain-text password to hash (omit to be prompted securely)",
        )
        parser.add_argument(
            "--hasher",
            dest="hasher",
            choices=[
                "default",
                "argon2",
                "pbkdf2_sha256",
                "pbkdf2_sha1",
                "bcrypt_sha256",
            ],
            default="default",
            help=(
                "Which hasher to use. "
                "'default' uses the first entry in PASSWORD_HASHERS. "
                "Common options: 'argon2', 'pbkdf2_sha256'."
            ),
        )

    def handle(self, *args, **options) -> str | None:
        pwd: str | None = options.get("password")
        hasher: str = options.get("hasher") or "default"

        if not pwd:
            pwd = getpass.getpass("Password: ")
            confirm = getpass.getpass("Confirm:  ")
            if pwd != confirm:
                self.stderr.write(self.style.ERROR("Passwords do not match."))
                return None

        # Use default hasher when 'default' selected; else use chosen algorithm
        if hasher == "default":
            hashed = make_password(pwd)
        else:
            hashed = make_password(pwd, hasher=hasher)
        # Print the hash only
        self.stdout.write(hashed)
        return None
