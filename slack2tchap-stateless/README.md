# slack2tchap-stateless

Micro-service passerelle webhook **100% Stateless** entre Slack / Mattermost et Matrix / Tchap, **sans aucune dépendance de base de données**.

## 🎯 Pourquoi ce projet ?

Ce micro-service est conçu pour être déployé en quelques secondes avec une empreinte mémoire et CPU minimale :
- **Zéro base de données** : Pas de PostgreSQL, pas de SQLite, pas d'ORM SQLAlchemy, pas d'Alembic.
- **Client Matrix à la volée** : Chaque requête d'alerte instancie un client éphémère en mémoire, s'authentifie, distribue l'alerte dans le salon et détruit immédiatement la session.
- **Sécurité de bout en bout du webhook** : Les identifiants (`username`, `password`, `channelID`) sont encapsulés dans un paramètre d'URL chiffré en **AES-256-GCM**.
- **Salons non chiffrés** : Ne nécessite pas de gestion de trousseau de clés Olm/Megolm ni de persistance sur disque. Idéal pour les salons publics, canaux d'astreinte ou d'alerting d'équipes.

---

## 🔒 Schéma de chiffrement AES-256-GCM

L'URL d'ingestion a la structure suivante :
```
POST https://gateway.domaine.fr/slack?param=<TOKEN_CHIFFRÉ>
```

Le paramètre `param` est construit comme suit :
1. **Données claires** : JSON contenant `{"username": "@bot:agent.tchap.gouv.fr", "password": "...", "channelID": "!room:agent.tchap.gouv.fr"}`.
2. **Chiffrement AEAD** : Chiffré avec la clé secrète `SECRET_ENCRYPTION_KEY` du serveur (256 bits).
3. **Nonce & Tag** : Chaque token intègre un vecteur d'initialisation aléatoire de 96 bits (`os.urandom(12)`) et un tag d'intégrité de 128 bits.
4. **Encodage URL-Safe** : La charge binaire `[Nonce 12B] + [Ciphertext] + [Tag 16B]` est encodée en **URL-safe Base64** sans padding. Toute altération est rejetée avec un code HTTP 400.

---

## 🛠️ Génération de votre URL Stateless

Un script interactif est fourni dans le dossier `scripts/` :

> [!TIP]
> Dans **zsh** (macOS), le point d'exclamation `!` déclenche l'expansion d'historique s'il est entre guillemets doubles. Utilisez des **guillemets simples `'...'`** ou le mode interactif.

```bash
# Mode interactif (sans arguments, mot de passe masqué) :
uv run python scripts/generate_stateless_url.py

# Ou avec arguments en ligne de commande :
uv run python scripts/generate_stateless_url.py \
  --username '@mon-bot:agent.tchap.gouv.fr' \
  --password 'MotDePasseSecret' \
  --channel '!mon_salon:agent.tchap.gouv.fr' \
  --secret-key 'ma_cle_secrete_256_bits' \
  --base-url 'https://slack2tchap.mon-domaine.fr'
```

Le script produit l'URL prête à être renseignée dans Grafana, Alertmanager, GitLab ou GitHub Actions :
`https://slack2tchap.mon-domaine.fr/slack?param=eyJhbGciOi...`

---

## 🚀 Démarrage rapide

### 1. Variables d'environnement (`.env`)

Générez une clé de chiffrement maître de 256 bits (32 octets aléatoires) :
```bash
# Avec OpenSSL (recommandé) :
openssl rand -hex 32

# Ou avec Python / uv :
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Configurez votre fichier `.env` :

```env
# Clé maîtresse de chiffrement AES-256-GCM générée ci-dessus
SECRET_ENCRYPTION_KEY=a1b2c3d4e5f6... (valeur générée)
ENVIRONMENT=production
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
MATRIX_HOMESERVER=https://matrix.agent.tchap.gouv.fr
MATRIX_AUTO_JOIN=true
```

### 2. Lancement local avec `uv`

```bash
uv run uvicorn slack2tchap_stateless.main:app --host 0.0.0.0 --port 8000
```

### 3. Compilation en binaire autonome (PyInstaller)

```bash
uv run pyinstaller --onefile --name slack2tchap-stateless src/slack2tchap_stateless/main.py
```

Le binaire standalone produit dans `dist/slack2tchap-stateless` fonctionne sans Python installé sur la machine cible !

---

## 📡 Routes HTTP exposées

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/health` | Vérification de bonne santé (`{"status": "healthy", "mode": "stateless"}`) |
| `POST` | `/slack?param=...` | Point d'ingestion principal du webhook Slack |
| `POST` | `/webhook/slack?param=...` | Alias d'ingestion |

### Exemple d'appel d'alerte (cURL)

```bash
curl -X POST "http://localhost:8000/slack?param=<VOTRE_TOKEN_CHIFFRÉ>" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Alerte de supervision",
    "attachments": [
      {
        "color": "danger",
        "title": "CPU Overload",
        "title_link": "https://grafana.domaine.fr",
        "text": "Utilisation CPU > 95% sur node-01",
        "fields": [
          {"title": "Environnement", "value": "Production", "short": true},
          {"title": "Seuil", "value": "95%", "short": true}
        ],
        "footer": "Prometheus Alertmanager"
      }
    ]
  }'
```

---

## 🧪 Lancer les tests

```bash
uv run pytest tests/
```
