# AGENTS.md — slack2tchap (Matrix / Tchap Webhook Gateway)
    
    Micro-service FastAPI faisant office de passerelle entre les webhooks entrants au format Slack / Mattermost et la messagerie sécurisée Matrix / Tchap.
    
    ## Stack technique
    
    - **Runtime & Gestionnaire** : Python 3.12+, géré exclusivement avec `uv`
    - **Web framework** : FastAPI (ASGI)
    - **Typage & Validation** : Pydantic v2 + Pyright (typage strict)
    - **Configuration** : `pydantic-settings`
    - **Matrix client** : `matrix-nio[e2e]` (avec support Olm/Megolm & libolm)
    - **Linter / Formateur** : `ruff`
    - **Tests** : `pytest`, `pytest-asyncio`, `httpx`
    
    ## Principes d'Architecture (Clean Architecture)
    
    Le projet respecte les couches de la Clean Architecture sous `src/slack2tchap/` :
    
  src/slack2tchap/
  ├── domain/            # Cœur métier pur (zéro dépendance externe)
  │   ├── models.py      # Entités et Value Objects (AlertMessage, etc.)
  │   ├── ports.py       # Interfaces/Protocols (MatrixMessengerPort)
  │   └── exceptions.py  # Exceptions métier
  ├── application/       # Orchestration des flux
  │   ├── use_cases.py   # Logique applicative (SendAlertUseCase)
  │   └── dtos.py        # Objets de transfert
  ├── infrastructure/    # Adaptateurs et technos externes
  │   ├── matrix/        # Client matrix-nio, crypto store SQLite, gestion E2EE
  │   └── parsers/       # Transformation payload Slack/Mattermost -> Domain
  ├── interfaces/api/    # Adaptateurs d'entrée (FastAPI)
  │   ├── routes.py      # Contrôleurs HTTP
  │   ├── schemas.py     # Schémas Pydantic d'entrée
  │   └── dependencies.py# Injection de dépendances
  ├── core/              # Transverse technique
  │   ├── config.py      # Pydantic Settings
  │   └── logging.py     # Setup des logs
  └── main.py            # Point d'entrée et lifespan ASGI

    
    ### Règles strictes à suivre pour les modifications de code :
    
    1. **Règle des dépendances** :
       - Le `domain` ne dépend de rien d'externe (ni FastAPI, ni `matrix-nio`, ni Pydantic).
       - L'`application` ne dépend que du `domain`.
       - L'`infrastructure` et l'`interface API` implémentent les ports définis par le domain.
    2. **Configuration (`pydantic-settings`)** :
       - Toute variable d'environnement doit être déclarée dans `src/slack2tchap/core/config.py` dans une classe dérivée de `pydantic_settings.BaseSettings`.
       - Ne jamais faire d'appel direct à `os.getenv()` dans le code applicatif ou d'infrastructure : toujours injecter `Settings`.
       - Fournir des valeurs par défaut saines pour le développement local et documenter les variables requises dans `.env.example`.
    3. **Typage et Qualité de code** :
       - Toutes les fonctions, méthodes et paramètres doivent être explicitement typés.
       - Tout le code doit passer `ruff check`, `ruff format --check` et `pyright` sans aucun warning ni erreur.
    4. **Gestion du Chiffrement Matrix (E2EE / Tchap)** :
       - Le chemin du crypto store SQLite (`STORE_PATH`) doit être persistant (volume). Ne jamais instancier un client Matrix sans stockage persistant des clés.
       - Ne pas assumer que tous les salons sont chiffrés : vérifier l'état du salon (`room.encrypted`) avant d'émettre l'alerte.
       - Gérer l'auto-join sur invitation.
       - Utiliser le **Matrix ID complet** (`@user:server.gouv.fr`) pour l'authentification (compatibilité MAS Tchap 2026).

    ## Commandes utiles

    - Installer les dépendances : `uv sync`
    - Lancer le serveur dev : `uv run uvicorn slack2tchap.main:app --reload`
    - Lancer les tests : `uv run pytest`
    - Vérifier le formatage et le lint : `uv run ruff check . && uv run ruff format --check .`
    - Vérifier les types : `uv run pyright`
    - Compiler le binaire localement : `uv run pyinstaller --onefile --name slack2tchap src/slack2tchap/main.py`

