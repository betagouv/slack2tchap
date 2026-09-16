# slack2tchap

Passerelle sécurisée haute performance développée en Python (FastAPI) faisant office de pont entre les webhooks entrants au format standard **Slack / Mattermost** et la messagerie sécurisée interministérielle de l'État français **Matrix / Tchap**.

Le service est conçu pour fonctionner en mode **100% Stateless** (compatible PaaS type Scalingo / Kubernetes) avec une persistance multi-tenant dans **PostgreSQL** :
- Chiffrement de bout en bout (**E2EE - Olm/Megolm**) via `matrix-nio[e2e]`.
- Détection automatique si le salon cible est chiffré ou non.
- Sauvegarde et restauration automatiques des stores cryptographiques SQLite Olm archivés (`tar.gz`) sous forme binaire dans PostgreSQL.
- Support multi-bots : déclaration de multiples comptes Matrix bots via API d'administration.
- URLs de webhooks publiques uniques (`/webhook/slack/{uuid}` ou `/slack/{uuid}`) ne nécessitant aucune clé API côté émetteur (Alertmanager, Grafana, GitLab, GitHub, Datadog...).
- Chiffrement symétrique **AES-256-GCM** des secrets (mots de passe et tokens d'accès Matrix) en base de données.

---

## 🏛️ Architecture (Clean Architecture)

Le projet respecte scrupuleusement les principes de la **Clean Architecture** sous `src/slack2tchap/` :

```
src/slack2tchap/
├── domain/                  # Cœur métier pur (zéro dépendance externe)
│   ├── models.py            # AlertMessage, MatrixAccount, WebhookEndpoint, User
│   ├── ports.py             # Interfaces / Protocoles (MatrixMessengerPort, Repositories, Cipher)
│   └── exceptions.py        # Exceptions métier
├── application/             # Orchestration des flux applicatifs
│   ├── use_cases.py         # ProcessPublicWebhookUseCase, RegisterMatrixAccount, CreateWebhook...
│   └── dtos.py              # Commandes et DTOs
├── infrastructure/          # Adaptateurs techniques et base de données
│   ├── database/            # SQLAlchemy async (PostgreSQL / asyncpg) + Alembic
│   │   ├── models.py        # UserModel, MatrixAccountModel, WebhookModel
│   │   ├── session.py       # Async engine & sessionmaker
│   │   └── migrator.py      # Exécution auto des migrations Alembic au démarrage
│   ├── matrix/              # Client Matrix via matrix-nio[e2e]
│   │   ├── adapter.py       # MatrixNioAdapter (E2EE, auto-join, session SQLite)
│   │   └── manager.py       # MatrixClientManager (restauration/sauvegarde stores blob en DB)
│   ├── repositories/        # Repositories SQLAlchemy (User, MatrixAccount, Webhook)
│   ├── security/            # Hashing SHA-256 d'API keys & Chiffrement AES-256-GCM
│   └── parsers/             # Transformation Slack/Mattermost -> Modèles Domain
├── interfaces/api/          # Adaptateurs d'entrée HTTP (FastAPI)
│   ├── routes.py            # Endpoints publics (/webhook/slack/{uuid}) et admin (/api/v1/admin/...)
│   ├── schemas.py           # Schémas Pydantic d'entrée et de sortie
│   └── dependencies.py      # Injection de dépendances FastAPI
├── core/                    # Socle transverse
│   ├── config.py            # Configuration pydantic-settings
│   └── logging.py           # Configuration centralisée des logs
└── main.py                  # Lifespan ASGI : migrations, démarrage manager Matrix, sauvegarde à l'arrêt
```

---

## 🚀 Démarrage rapide

### 1. Prérequis

- **Python 3.12+**
- **uv** (gestionnaire d'environnement et de paquets)
- **Docker & Docker Compose** (pour PostgreSQL en local)

### 2. Démarrer PostgreSQL

Un compose prêt à l'emploi est fourni (par défaut sur le port local `5436` pour éviter les conflits avec d'autres bases locales) :

```bash
docker compose -f docker-compose-dev.yaml up -d
```

### 3. Configuration de l'environnement (`.env`)

Générez une clé de chiffrement des secrets et une clé API administrateur :

```bash
uv run python scripts/generate_api_key.py
```

Ce script affiche un exemple de configuration prêt à être copié dans votre `.env` :

```bash
cp .env.example .env
```

Variables principales dans `.env` :

| Variable | Description | Exemple |
|---|---|---|
| `DATABASE_URL` | URL de connexion PostgreSQL asynchrone | `postgresql+asyncpg://slack2tchap:slack2tchap_dev@localhost:5436/slack2tchap` |
| `SECRET_ENCRYPTION_KEY` | Clé secrète 32 bytes (hex 64 chars) pour AES-GCM | `0123456789abcdef...` |
| `ADMIN_EMAIL` | Email de l'administrateur initial | `admin@tchap.gouv.fr` |
| `ADMIN_API_KEY` | Clé API initiale de l'admin (insérée au 1er boot) | `s2t_live_secret_...` |
| `PUBLIC_BASE_URL` | URL de base publique du service | `https://slack2tchap.mon-domaine.fr` |
| `MATRIX_HOMESERVER` | Serveur Matrix / Tchap par défaut | `https://matrix.agent.tchap.gouv.fr` |
| `MATRIX_AUTO_JOIN` | Accepter automatiquement les invitations dans les salons | `true` |
| `PORT` | Port d'écoute HTTP | `8000` |

### 4. Installer les dépendances

```bash
uv sync --dev
```

### 5. Lancer l'application

Les migrations Alembic s'exécutent automatiquement au démarrage de l'application :

```bash
uv run uvicorn slack2tchap.main:app --reload --port 8000
```

---

## ⚙️ Gestion des Utilisateurs, Bots & Webhooks

### Modèle de sécurité

Le service utilise un système d'authentification par **clé API** (`X-API-Key` ou `Authorization: Bearer <clé>`) avec deux niveaux de privilèges :

| Rôle | Peut créer des utilisateurs | Peut gérer ses bots & webhooks | Accès aux ressources d'autres utilisateurs |
|---|---|---|---|
| **Admin** | ✅ | ✅ | ❌ (isolement strict) |
| **Utilisateur standard** | ❌ (403 Forbidden) | ✅ | ❌ (isolement strict) |

> **Isolement strict** : chaque utilisateur ne peut voir, modifier ou supprimer **que** ses propres bots Matrix et webhooks. Un utilisateur ne peut pas non plus créer un webhook référençant le bot d'un autre utilisateur.

### 0. Administrateur initial (seeding automatique)

Au **premier démarrage**, l'application crée automatiquement un compte administrateur à partir des variables d'environnement `ADMIN_EMAIL` et `ADMIN_API_KEY` :

```bash
# Générer les clés de sécurité
uv run python scripts/generate_api_key.py
```

Ce script affiche les valeurs à insérer dans `.env` (dont `ADMIN_API_KEY` et `SECRET_ENCRYPTION_KEY`). Le seeding est **idempotent** : si l'admin existe déjà, il est ignoré.

### 1. Créer un utilisateur (admin uniquement)

Seul un administrateur peut créer de nouveaux comptes utilisateurs. La clé API générée est retournée **une seule fois** dans la réponse et ne peut pas être récupérée ultérieurement :

```bash
curl -X POST http://localhost:8000/api/v1/admin/users \
  -H "X-API-Key: <ADMIN_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"email": "operator@beta.gouv.fr"}'
```

Réponse :
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "email": "operator@beta.gouv.fr",
  "api_key_prefix": "s2t_live_aBcDeF...",
  "raw_api_key": "s2t_live_aBcDeFgHiJkLmNoPqRsTuVwXyZ...",
  "is_admin": false,
  "is_active": true,
  "created_at": "2026-09-16T10:00:00+00:00"
}
```

> ⚠️ **Conservez précieusement la valeur `raw_api_key`** — elle ne sera plus jamais affichée. Si la clé est perdue, il faudra créer un nouvel utilisateur.

L'utilisateur créé peut ensuite utiliser sa clé API pour gérer **ses propres** bots et webhooks.

### 2. Enregistrer un bot Matrix (Tchap)

Chaque utilisateur authentifié peut enregistrer ses propres comptes bots Matrix :

```bash
curl -X POST http://localhost:8000/api/v1/admin/matrix-accounts \
  -H "X-API-Key: <VOTRE_CLE_API>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bot Alertmanager DSI",
    "matrix_user_id": "@bot-alertmanager:agent.tchap.gouv.fr",
    "password": "mot_de_passe_du_bot"
  }'
```

Le mot de passe / token est chiffré en AES-256-GCM avant stockage en base. Le client Matrix initialise immédiatement sa session E2EE et sauvegarde l'archive cryptographique dans PostgreSQL.

### 3. Créer une URL de Webhook pour un salon

Le webhook **doit référencer un bot appartenant à l'utilisateur authentifié** :

```bash
curl -X POST http://localhost:8000/api/v1/admin/webhooks \
  -H "X-API-Key: <VOTRE_CLE_API>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alertes Production",
    "matrix_room_id": "!salon_tchap_id:agent.tchap.gouv.fr",
    "matrix_account_id": "<UUID_DU_BOT_OBTENU_CI_DESSUS>"
  }'
```

Réponse :
```json
{
  "id": "e4b52bb2-6b99-4d69-a1b6-79cf02ca4301",
  "name": "Alertes Production",
  "matrix_room_id": "!salon_tchap_id:agent.tchap.gouv.fr",
  "matrix_account_id": "8f3b23e8-54c2-47df-bc69-1ce7d04e38e1",
  "public_url": "http://localhost:8000/webhook/slack/e4b52bb2-6b99-4d69-a1b6-79cf02ca4301",
  "is_active": true,
  "created_at": "2026-09-16T10:00:00Z"
}
```

### 4. Vérifier la session du bot (Vérification E2EE / Emojis)

Par défaut, lors de sa première connexion, la session du bot apparaît non vérifiée dans Tchap (avec un symbole d'avertissement à côté de ses messages). Pour certifier la session cryptographique de votre bot avec un **bouclier vert vérifié** dans Tchap :

#### Procédure étape par étape :

1. **Identifier l'ID du bot (`bot_uuid`)** :
   - Récupérez l'identifiant UUID du compte bot obtenu lors de sa création, ou listez vos bots existants :
     ```bash
     curl http://localhost:8000/api/v1/admin/matrix-accounts \
       -H "X-API-Key: <VOTRE_CLE_API>"
     ```

2. **Initier la vérification depuis Tchap** :
   - Connectez-vous sur **Tchap** (Web ou Mobile) avec le compte associé au bot.
   - Rendez-vous dans **Paramètres** > **Sessions** (ou *Sécurité & Confidentialité* > *Appareils*).
   - Localisez la session du bot (nommée par défaut `s2t_<id>`).
   - Cliquez sur **Vérifier l'appareil** (ou l'icône de bouclier).

3. **Déclencher la négociation SAS via la passerelle** :
   - Dans votre terminal, déclenchez la route de vérification sécurisée avec votre clé API propriétaire (`X-API-Key` ou `Authorization: Bearer`) :
     ```bash
     curl -X POST http://localhost:8000/verify/<bot_uuid> \
       -H "X-API-Key: <VOTRE_CLE_API>"
     ```
   - La passerelle échange les clés éphémères et renvoie les 7 émojis SAS :
     ```json
     {
       "status": "emojis_ready",
       "message": "Please compare these emojis with the ones displayed on your Tchap client, then confirm in Tchap ('They match').",
       "account_id": "086992a6-d36b-4e70-a87b-fa56d7ec9548",
       "transaction_id": "41c073fc0a56466c837802cde67d8628",
       "target_device_id": "mpmhW9NLOV",
       "emojis": [
         {"emoji": "🐶", "description": "Dog"},
         {"emoji": "🚀", "description": "Rocket"},
         {"emoji": "🐱", "description": "Cat"},
         {"emoji": "🌟", "description": "Star"},
         {"emoji": "🍕", "description": "Pizza"},
         {"emoji": "🎩", "description": "Hat"},
         {"emoji": "🚲", "description": "Bicycle"}
       ],
       "emoji_string": "🐶 🚀 🐱 🌟 🍕 🎩 🚲"
     }
     ```

4. **Confirmer la correspondance dans Tchap** :
   - Sur Tchap Web / Mobile, comparez les 7 émojis affichés avec la chaîne `emoji_string` retournée par le terminal.
   - Cliquez sur **"Elles correspondent"** sur Tchap.
   - Le bot transmet automatiquement l'acquittement de fin (`m.key.verification.done`).
   - La session est validée avec succès : **le bouclier vert apparaît** et l'archive de clés SQLite mise à jour est immédiatement persistée dans PostgreSQL.

### 5. Lister et supprimer ses ressources

Chaque utilisateur ne voit que ses propres ressources :

```bash
# Lister ses bots
curl http://localhost:8000/api/v1/admin/matrix-accounts \
  -H "X-API-Key: <VOTRE_CLE_API>"

# Lister ses webhooks
curl http://localhost:8000/api/v1/admin/webhooks \
  -H "X-API-Key: <VOTRE_CLE_API>"

# Supprimer un bot
curl -X DELETE http://localhost:8000/api/v1/admin/matrix-accounts/<bot_uuid> \
  -H "X-API-Key: <VOTRE_CLE_API>"

# Supprimer un webhook
curl -X DELETE http://localhost:8000/api/v1/admin/webhooks/<webhook_uuid> \
  -H "X-API-Key: <VOTRE_CLE_API>"
```

### 6. Envoyer une alerte (Public - sans clé API requise)


Configurez simplement l'URL reçue (`/webhook/slack/{uuid}` ou `/slack/{uuid}`) dans Alertmanager, Grafana, GitLab CI, etc. :

```bash
curl -X POST http://localhost:8000/webhook/slack/e4b52bb2-6b99-4d69-a1b6-79cf02ca4301 \
  -H "Content-Type: application/json" \
  -d '{
    "text": "🚨 Incident de production en cours",
    "attachments": [
      {
        "color": "danger",
        "title": "Alerte Disque Saturé - Serveur DB-01",
        "fields": [
          {"title": "Espace restant", "value": "2%", "short": true},
          {"title": "Niveau", "value": "Critique", "short": true}
        ]
      }
    ]
  }'
```

Le service identifie le salon et le bot associé depuis la base de données, chiffre le message si le salon Tchap est chiffré, et l'envoie instantanément.

### Récapitulatif des routes API

| Méthode | Route | Auth | Rôle requis | Description |
|---|---|---|---|---|
| `GET` | `/health` | ❌ | — | Healthcheck |
| `POST` | `/webhook/slack/{uuid}` | ❌ | — | Ingestion webhook public |
| `POST` | `/slack/{uuid}` | ❌ | — | Alias court webhook |
| `POST` | `/api/v1/admin/users` | ✅ | **Admin** | Créer un utilisateur |
| `POST` | `/api/v1/admin/matrix-accounts` | ✅ | Utilisateur | Enregistrer un bot |
| `GET` | `/api/v1/admin/matrix-accounts` | ✅ | Utilisateur | Lister ses bots |
| `DELETE` | `/api/v1/admin/matrix-accounts/{id}` | ✅ | Utilisateur | Supprimer son bot |
| `POST` | `/api/v1/admin/webhooks` | ✅ | Utilisateur | Créer un webhook |
| `GET` | `/api/v1/admin/webhooks` | ✅ | Utilisateur | Lister ses webhooks |
| `DELETE` | `/api/v1/admin/webhooks/{id}` | ✅ | Utilisateur | Supprimer son webhook |
| `POST` | `/verify/{bot_uuid}` | ✅ | Utilisateur | Vérification SAS E2EE |

---

## 📨 Contrat d'interface Slack & Mattermost supporté

La passerelle implémente le contrat d'interface webhook entrant standard de **Slack** et **Mattermost** (utilisé nativement par Alertmanager Prometheus, Grafana, GitLab CI, GitHub Actions, Datadog, Sentry, etc.).

### 1. Payload racine (`application/json`)

| Champ | Type | Supporté | Rendu & Comportement dans Matrix / Tchap |
|---|---|---|---|
| `text` | `string` | ✅ Oui | Message principal. Nettoyé et converti automatiquement (Markdown + HTML). |
| `attachments` | `array[object]` | ✅ Oui | Blocs riches d'informations et d'alertes détaillées (voir ci-dessous). |
| `channel` | `string` | ✅ Optionnel | Surcharge le salon cible si c'est un ID Matrix (`!room:server`) ou alias (`#alias:server`). |
| `username` | `string` | ℹ️ Accepté | Accepté dans le schéma (l'identité émettrice est portée par le compte bot Matrix). |
| `icon_emoji` | `string` | ℹ️ Accepté | Accepté dans le schéma Pydantic (non bloquant). |
| `icon_url` | `string` | ℹ️ Accepté | Accepté dans le schéma Pydantic (non bloquant). |

### 2. Blocs d'attachements (`attachments[]`)

Chaque élément de la liste `attachments` est converti en une citation stylisée Matrix (`<blockquote>`) avec une bordure verticale colorée selon la sévérité :

| Champ | Type | Supporté | Rendu dans Matrix / Tchap |
|---|---|---|---|
| `color` | `string` | ✅ Oui | Couleur hexadécimale (`#36a64f`, `#de4343`...) ou nom prédéfini (`good`, `warning`, `danger`). Détermine la couleur de bordure du bloc et le badge de sévérité (`[SUCCESS]`, `[WARNING]`, `[DANGER]`). |
| `title` | `string` | ✅ Oui | Titre du bloc d'alerte, rendu en gras `<h4>`. |
| `title_link` | `string` (URL) | ✅ Oui | Transforme le titre en hyperlien cliquable : `<a href="title_link">title</a>`. |
| `text` | `string` | ✅ Oui | Corps principal du bloc d'attachement avec préservation des sauts de ligne. |
| `fallback` | `string` | ✅ Oui | Utilisé comme texte alternatif si le champ `text` n'est pas renseigné. |
| `author_name` | `string` | ✅ Oui | Nom de l'auteur affiché discrètement au-dessus du titre (`<small>`). |
| `fields` | `array[object]` | ✅ Oui | Liste de paires clé/valeur structurées (voir ci-dessous). |
| `footer` | `string` | ✅ Oui | Texte de bas de bloc affiché en italique discret (`<small><em>`). |
| `ts` | `number` | ✅ Oui | Horodatage Unix de l'événement. |
| `pretext` | `string` | ℹ️ Accepté | Texte introductif précédant le bloc. |
| `author_link`, `author_icon`, `footer_icon` | `string` (URL) | ℹ️ Accepté | URLs associées aux métadonnées. |

### 3. Champs structurés (`attachments[].fields[]`)

Les champs structurés sont rendus sous forme de tableau HTML propre (`<table>`) dans Matrix, ou sous forme de liste à puces en version texte brut :

| Champ | Type | Supporté | Rendu dans Matrix / Tchap |
|---|---|---|---|
| `title` | `string` | ✅ Oui | Intitulé du champ (affiché en gras dans la colonne de gauche). |
| `value` | `string` | ✅ Oui | Valeur du champ (colonne de droite, liens mrkdwn convertis). |
| `short` | `boolean` | ✅ Oui | Indicateur Slack pour affichage compact côte à côte. |

### 4. Conversion syntaxique automatique (Slack mrkdwn -> Matrix)

Les syntaxes spécifiques à Slack sont automatiquement traduites :

| Format Slack entrant | Rendu converti dans Matrix / Tchap |
|---|---|
| `<https://example.com\|Mon Lien>` | Lien cliquable `[Mon Lien](https://example.com)` / `<a href="...">` |
| `<https://example.com>` | URL directe `https://example.com` |
| `<!here>`, `<!channel>`, `<!everyone>` | Mention Matrix `@room` |
| `*texte en gras*` | `**texte en gras**` / `<strong>` |
| `_texte en italique_` | `_texte en italique_` / `<em>` |
| `~texte barré~` | `<del>texte barré</del>` |
| `` `code inline` `` | `` `code inline` `` / `<code>` |

## 🧪 Qualité & Tests

```bash
# Vérification du formatage et linting
uv run ruff check .
uv run ruff format --check .

# Typage strict (Pyright)
uv run pyright

# Exécution de la suite de tests complète
uv run pytest
```

---

## ☁️ Déploiement sur Scalingo (Stateless)

Le service est conçu pour les environnements à système de fichiers éphémère :
1. Créez une application Scalingo avec un addon PostgreSQL.
2. Définissez les variables d'environnement dans le Dashboard Scalingo (`DATABASE_URL`, `SECRET_ENCRYPTION_KEY`, `ADMIN_API_KEY`, `PUBLIC_BASE_URL`).
3. Déployez votre code (via Git ou GitHub integration).
4. Au boot, le dyno applique les migrations Alembic et instancie les bots configurés en restaurant leurs stores Olm depuis PostgreSQL.
5. À chaque arrêt / redémarrage du dyno, le `lifespan` sauvegarde l'état cryptographique à jour dans PostgreSQL.
Pour plus de détails, consultez [docs/STATELESS_MATRIX_SCALINGO.md](file:///Users/nsagon/Projects/beta/tchap-webhook-gateway/docs/STATELESS_MATRIX_SCALINGO.md).
