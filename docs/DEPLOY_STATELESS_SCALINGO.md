# Déploiement de `slack2tchap-stateless` sur Scalingo

Ce guide détaille pas-à-pas la procédure pour déployer la version **100% Stateless** de `slack2tchap` sur la plateforme PaaS **Scalingo**.

---

## 🎯 Caractéristiques de l'Édition Stateless

- **ZÉRO base de données** : Aucun addon PostgreSQL, MySQL ou Redis n'est nécessaire.
- **Coût minimal** : Tourne sur un simple conteneur web Scalingo (taille `S` ou `M`).
- **Zéro persistance** : La configuration et les identifiants Matrix sont chiffrés en **AES-256-GCM** dans l'URL du webhook (`?param=...`).
- **Idéal pour** : Alertmanager, Grafana, GitLab, GitHub, scripts CI/CD souhaitant envoyer des alertes vers des salons publics ou privés Tchap / Matrix.

---

## 📋 Prérequis

1. Avoir un compte [Scalingo](https://scalingo.com).
2. Avoir installé la [CLI Scalingo](https://doc.scalingo.com/cli) et s'être authentifié :
   ```bash
   scalingo login
   ```
3. Avoir une clé secrète de chiffrement maître de 256 bits (générée aléatoirement).

---

## 🚀 Étape 1 : Créer l'Application Scalingo

Depuis votre terminal, à la racine du dépôt :

```bash
# Choisir un nom unique pour votre passerelle stateless
APP_NAME="slack2tchap-stateless"

# Créer l'application sur la région osc-fr1 (France)
scalingo create "$APP_NAME" --region osc-fr1
```

---

## ⚙️ Étape 2 : Configurer les Variables d'Environnement

Configurez les variables requises sur Scalingo.

> [!IMPORTANT]
> **Deux variables indispensables pour le monorepo :**
> 1. **`PROJECT_DIR=slack2tchap-stateless`** : Isole le sous-projet. Scalingo ne compile et n'embarque dans le slug que le micro-service stateless, excluant ainsi tout le code mort (PostgreSQL, Alembic, tests, etc.).
> 2. **`UV_NO_EDITABLE=1`** : Ordonne à `uv` de compiler et copier physiquement le paquet local `slack2tchap-core` dans le virtualenv plutôt que d'utiliser des liens symboliques (incompatibles avec les slugs Scalingo).

### 1. Générer la clé de chiffrement maître (256-bit hex)

```bash
SECRET_KEY=$(openssl rand -hex 32)
echo "Conservez précieusement cette clé : $SECRET_KEY"
```

### 2. Injecter les variables dans l'application Scalingo

```bash
# Isoler uniquement le sous-dossier stateless (zéro code mort dans le conteneur)
scalingo -a "$APP_NAME" env-set PROJECT_DIR=slack2tchap-stateless

# Activer la copie physique des dépendances uv du monorepo
scalingo -a "$APP_NAME" env-set UV_NO_EDITABLE=1

# Mode production
scalingo -a "$APP_NAME" env-set ENVIRONMENT=production

# Clé secrète de chiffrement AES-256-GCM
scalingo -a "$APP_NAME" env-set SECRET_ENCRYPTION_KEY="$SECRET_KEY"

# URL publique de votre passerelle (pour le générateur de tokens)
scalingo -a "$APP_NAME" env-set PUBLIC_BASE_URL="https://${APP_NAME}.osc-fr1.scalingo.io"

# Homeserver Matrix / Tchap par défaut
scalingo -a "$APP_NAME" env-set MATRIX_HOMESERVER="https://matrix.agent.tchap.gouv.fr"
```

---

## 📦 Étape 3 : Déployer le Code
 
Grâce à `PROJECT_DIR=slack2tchap-stateless`, Scalingo se positionne directement dans le dossier `slack2tchap-stateless/` qui contient :
- Son propre `Procfile` :
  ```text
  web: uvicorn slack2tchap_stateless.main:app --host 0.0.0.0 --port $PORT
  ```
- Son propre `.python-version` (`3.12`) et `.buildpacks`.
- Son fichier de verrouillage `uv.lock`.

Ajoutez le remote Git de Scalingo et poussez votre branche `main` :

```bash
# Ajouter le remote Git Scalingo
git remote add scalingo "git@ssh.osc-fr1.scalingo.com:${APP_NAME}.git"

# Déployer
git push scalingo main
```

Scalingo va :
1. Détecter `PROJECT_DIR=slack2tchap-stateless` et s'y déplacer.
2. Détecter automatiquement `uv.lock` et `.python-version`.
3. Installer `uv` et exécuter `uv sync` (en compilant physiquement `slack2tchap-core` grâce à `UV_NO_EDITABLE=1`).
4. Préparer le conteneur `web` allégé (aucun fichier de base de données ni de dépendance superflue).
5. Démarrer Uvicorn sur le port dynamique alloué par Scalingo (`$PORT`).

---

## ✅ Étape 4 : Vérification et Test de Santé

Vérifiez le bon démarrage du service :

```bash
# Consulter les logs en temps réel
scalingo -a "$APP_NAME" logs --follow
```

Vous devez observer :
```text
Starting slack2tchap-stateless gateway v1.0.0 in production mode (zero database)
Uvicorn running on http://0.0.0.0:xxxx (Press CTRL+C to quit)
Application startup complete.
```

Testez l'endpoint de santé :

```bash
curl -i "https://${APP_NAME}.osc-fr1.scalingo.io/health"
```

Réponse attendue (`200 OK`) :
```json
{"status":"healthy","mode":"stateless"}
```

---

## 🔗 Étape 5 : Générer les Webhooks Chiffrés pour vos Équipes

Une fois l'application déployée, chaque équipe ou service souhaitant recevoir des alertes Slack vers un salon Tchap peut générer son URL sécurisée grâce au script dédié :

```bash
uv run python slack2tchap-stateless/scripts/generate_stateless_url.py \
    --username '@mon-bot:agent.tchap.gouv.fr' \
    --password 'MotDePasseDuBot' \
    --channel '!id_du_salon:agent.tchap.gouv.fr' \
    --secret-key "$SECRET_KEY" \
    --base-url "https://${APP_NAME}.osc-fr1.scalingo.io"
```

Le script retourne une URL de ce type :
```text
https://slack2tchap-stateless.osc-fr1.scalingo.io/slack?param=eyJpdiI6ICIuLi4iLCAiY3lwaGVydGV4dCI6ICIuLi4iLCAidGFnIjogIi4uLiJ9
```

Cette URL peut être renseignée directement dans **Alertmanager**, **Grafana**, **GitLab Webhooks**, etc., avec le payload format Slack habituel.

---

## 🛠️ Commandes Utiles de Maintenance

| Action | Commande |
| :--- | :--- |
| Voir les logs | `scalingo -a $APP_NAME logs --follow` |
| Redémarrer l'application | `scalingo -a $APP_NAME restart` |
| Voir les variables d'environnement | `scalingo -a $APP_NAME env` |
| Ajuster les conteneurs | `scalingo -a $APP_NAME scale web:1:M` |
| Ouvrir dans le navigateur | `scalingo -a $APP_NAME open` |
