#!/usr/bin/env python3
"""Script autonome pour générer les clés de sécurité pour slack2tchap.

Génère :
1. SECRET_ENCRYPTION_KEY : Clé maîtresse de 256 bits (32 octets / 64 caractères hexadécimaux) pour AES-256-GCM.
2. ADMIN_API_KEY : Clé API à haute entropie avec préfixe reconnaissable pour l'administrateur initial.
"""

import secrets

from slack2tchap_core.infrastructure.security.api_key import hash_api_key


def generate_api_key(prefix: str = "s2t_live_", pepper: str | None = None) -> tuple[str, str, str]:
    """Generate a high-entropy API key, its display prefix, and its HMAC-SHA256 hash."""
    random_part = secrets.token_urlsafe(32)
    raw_key = f"{prefix}{random_part}"
    display_prefix = raw_key[:16] + "..."
    key_hash = hash_api_key(raw_key, pepper=pepper)
    return raw_key, display_prefix, key_hash


def generate_encryption_key() -> str:
    """Generate a 256-bit cryptographically secure hex key for AES-256-GCM."""
    return secrets.token_hex(32)


def main() -> None:
    enc_key = generate_encryption_key()
    raw_api_key, display_prefix, key_hash = generate_api_key(pepper=enc_key)

    print("\n" + "=" * 68)
    print("🔐  GÉNÉRATION DES CLÉS DE SÉCURITÉ POUR SLACK2TCHAP")
    print("=" * 68)

    print("\n1. Clé maîtresse de chiffrement AES-256-GCM (SECRET_ENCRYPTION_KEY)")
    print(f"   Valeur (64 caractères hex / 256 bits) : {enc_key}")

    print("\n2. Clé API Administrateur (ADMIN_API_KEY)")
    print(f"   Clé en clair     : {raw_api_key}")
    print(f"   Préfixe          : {display_prefix}")
    print(f"   Hash HMAC-SHA256 : {key_hash}")

    print("\n" + "-" * 68)
    print("📋  COPIER-COLLER DANS VOTRE FICHIER .env :")
    print("-" * 68)
    print(f"SECRET_ENCRYPTION_KEY={enc_key}")
    print("ADMIN_EMAIL=admin@tchap.gouv.fr")
    print(f"ADMIN_API_KEY={raw_api_key}")
    print("-" * 68 + "\n")


if __name__ == "__main__":
    main()
