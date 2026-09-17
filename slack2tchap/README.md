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

## 🚀 Guide de démarrage et Premier Lancement

### 1. Génération des clés de sécurité (`scripts/generate_api_key.py`)

Au premier lancement, la passerelle a besoin de deux secrets critiques :
1. **`SECRET_ENCRYPTION_KEY`** : Clé maîtresse AES-256 (32 octets aléatoires) utilisée pour chiffrer au repos les mots de passe et tokens Matrix, et poivrer les empreintes d'API keys.
2. **`ADMIN_API_KEY`** : Clé d'API brute à haute entropie (`s2t_live_...`) permettant au compte administrateur initial de s'authentifier.

Un script utilitaire génère ces deux clés en une seule commande et vous fournit le bloc prêt à copier-coller :

```bash
uv run python scripts/generate_api_key.py
```

*Exemple de sortie :*
```text
====================================================================
🔐  GÉNÉRATION DES CLÉS DE SÉCURITÉ POUR SLACK2TCHAP
====================================================================

1. Clé maîtresse de chiffrement AES-256-GCM (SECRET_ENCRYPTION_KEY)
   Valeur (64 caractères hex / 256 bits) : 7f8a9b2c3d4e5f60...

2. Clé API Administrateur (ADMIN_API_KEY)
   Clé en clair     : <VOTRE_CLE_API>
   Préfixe          : s2t_live_m7m8eI...
   Hash HMAC-SHA256 : e3b0c44298fc1c1...

--------------------------------------------------------------------
📋  COPIER-COLLER DANS VOTRE FICHIER .env :
--------------------------------------------------------------------
SECRET_ENCRYPTION_KEY=7f8a9b2c3d4e5f60...
ADMIN_EMAIL=admin@tchap.gouv.fr
ADMIN_API_KEY=<VOTRE_CLE_API>
--------------------------------------------------------------------
```

---

### 2. Configuration du fichier `.env`

Créez un fichier `.env` à la racine de votre environnement ou du dossier `slack2tchap/` :

```env
# Clés cryptographiques (générées via scripts/generate_api_key.py)
SECRET_ENCRYPTION_KEY=7f8a9b2c3d4e5f60... (votre clé 256 bits)
ADMIN_EMAIL=admin@tchap.gouv.fr
ADMIN_API_KEY=<VOTRE_CLE_API>

# Base de données (SQLite par défaut, ou PostgreSQL pour la production)
DATABASE_URL=sqlite+aiosqlite:///./slack2tchap.db
# PostgreSQL : DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/slack2tchap

# Configuration serveur HTTP
ENVIRONMENT=production
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
PUBLIC_BASE_URL=http://localhost:8000

# Paramètres Matrix / Tchap
MATRIX_HOMESERVER=https://matrix.agent.tchap.gouv.fr
MATRIX_AUTO_JOIN=true
```

---

### 3. Démarrer le serveur et initialisation automatique

Lancez la passerelle avec `uv` :

```bash
uv run uvicorn slack2tchap.main:app --host 0.0.0.0 --port 8000
```

Au démarrage :
1. **Migrations automatiques Alembic** : La structure des tables (`users`, `matrix_accounts`, `webhooks`) est automatiquement créée ou mise à niveau.
2. **Auto-seeding de l'Administrateur** : Si la base est vierge, le compte `ADMIN_EMAIL` est automatiquement créé avec l'empreinte sécurisée de votre `ADMIN_API_KEY`.
3. Le serveur est prêt à recevoir vos requêtes d'administration sur `http://localhost:8000`.

---

### 4. Workflow pas à pas : Configurer votre premier Webhook

Toutes les requêtes d'administration s'authentifient via le header `X-API-Key: <VOTRE_CLE>` ou `Authorization: Bearer <VOTRE_CLE>`.

#### Étape 4.1 : Enregistrer votre compte bot Matrix
Le mot de passe du bot est automatiquement chiffré en AES-256-GCM avant stockage :

```bash
curl -X POST http://localhost:8000/api/v1/admin/matrix-accounts \
  -H "X-API-Key: <VOTRE_CLE_API>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bot Alertes Production",
    "matrix_user_id": "@mon-bot:agent.tchap.gouv.fr",
    "password": "MotDePasseTchapSecretDuBot"
  }'
```

*Réponse (conservez l'`id` du bot) :*
```json
{
  "id": "a1b2c3d4-0000-0000-0000-000000000001",
  "name": "Bot Alertes Production",
  "matrix_user_id": "@mon-bot:agent.tchap.gouv.fr",
  "device_id": "AUTO_DEVICE_...",
  "has_password": true,
  "has_access_token": false,
  "created_at": "2026-09-17T10:00:00Z"
}
```

#### Étape 4.2 : Créer un point de terminaison webhook Slack
Associez le bot à un salon Tchap cible :

```bash
curl -X POST http://localhost:8000/api/v1/admin/webhooks \
  -H "X-API-Key: <VOTRE_CLE_API>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Supervision Grafana",
    "matrix_room_id": "!salon_astreinte:agent.tchap.gouv.fr",
    "matrix_account_id": "a1b2c3d4-0000-0000-0000-000000000001"
  }'
```

*Réponse :*
```json
{
  "id": "e5f6a7b8-1111-2222-3333-444455556666",
  "name": "Supervision Grafana",
  "matrix_room_id": "!salon_astreinte:agent.tchap.gouv.fr",
  "matrix_account_id": "a1b2c3d4-0000-0000-0000-000000000001",
  "public_url": "http://localhost:8000/webhook/slack/e5f6a7b8-1111-2222-3333-444455556666",
  "is_active": true,
  "created_at": "2026-09-17T10:05:00Z"
}
```

L'URL publique `http://localhost:8000/webhook/slack/e5f6a7b8-...` est prête à être renseignée dans vos générateurs d'alertes (Grafana, Alertmanager, Sentry, GitLab...).

#### Étape 4.3 : (Optionnel) Créer un utilisateur non-admin
En tant qu'administrateur, vous pouvez déléguer la gestion de webhooks à une autre équipe :

```bash
curl -X POST http://localhost:8000/api/v1/admin/users \
  -H "X-API-Key: <VOTRE_CLE_API>" \
  -H "Content-Type: application/json" \
  -d '{"email": "equipe-infra@domaine.gouv.fr"}'
```

La réponse fournit une nouvelle clé d'API (`s2t_live_...`) dédiée à cet utilisateur.

---

### 5. Compilation en binaire autonome (PyInstaller)

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
     -H "X-API-Key: <VOTRE_CLE_API>"
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
