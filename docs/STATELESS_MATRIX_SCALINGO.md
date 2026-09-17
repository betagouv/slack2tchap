# Architecture Stateless : Chiffrement Matrix E2EE sur Scalingo

Ce document décrit l'architecture **100% Stateless** conçue pour exécuter `slack2tchap` sur une plateforme PaaS telle que **Scalingo** (ou Kubernetes sans volume persistant) tout en garantissant l'intégrité absolue du chiffrement de bout en bout (**E2EE Olm/Megolm**) de Matrix.

---

## 1. Le Défi des Conteneurs Éphémères avec Matrix E2EE

Sur **Scalingo**, les dynos/conteneurs sont éphémères :
- À chaque redémarrage automatique, crash ou nouveau déploiement git, le système de fichiers local du conteneur est intégralement détruit.
- Or, la bibliothèque **`matrix-nio[e2e]`** repose sur un store de clés local (base SQLite `matrix-nio.db`) contenant :
  1. Les clés d'identité cryptographiques privées (`Ed25519` et `Curve25519`) associées au `device_id`.
  2. Les sessions de chiffrement de groupe Megolm partagées avec les membres des salons Tchap.
  3. Les jetons de synchronisation (`sync_token`).

### Conséquences d'un conteneur éphémère sans persistance :
1. **Conflit de clés d'appareil** : Si le bot redémarre avec le même `device_id` mais des clés locales régénérées, le homeserver Matrix / Tchap rejette la signature cryptographique.
2. **Prolifération d'appareils fantômes** : Si le bot crée un nouveau `device_id` à chaque boot, le compte bot accumule des dizaines d'appareils inconnus sur Tchap, rendant les salons chiffrés inaccessibles ("Unverified device").
3. **Impossibilité d'émettre des alertes continues**.

---

## 2. La Solution : Persistance du Crypto-Store dans PostgreSQL

Puisque Scalingo fournit un addon **PostgreSQL persistant**, `slack2tchap` transforme le stockage local en **cache temporaire synchronisé avec PostgreSQL** :

```text
                                  ┌───────────────────────────────┐
                                  │      PostgreSQL Scalingo      │
                                  │  (Table `matrix_accounts`)    │
                                  │  - device_id (stable)         │
                                  │  - crypto_store_blob (BYTEA)  │
                                  └──────────────┬────────────────┘
                                                 │
                                ┌────────────────┴────────────────┐
                                │ Au démarrage du conteneur / bot │
                                │ (Restauration de l'archive)     │
                                ▼                                 ▼
                   ┌─────────────────────────┐       ┌─────────────────────────┐
                   │ Dyno Scalingo Éphémère  │       │ Dyno Scalingo Éphémère  │
                   │ /tmp/matrix_stores/bot1 │       │ /tmp/matrix_stores/bot2 │
                   │   - matrix-nio.db       │       │   - matrix-nio.db       │
                   └────────────┬────────────┘       └────────────┬────────────┘
                                │                                 │
                                └────────────────┬────────────────┘
                                                 │
                                │ Périodiquement / au shutdown   │
                                │ (Archivage tar.gz -> BYTEA)     │
                                ▼                                 │
                                  ┌───────────────────────────────┐
                                  │ Sauvegarde de l'état E2EE en  │
                                  │ base de données PostgreSQL    │
                                  └───────────────────────────────┘
```

---

## 3. Implémentation Détaillée

### A. Restauration au Démarrage ([`MatrixClientManager`](../slack2tchap/src/slack2tchap/infrastructure/matrix/manager.py))
Lorsqu'un bot Matrix est sollicité :
1. Le gestionnaire vérifie s'il existe une archive dans `matrix_accounts.crypto_store_blob`.
2. Si oui, il décompresse l'archive `tar.gz` directement dans le dossier temporaire `/tmp/matrix_stores/{account_id}/`.
3. `matrix-nio` initialise sa session : il retrouve instantanément son identité, ses clés Olm privées et ses sessions Megolm.
4. Aucun nouvel appareil n'est créé sur le homeserver Tchap.

### B. Sauvegarde Sécurisée vers PostgreSQL
1. Au premier démarrage d'un bot (après négociation des clés initiales) : le dossier `/tmp` est compressé en mémoire et persisté dans `matrix_accounts.crypto_store_blob`.
2. Lors de l'arrêt gracieux du conteneur (signal `SIGTERM` envoyé par Scalingo lors d'un restart ou redéploiement) :
   - Le cycle de vie FastAPI [`lifespan`](../slack2tchap/src/slack2tchap/main.py#L23-L78) intercepte l'arrêt.
   - Il compresse le store de chaque bot actif et met à jour PostgreSQL avant de libérer les connexions.

---

## 4. Avantages pour la Production sur Scalingo

- **100% Stateless** : Aucun volume disque persistant hôte requis (`docker-compose-dev.yaml` ou Scalingo n'ont besoin d'aucun montage `/data`).
- **Multi-Bot Natif** : Plusieurs comptes bots peuvent cohabiter, chacun avec son propre sous-répertoire `/tmp/matrix_stores/{id}` et sa propre ligne en base.
- **Zéro fuite d'appareils** : Un `device_id` unique et stable est attribué par bot et conservé pour toujours.
- **Résilience aux pannes** : Même en cas de `kill -9` brutal, le bot redémarre avec le dernier état sauvegardé en base de données sans corrompre les clés de salon.
