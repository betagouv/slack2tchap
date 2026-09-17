# slack2tchap (Stateful Multi-Bot Webhook Gateway)

Passerelle webhook multi-bots complète et sécurisée entre Slack / Mattermost et Matrix / Tchap, avec **support E2EE (chiffrement de bout en bout Olm/Megolm)**, **persistance en base de données** (PostgreSQL / SQLite), et **gestion multi-utilisateurs / RBAC**.

---

## 🏗️ Architecture & Fonctionnalités

Contrairement à `slack2tchap-stateless` qui fonctionne sans base de données pour les salons non chiffrés, ce projet fournit une solution complète pour les environnements exigeant un chiffrement de bout en bout (E2EE) et une gestion centralisée :

- **Multi-tenant / Multi-bots** : Chaque utilisateur ou équipe peut configurer ses propres bots Matrix et ses propres webhooks.
- **Support E2EE natif (Olm / Megolm)** : Sessions chiffrées persistantes avec chiffrement des clés au repos et vérification interactive SAS par emojis (`/verify/{bot_uuid}`).
- **Base de données relationnelle** : Modèles SQLAlchemy gérés par des migrations automatiques Alembic (compatible SQLite et PostgreSQL).
- **Contrôle d'accès basé sur les rôles (RBAC)** :
  - **Administrateurs** : Création et suppression d'utilisateurs, suppression en cascade des bots et webhooks orphelins.
  - **Utilisateurs** : Gestion de leurs propres bots Matrix et de leurs webhooks associés.
- **Sécurité** :
  - Clés d'API hachées en SHA-256 avec comparaison en temps constant (`hmac.compare_digest`).
  - Mots de passe et tokens Matrix chiffrés au repos en **AES-256-GCM** via la clé secrète du serveur.

---

## 🚀 Démarrage rapide

### 1. Variables d'environnement (`.env`)

```env
# Clé maîtresse de chiffrement AES-256-GCM (32 octets / 256 bits)
SECRET_ENCRYPTION_KEY=votre_cle_secrete_hautement_securisee_256_bits!

# Base de données (SQLite par défaut, ou PostgreSQL asyncpg)
DATABASE_URL=sqlite+aiosqlite:///./slack2tchap.db
# Pour PostgreSQL :
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/slack2tchap

# Environnement et logs
ENVIRONMENT=production
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
PUBLIC_BASE_URL=http://localhost:8000

# Matrix / Tchap
MATRIX_HOMESERVER=https://matrix.agent.tchap.gouv.fr
MATRIX_AUTO_JOIN=true
```

### 2. Démarrer le serveur avec `uv`

```bash
uv run uvicorn slack2tchap.main:app --host 0.0.0.0 --port 8000
```

Au démarrage, les migrations Alembic sont appliquées automatiquement et un compte administrateur initial est créé si la base est vierge.

### 3. Compilation en binaire autonome (PyInstaller)

```bash
uv run pyinstaller --onefile --name slack2tchap src/slack2tchap/main.py
```

Le binaire standalone est produit dans `dist/slack2tchap`.

---

## 📡 Récapitulatif des routes API

| Méthode | Route | Auth | Rôle requis | Description |
|---|---|---|---|---|
| `GET` | `/health` | ❌ | — | Vérification de l'état de l'application |
| `POST` | `/webhook/slack/{uuid}` | ❌ | — | Ingestion publique d'un webhook Slack via UUID |
| `POST` | `/slack/{uuid}` | ❌ | — | Alias court pour l'ingestion d'un webhook |
| `POST` | `/api/v1/admin/users` | ✅ | **Admin** | Créer un nouvel utilisateur avec clé d'API |
| `DELETE` | `/api/v1/admin/users/{id}` | ✅ | **Admin** | Supprimer un utilisateur et ses ressources associées en cascade |
| `POST` | `/api/v1/admin/matrix-accounts` | ✅ | Utilisateur | Enregistrer un bot Matrix (mot de passe ou access_token) |
| `GET` | `/api/v1/admin/matrix-accounts` | ✅ | Utilisateur | Lister ses bots enregistrés |
| `DELETE` | `/api/v1/admin/matrix-accounts/{id}` | ✅ | Utilisateur / **Admin** | Supprimer un bot Matrix et ses webhooks associés |
| `POST` | `/api/v1/admin/webhooks` | ✅ | Utilisateur | Créer un point de terminaison webhook associé à un bot |
| `GET` | `/api/v1/admin/webhooks` | ✅ | Utilisateur | Lister ses webhooks configurés |
| `DELETE` | `/api/v1/admin/webhooks/{id}` | ✅ | Utilisateur / **Admin** | Supprimer un webhook |
| `POST` | `/verify/{bot_uuid}` | ✅ | Utilisateur | Déclencher la vérification interactive SAS E2EE (émojis) |

---

## 🔐 Vérification SAS E2EE (Échange d'émojis)

Pour les salons Tchap chiffrés de bout en bout :
1. Invitez le bot dans le salon Tchap cible.
2. Déclenchez la vérification interactive :
   ```bash
   curl -X POST http://localhost:8000/verify/<BOT_UUID> \
     -H "Authorization: Bearer <VOTRE_CLE_API>"
   ```
3. L'API retourne les émojis SAS à comparer avec votre application Tchap (Web ou Mobile) :
   ```json
   {
     "status": "emojis_ready",
     "emojis": [
       {"emoji": "🐶", "description": "Dog"},
       {"emoji": "🚀", "description": "Rocket"},
       {"emoji": "🐱", "description": "Cat"},
       {"emoji": "🌟", "description": "Star"},
       {"emoji": "🍕", "description": "Pizza"},
       {"emoji": "🎩", "description": "Hat"},
       {"emoji": "🚲", "description": "Bicycle"}
     ]
   }
   ```
4. Confirmez la correspondance dans Tchap (« Ils correspondent ») pour finaliser l'approbation du périphérique.

---

## 🧪 Exécuter les tests

```bash
uv run pytest tests/
```
