# Guide de Sécurité : Génération, Hachage et Stockage des Clés d'API

Ce document expose les principes cryptographiques et les bonnes pratiques de l'industrie (RFC, NIST, standards Stripe/GitHub) appliqués dans `slack2tchap` pour la gestion des clés API.

---

## 1. Pourquoi les Clés API diffèrent des Mots de Passe Humains

Une erreur courante de conception consiste à traiter les clés API comme des mots de passe utilisateurs :

| Critère | Mot de Passe Humain | Clé d'API Machine |
|---|---|---|
| **Entropie** | Très faible (souvent < 40 bits). Les humains choisissent des motifs prévisibles. | **Maximale (256 bits)** de vrai aléatoire cryptographique (`secrets.token_urlsafe(32)`). |
| **Vulnérabilité aux attaques par dictionnaire** | **Élevée**. Nécessite des fonctions d'étirement de clé lentes (**Argon2id**, **bcrypt**, **PBKDF2**) pour ralentir le GPU des attaquants. | **Nulle**. L'espace de recherche ($2^{256}$ combinaisons) est mathématiquement infaisable à attaquer par brute-force, même avec tous les ordinateurs de la Terre pendant des siècles. |
| **Algorithme de hachage recommandé** | Argon2id ou bcrypt avec coût CPU/RAM élevé. | **SHA-256 à sens unique** (recommandation officielle Stripe, GitHub Tokens, AWS Access Keys). |
| **Impact sur la latence du serveur** | Un login humain peut prendre 200ms sans problème. | Chaque requête API passe par l'authentification : un hachage lent pénaliserait le débit de requêtes. **SHA-256 s'exécute en < 1 µs**. |

---

## 2. Anatomie d'une Clé API Sécurisée dans slack2tchap

Une clé d'API générée par `slack2tchap` respecte la structure suivante :

```text
 s2t_live_m7m8eI6a8AXfqqfkZHKVLQlmL9U8F08axYlK5Zhd-S8
 └───────┘└─────────────────────────────────────────┘
  Préfixe        Partie secrète à 256 bits d'entropie
  public           (générée par /dev/urandom)
```

1. **Préfixe reconnaissable (`s2t_live_`)** :
   - Permet l'analyse statique de fuite de secrets (Secret Scanning par GitHub / GitGuardian / TruffleHog).
   - Indique l'environnement (`live` vs `test`).
2. **Entropie cryptographique** :
   - Généré via `secrets.token_urlsafe(32)` de la bibliothèque standard Python, alimenté par le CSPRNG de l'OS (`/dev/urandom` ou `getrandom(2)`).
3. **Préfixe d'affichage public (`Key Hint`)** :
   - Seuls les 12 premiers caractères sont stockés en clair (ex: `s2t_live_m7m8...`) pour permettre à l'administrateur d'identifier visuellement sa clé dans les logs ou interfaces sans jamais exposer le secret.

---

## 3. Stockage Sécurisé en Base de Données

> [!CAUTION]
> **Règle absolue : La clé en clair n'est JAMAIS stockée dans la base de données.**

Lors de la création ou du seeding de la clé :
```python
raw_key = "s2t_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
api_key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
api_key_prefix = raw_key[:12] + "..."
```

La base de données ne persiste que :
- `api_key_hash` : 64 caractères hexadécimaux (empreinte SHA-256 irréversible).
- `api_key_prefix` : chaîne tronquée non sensible pour affichage.

Si la base de données venait à faire l'objet d'un dump non autorisé, les attaquants ne posséderaient **aucun moyen de recalculer les clés en clair** pour appeler les APIs.

---

## 4. Vérification à l'Exécution & Protection contre les Attaques Temporelles (Timing Attacks)

Lorsqu'un client admin appelle l'API avec le header `X-API-Key: s2t_live_...` :

1. Le serveur calcule le hash SHA-256 de la clé reçue :
   ```python
   incoming_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
   ```
2. Il effectue une requête indexée $O(1)$ dans la table `users` sur la colonne `api_key_hash`.
3. Pour la vérification en mémoire, il utilise une comparaison en temps constant :
   ```python
   hmac.compare_digest(incoming_hash, user.api_key_hash)
   ```
   Cela neutralise toute tentative de déduction de caractères par mesure de nanosecondes de temps de réponse.

---

## 5. Utilisation du Script Autonome de Génération

Pour générer une nouvelle clé d'API sans toucher à la base :

```bash
uv run python scripts/generate_api_key.py
```

Résultat :
```text
================================================================
🔑  NOUVELLE CLÉ API SÉCURISÉE GÉNÉRÉE (slack2tchap)
================================================================

Clé API en clair  : s2t_live_m7m8eI6a8AXfqqfkZHKVLQlmL9U8F08axYlK5Zhd-S8
Préfixe public    : s2t_live_m7m8...
Empreinte SHA-256 : 7a14ef8369cf55f03e70c23809fdd4a70d950c6c1d7e193adbd29ad15eca795b

----------------------------------------------------------------
⚠️   IMPORTANT :
Cette clé en clair ne sera plus JAMAIS affichée.
Copiez-la immédiatement dans votre fichier .env :
----------------------------------------------------------------

ADMIN_API_KEY=s2t_live_m7m8eI6a8AXfqqfkZHKVLQlmL9U8F08axYlK5Zhd-S8
ADMIN_EMAIL=admin@tchap.gouv.fr
================================================================
```
