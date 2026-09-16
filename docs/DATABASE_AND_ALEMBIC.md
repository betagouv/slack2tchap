# Guide Technique : Base de Données PostgreSQL & Migrations Alembic

Ce document détaille l'architecture de persistance de `slack2tchap`, la gestion asynchrone des connexions avec **SQLAlchemy 2.0** / **asyncpg**, et le cycle de vie des migrations automatisées avec **Alembic**.

---

## 1. Stack Technique & Architecture

- **SGBD** : PostgreSQL 16+ (environnement local conteneurisé via `docker-compose-dev.yaml`)
- **Driver Asynchrone** : `asyncpg` (driver binaire asynchrone à haute performance)
- **ORM / Query Builder** : SQLAlchemy 2.0 en mode strict typé (`Mapped[...]`, `mapped_column(...)`)
- **Gestionnaire de Migrations** : Alembic avec support natif `async_engine`
- **Pattern de Conception** : Repository Pattern (Clean Architecture)
  - Le domaine ne dépend d'aucun ORM.
  - Les repositories (`SqlAlchemyUserRepository`, `SqlAlchemyWebhookRepository`) transforment les modèles ORM vers les entités pures du domaine (`User`, `WebhookEndpoint`).

---

## 2. Démarrage de PostgreSQL en Développement

Pour lancer PostgreSQL localement dans un conteneur Docker isolé :

```bash
docker compose -f docker-compose-dev.yaml up -d
```

Pour vérifier son état d'exécution et les logs :

```bash
docker compose -f docker-compose-dev.yaml ps
docker compose -f docker-compose-dev.yaml logs -f
```

La base de données sera disponible sur `localhost:5436` (ou le port défini par `POSTGRES_PORT`) avec les identifiants configurés dans `.env` :
```env
POSTGRES_PORT=5436
DATABASE_URL=postgresql+asyncpg://slack2tchap:postgres_dev_password@localhost:5436/slack2tchap_dev
```

---

## 3. Schéma de Base de Données

### Table `users`
Stocke les comptes utilisateurs et administrateurs du système :

| Colonne | Type | Description |
|---|---|---|
| `id` | `UUID` (PK) | Identifiant unique généré (UUIDv4) |
| `email` | `VARCHAR(255)` (UNIQUE, INDEX) | Adresse email normalisée en minuscules |
| `api_key_hash` | `VARCHAR(64)` (UNIQUE, INDEX) | Empreinte SHA-256 de la clé API |
| `api_key_prefix` | `VARCHAR(32)` | Préfixe non sensible (ex: `s2t_live_a1b2...`) pour affichage |
| `is_admin` | `BOOLEAN` | Droit d'administration (création d'utilisateurs, gestion globale) |
| `is_active` | `BOOLEAN` | Statut du compte (permet la révocation immédiate) |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | Date de création UTC |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | Date de dernière mise à jour UTC |

### Table `webhooks`
Stocke les destinations de routage des alertes :

| Colonne | Type | Description |
|---|---|---|
| `id` | `UUID` (PK) | UUID public aléatoire utilisé dans l'URL publique `/slack/{id}` |
| `name` | `VARCHAR(255)` | Nom descriptif (ex: `Alertmanager Prod`) |
| `matrix_room_id` | `VARCHAR(255)` | Identifiant de salon Matrix (`!room:server` ou `#alias:server`) |
| `user_id` | `UUID` (FK -> `users.id`) | Propriétaire du webhook (suppression en cascade) |
| `custom_matrix_user_id` | `VARCHAR(255)` (NULLABLE) | Matrix ID d'un bot dédié optionnel |
| `encrypted_matrix_password` | `TEXT` (NULLABLE) | Mot de passe chiffré au repos via AES-256-GCM |
| `encrypted_matrix_token` | `TEXT` (NULLABLE) | Jeton d'accès chiffré au repos via AES-256-GCM |
| `encryption_nonce` | `VARCHAR(64)` (NULLABLE) | Nonce unique 96-bit (Base64) utilisé pour le chiffrement |
| `is_active` | `BOOLEAN` | Activation/désactivation du webhook |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | Date de création UTC |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | Date de dernière mise à jour UTC |

---

## 4. Migrations Automatiques au Démarrage (`Auto-Upgrade`)

Au démarrage du serveur FastAPI (dans le gestionnaire de cycle de vie `lifespan` de `main.py`) :

1. L'application charge les `Settings`.
2. Le module [`migrator.py`](file:///Users/nsagon/Projects/beta/tchap-webhook-gateway/src/slack2tchap/infrastructure/database/migrator.py) invoque la commande Alembic :
   ```python
   command.upgrade(alembic_cfg, "head")
   ```
3. Cela garantit que la base de données est systématiquement à jour avec la dernière révision de schéma, sans nécessiter de script de déploiement manuel dans les conteneurs ou environnements de production.

---

## 5. Seeding Automatique de l'Administrateur par Défaut

Le premier démarrage applique la migration initiale [`alembic/versions/0001_initial_schema.py`](file:///Users/nsagon/Projects/beta/tchap-webhook-gateway/alembic/versions/0001_initial_schema.py).

Si les variables `ADMIN_API_KEY` et `ADMIN_EMAIL` sont configurées dans votre `.env` :
1. Alembic extrait la clé en clair fournie.
2. Il calcule son hash `SHA-256` et son préfixe public.
3. Il insère l'utilisateur administrateur en base de données.
4. **La clé en clair n'est jamais écrite sur le disque ou en base de données**, respectant les principes de Zero-Trust.

---

## 6. Commandes Utiles Alembic

### Créer une nouvelle migration après modification des modèles ORM :

```bash
uv run alembic revision --autogenerate -m "description_du_changement"
```

### Appliquer manuellement les migrations vers la dernière version :

```bash
uv run alembic upgrade head
```

### Revenir en arrière d'une révision :

```bash
uv run alembic downgrade -1
```

### Consulter l'historique et la version courante :

```bash
uv run alembic current
uv run alembic history --verbose
```
