# slack2tchap-core

Bibliothèque commune et boîte à outils pour **slack2tchap** et **slack2tchap-stateless**.

## 📦 Rôle et responsabilités

Ce sous-projet regroupe tous les composants purs, agnostiques des frameworks web et des bases de données :
- **Modèles de domaine purs** (`AlertMessage`, `AlertAttachment`, `RoomId`, `MatrixUserId`, etc.)
- **Ports & Interfaces** (`SecretCipherPort`, `StatelessMessengerPort`, `MatrixMessengerPort`, `UserRepositoryPort`, etc.)
- **Exceptions de domaine** (`DomainError`, `CipherError`, `AuthenticationError`, etc.)
- **Chiffrement AEAD AES-256-GCM** avec dérivation PBKDF2 et validation de tokens URL-safe
- **Hachage cryptographique et validation de clés API** (HMAC-SHA256 avec comparaison en temps constant)
- **Parser de payload entrant Slack / Mattermost** avec conversion vers le format Matrix Markdown / HTML
- **Outils Matrix partagés** (résolution de homeserver Tchap, construction de messages)
- **CLI binaire autonome (`slack2tchap-core`)** pour les manipulations cryptographiques et de validation

## 🚀 Utilisation de la CLI

La bibliothèque fournit une CLI `slack2tchap-core` compilable en binaire autonome :

### 1. Chiffrer un token stateless
```bash
uv run slack2tchap-core encrypt-token \
  -u "@mon-bot:agent.tchap.gouv.fr" \
  -p "MonMotDePasse" \
  -c "!mon_salon:agent.tchap.gouv.fr" \
  -k "ma_cle_secrete_256_bits"
```

### 2. Déchiffrer un token stateless
```bash
uv run slack2tchap-core decrypt-token \
  -t "<TOKEN_CHIFFRÉ>" \
  -k "ma_cle_secrete_256_bits"
```

### 3. Calculer l'empreinte d'une clé API
```bash
uv run slack2tchap-core hash-key -k "s2t_live_secret_12345"
```

### 4. Valider le rendu d'un payload Slack
```bash
uv run slack2tchap-core parse-slack -j '{"text": "Alerte test", "attachments": [{"title": "CPU", "color": "danger"}]}'
```

## 🛠️ Compilation du binaire

```bash
uv run pyinstaller --onefile --name slack2tchap-core src/slack2tchap_core/cli.py
```

## 🧪 Tests

```bash
uv run pytest tests/
```
