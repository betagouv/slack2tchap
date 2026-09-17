"""Command-line utility and binary entrypoint for slack2tchap-core."""

import argparse
import getpass
import json
import os
import sys

from slack2tchap_core import __version__
from slack2tchap_core.infrastructure.parsers.slack_parser import SlackPayloadParser
from slack2tchap_core.infrastructure.security.api_key import hash_api_key
from slack2tchap_core.infrastructure.security.cipher import AesGcmSecretCipher


def cmd_encrypt_token(args: argparse.Namespace) -> None:
    """Encrypt credentials and channel ID into a URL-safe token."""
    username = args.username or input("Matrix Bot User ID (@bot:agent.tchap.gouv.fr): ").strip()
    password = args.password or getpass.getpass("Matrix Bot Password: ").strip()
    channel = args.channel or input("Matrix Room ID (!salon:agent.tchap.gouv.fr): ").strip()
    secret_key = (
        args.secret_key
        or os.getenv("SECRET_ENCRYPTION_KEY")
        or getpass.getpass("Master Secret Key (SECRET_ENCRYPTION_KEY): ").strip()
    )

    if not secret_key:
        print("❌ Erreur : Clé secrète manquante.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "username": username,
        "password": password,
        "channelID": channel,
    }
    if args.homeserver:
        payload["homeserver"] = args.homeserver.strip()

    cipher = AesGcmSecretCipher(secret_key)
    token = cipher.encrypt_token(json.dumps(payload))
    print("\n🔒 Token Stateless chiffré (AES-256-GCM URL-Safe) :")
    print(token)


def cmd_decrypt_token(args: argparse.Namespace) -> None:
    """Decrypt and inspect a stateless token."""
    token = args.token or input("Stateless Token: ").strip()
    secret_key = (
        args.secret_key
        or os.getenv("SECRET_ENCRYPTION_KEY")
        or getpass.getpass("Master Secret Key (SECRET_ENCRYPTION_KEY): ").strip()
    )

    if not secret_key:
        print("❌ Erreur : Clé secrète manquante.", file=sys.stderr)
        sys.exit(1)

    cipher = AesGcmSecretCipher(secret_key)
    try:
        decrypted = cipher.decrypt_token(token)
        print("\n🔓 Contenu déchiffré du token :")
        print(json.dumps(json.loads(decrypted), indent=2))
    except Exception as exc:
        print(f"❌ Échec du déchiffrement : {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_hash_api_key(args: argparse.Namespace) -> None:
    """Compute HMAC-SHA256 hash for an API key."""
    raw_key = args.key or getpass.getpass("Clé API brute: ").strip()
    if not raw_key:
        print("❌ Erreur : Clé API vide.", file=sys.stderr)
        sys.exit(1)
    pepper = args.secret_key or os.getenv("SECRET_ENCRYPTION_KEY")
    print("\n🔑 Empreinte HMAC-SHA256 :")
    print(hash_api_key(raw_key, pepper=pepper))


def cmd_parse_slack(args: argparse.Namespace) -> None:
    """Test parsing a Slack JSON payload and print rendered Matrix text and HTML."""
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            raw_data = json.load(f)
    elif args.json:
        raw_data = json.loads(args.json)
    else:
        print("Entrez le JSON Slack (Ctrl+D pour terminer) :")
        raw_data = json.load(sys.stdin)

    alert = SlackPayloadParser.parse(raw_data)
    print("\n--- Rendu Texte Brut ---")
    print(alert.to_plain_text())
    print("\n--- Rendu HTML Matrix ---")
    print(alert.to_matrix_html())


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="slack2tchap-core",
        description="Boîte à outils cryptographiques et domaine pour slack2tchap",
    )
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # encrypt-token
    p_enc = subparsers.add_parser(
        "encrypt-token", help="Chiffrer des identifiants Matrix en token stateless"
    )
    p_enc.add_argument("-u", "--username", help="Matrix user ID")
    p_enc.add_argument("-p", "--password", help="Matrix password")
    p_enc.add_argument("-c", "--channel", help="Matrix room ID")
    p_enc.add_argument("-s", "--homeserver", help="Optionnel : homeserver URL")
    p_enc.add_argument("-k", "--secret-key", help="Clé secrète de chiffrement")
    p_enc.set_defaults(func=cmd_encrypt_token)

    # decrypt-token
    p_dec = subparsers.add_parser("decrypt-token", help="Déchiffrer un token stateless")
    p_dec.add_argument("-t", "--token", help="Token chiffré")
    p_dec.add_argument("-k", "--secret-key", help="Clé secrète de chiffrement")
    p_dec.set_defaults(func=cmd_decrypt_token)

    # hash-key
    p_hash = subparsers.add_parser("hash-key", help="Générer l'empreinte HMAC-SHA256 d'une clé API")
    p_hash.add_argument("-k", "--key", help="Clé API brute")
    p_hash.add_argument(
        "-s",
        "--secret-key",
        help="Optionnel : clé secrète serveur (SECRET_ENCRYPTION_KEY) utilisée comme poivre",
    )
    p_hash.set_defaults(func=cmd_hash_api_key)

    # parse-slack
    p_parse = subparsers.add_parser(
        "parse-slack", help="Tester le rendu d'un payload Slack vers Matrix"
    )
    p_parse.add_argument("-f", "--file", help="Chemin du fichier JSON")
    p_parse.add_argument("-j", "--json", help="Chaîne JSON directe")
    p_parse.set_defaults(func=cmd_parse_slack)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
