#!/usr/bin/env python3
"""CLI utility to generate encrypted stateless webhook URLs for slack2tchap-stateless.

Usage:
    # Interactive (recommended to avoid zsh history expansion on '!'):
    uv run python scripts/generate_stateless_url.py

    # With arguments (use single quotes for Matrix room ID):
    uv run python scripts/generate_stateless_url.py \
        --username '@mon-bot:agent.tchap.gouv.fr' \
        --password 'secret_matrix_password' \
        --channel '!mon_salon:agent.tchap.gouv.fr' \
        --secret-key '<SECRET_ENCRYPTION_KEY>' \
        --base-url 'https://slack2tchap.mon-domaine.fr'
"""

import argparse
import getpass
import json
import os
import sys

from slack2tchap_core.infrastructure.security.cipher import AesGcmSecretCipher


def generate_stateless_token(
    secret_key: str,
    username: str,
    password: str,
    channel_id: str,
    homeserver: str | None = None,
) -> str:
    """Encrypt credentials and channel ID into a URL-safe AES-256-GCM token."""
    payload = {
        "username": username.strip(),
        "password": password.strip(),
        "channelID": channel_id.strip(),
    }
    if homeserver:
        payload["homeserver"] = homeserver.strip()

    cipher = AesGcmSecretCipher(secret_key)
    return cipher.encrypt_token(json.dumps(payload))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Générer une URL de webhook stateless chiffrée pour slack2tchap-stateless."
    )
    parser.add_argument(
        "--username",
        "-u",
        default=None,
        help="Matrix bot user ID (e.g. @bot:agent.tchap.gouv.fr)",
    )
    parser.add_argument(
        "--password",
        "-p",
        default=None,
        help="Matrix bot password (or access token)",
    )
    parser.add_argument(
        "--channel",
        "-c",
        default=None,
        help="Matrix Room ID (e.g. !salon:agent.tchap.gouv.fr)",
    )
    parser.add_argument(
        "--homeserver",
        "-s",
        default=None,
        help="Optional Matrix homeserver URL override",
    )
    parser.add_argument(
        "--secret-key",
        "-k",
        default=os.getenv("SECRET_ENCRYPTION_KEY"),
        help="Master encryption key (defaults to SECRET_ENCRYPTION_KEY from env)",
    )
    parser.add_argument(
        "--base-url",
        "-b",
        default=os.getenv("PUBLIC_BASE_URL", "http://localhost:8000"),
        help="Gateway base URL (defaults to PUBLIC_BASE_URL from env or http://localhost:8000)",
    )

    args = parser.parse_args()

    # Interactive prompts if not provided
    username = args.username or input("Matrix Bot User ID (@bot:agent.tchap.gouv.fr): ").strip()
    password = args.password or getpass.getpass("Matrix Bot Password: ").strip()
    channel = args.channel or input("Matrix Room ID (!salon:agent.tchap.gouv.fr): ").strip()
    secret_key = (
        args.secret_key or getpass.getpass("Master Secret Key (SECRET_ENCRYPTION_KEY): ").strip()
    )

    if not secret_key:
        print(
            "❌ Erreur : SECRET_ENCRYPTION_KEY manquante. Fournissez --secret-key ou définissez SECRET_ENCRYPTION_KEY dans l'environnement.",
            file=sys.stderr,
        )
        sys.exit(1)

    token = generate_stateless_token(
        secret_key=secret_key,
        username=username,
        password=password,
        channel_id=channel,
        homeserver=args.homeserver,
    )

    clean_base = args.base_url.rstrip("/")
    webhook_url = f"{clean_base}/slack?param={token}"

    print("\n" + "=" * 70)
    print("🔒  GÉNÉRATEUR D'URL WEBHOOK STATELESS (AES-256-GCM)")
    print("=" * 70)
    print(f"\n👤 Bot       : {username}")
    print(f"🏠 Salon     : {channel}")
    print("\n🔑 Token chiffré (param) :")
    print(f"{token}")
    print("\n" + "-" * 70)
    print("🌐  URL DE WEBHOOK PUBLIQUE COMPLÈTE (à copier dans Alertmanager/Grafana) :")
    print("-" * 70)
    print(f"\n{webhook_url}\n")
    print("-" * 70 + "\n")


if __name__ == "__main__":
    main()
