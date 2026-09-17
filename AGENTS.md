# AGENTS.md — slack2tchap (Matrix / Tchap Webhook Gateway Monorepo)

Passerelle modulaire et sécurisée faisant office de passerelle entre les webhooks entrants au format Slack / Mattermost et la messagerie Matrix / Tchap.

## 📦 Organisation du Monorepo (`uv` workspace)

Le projet est structuré en **3 sous-projets indépendants** :

```
tchap-webhook-gateway/
├── slack2tchap-core/          # Bibliothèque pure : Domain, Crypto AES-GCM, Parsers, CLI
│   ├── src/slack2tchap_core/
│   │   ├── domain/            # Models, ports, exceptions
│   │   ├── infrastructure/    # Cipher AES-256-GCM, API key hashing, Slack parser
│   │   ├── matrix/            # Résolution homeserver, formatage messages Matrix
│   │   └── cli.py             # CLI utilitaire (slack2tchap-core)
│   └── tests/                 # Tests unitaires du cœur métier
├── slack2tchap-stateless/     # Micro-service 100% Stateless (ZÉRO base de données)
│   ├── src/slack2tchap_stateless/
│   │   ├── core/config.py     # Settings pydantic-settings
│   │   ├── application/       # ProcessStatelessWebhookUseCase
│   │   ├── infrastructure/    # StatelessMatrixMessenger (client éphémère sans persistance)
│   │   ├── interfaces/api/    # Routes /slack?param=... et /health
│   │   └── main.py            # Entrypoint ASGI & PyInstaller
│   ├── scripts/               # generate_stateless_url.py
│   └── tests/                 # Tests d'ingestion stateless
├── slack2tchap/               # Passerelle Stateful multi-bots
│   ├── src/slack2tchap/
│   │   ├── infrastructure/    # PostgreSQL/SQLite, SQLAlchemy, Repositories, E2EE Matrix
│   │   ├── interfaces/api/    # Routes d'administration, RBAC, /verify SAS, /webhook/slack/{uuid}
│   │   └── main.py            # Entrypoint ASGI & PyInstaller
│   ├── alembic/               # Migrations de base de données
│   ├── scripts/               # generate_api_key.py
│   └── tests/                 # Tests stateful (RBAC, migrations, E2EE)
├── scripts/                   # build_binaries.sh (compilation PyInstaller des 3 projets)
└── .github/workflows/ci.yml   # Pipeline CI (Lint, Format, Types, Tests, Binaires)
```

## Stack technique

- **Runtime & Gestionnaire** : Python 3.12+, géré exclusivement avec `uv` (monorepo workspace)
- **Web framework** : FastAPI (ASGI)
- **Typage & Validation** : Pydantic v2 + Pyright (typage strict)
- **Configuration** : `pydantic-settings`
- **Matrix client** : `matrix-nio` (stateless sans E2EE) et `matrix-nio[e2e]` (stateful avec Olm/Megolm)
- **Linter / Formateur** : `ruff`
- **Tests** : `pytest`, `pytest-asyncio`, `httpx`
- **Binaires** : `pyinstaller`

## Principes d'Architecture & Règles Strictes

1. **slack2tchap-core** ne dépend d'aucun framework web (pas de FastAPI), d'aucun ORM et d'aucun client Matrix lourd.
2. **slack2tchap-stateless** ne dépend d'aucune base de données (pas de SQLAlchemy, pas d'Alembic, pas d'asyncpg, pas d'aiosqlite).
3. **slack2tchap** héberge l'ensemble des fonctionnalités avec base de données et E2EE.
4. **Configuration (`pydantic-settings`)** :
   - Toute variable d'environnement doit être déclarée dans les classes `Settings` dédiées.
   - Ne jamais faire d'appel direct à `os.getenv()` dans le code applicatif.
5. **Typage et Qualité** :
   - 100% de conformité à `ruff check`, `ruff format --check` et `pyright` (0 warning, 0 error).

## Commandes utiles

- Installer les dépendances du workspace : `uv sync`
- Lancer les tests sur les 3 projets : `uv run pytest`
- Vérifier le formatage et le lint : `uv run ruff check . && uv run ruff format --check .`
- Vérifier les types : `uv run pyright`
- Compiler les 3 binaires : `./scripts/build_binaries.sh`
- Lancer slack2tchap-stateless : `uv run uvicorn slack2tchap_stateless.main:app --reload`
- Lancer slack2tchap (stateful) : `uv run uvicorn slack2tchap.main:app --reload`
