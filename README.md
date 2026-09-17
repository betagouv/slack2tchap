# slack2tchap — Monorepo Passerelle Webhook Matrix / Tchap

Passerelle sécurisée et performante entre les webhooks entrants au format **Slack / Mattermost** (Alertmanager Prometheus, Grafana, GitLab, GitHub Actions, Sentry, Datadog...) et la messagerie souveraine **Matrix / Tchap**.

Ce dépôt est structuré en **monorepo `uv`** composé de 2 micro-services indépendants et d'une bibliothèque de domaine partagée :

```
tchap-webhook-gateway/
├── slack2tchap-core/        # 📦 Bibliothèque commune (Domain, AES-GCM, Parsers, CLI)
├── slack2tchap-stateless/   # ⚡ Micro-service 100% Stateless (sans DB, bot à la volée)
├── slack2tchap/             # 🗄️ Passerelle Stateful (PostgreSQL/SQLite, E2EE, RBAC)
├── scripts/                 # 🔨 Script de compilation globale des binaires
└── .github/workflows/       # 🤖 CI/CD (Lint, Types, Tests 3 projets, Binaires)
```

---

## 🧭 Quel sous-projet utiliser ?

| Besoin | Projet recommandé | Base de données requise | Chiffrement salon |
|---|---|---|---|
| Déploiement ultra-léger, zéro base de données, salon d'alerte non chiffré | **`slack2tchap-stateless`** | ❌ Aucune (Zéro DB) | Messages en clair (`m.room.message`) |
| Multi-équipes, gestion multi-bots, salons Tchap chiffrés de bout en bout (E2EE) | **`slack2tchap`** | ✅ PostgreSQL ou SQLite | ✅ Olm / Megolm + SAS (émojis) |
| Bibliothèque Python, fonctions crypto partagées ou CLI de manipulation de tokens | **`slack2tchap-core`** | ❌ Aucune | — |

Consultez le README spécifique de chaque sous-projet pour les instructions détaillées :
- 📖 [Documentation slack2tchap-stateless](slack2tchap-stateless/README.md)
- 📖 [Documentation slack2tchap (Standard/Stateful)](slack2tchap/README.md)
- 📖 [Documentation slack2tchap-core](slack2tchap-core/README.md)

---

## 🚀 Démarrage rapide (Monorepo)

Le monorepo est exclusivement géré avec **[uv](https://docs.astral.sh/uv/)**.

### 1. Installation des dépendances

```bash
uv sync
```

Cette commande synchronise automatiquement les environnements virtuels et interconnecte les 3 projets en mode éditable.

---

## 🧪 Qualité de code & Tests

Toutes les commandes s'exécutent depuis la racine du monorepo et couvrent les 3 sous-projets :

### Exécuter les tests unitaires et d'intégration
```bash
uv run pytest
```
*(98 tests automatisés couvrant le cœur métier, le chiffrement, les parsers, les routes stateless et l'API stateful).*

### Vérifier le linting et le formatage
```bash
uv run ruff check .
uv run ruff format --check .
```

### Vérifier le typage statique strict
```bash
uv run pyright
```

---

## 🔨 Compilation des binaires autonomes (PyInstaller)

Chaque composant peut être compilé en binaire autonome ne nécessitant aucun runtime Python sur le serveur cible :

### Compiler les 3 binaires en une seule commande :
```bash
./scripts/build_binaries.sh
```

Les 3 exécutables standalone sont générés dans le dossier `dist/` :
- `dist/slack2tchap-core` : Boîte à outils CLI (chiffrement, déchiffrement de tokens, hachage de clés).
- `dist/slack2tchap-stateless` : Serveur web FastAPI stateless prêt au déploiement sans base de données.
- `dist/slack2tchap` : Serveur web FastAPI complet avec ORM, migrations automatiques et gestion E2EE.

---

## ☁️ Déploiement sur Scalingo

- **Version Stateless (Zéro base de données)** : Idéal pour déployer rapidement sans aucun coût d'addon de base de données.
  👉 Suivez le guide complet : [docs/DEPLOY_STATELESS_SCALINGO.md](docs/DEPLOY_STATELESS_SCALINGO.md)
---

## 🤖 Pipeline CI/CD GitHub Actions

Le workflow [.github/workflows/ci.yml](.github/workflows/ci.yml) vérifie automatiquement sur chaque commit et Pull Request :
1. **Formatage** : `ruff format --check .`
2. **Linting** : `ruff check .`
3. **Typage** : `pyright`
4. **Tests** : `pytest` avec rapport de couverture
5. **Compilation des binaires** : Génération des 3 exécutables standalone et publication des artefacts téléchargeables.
