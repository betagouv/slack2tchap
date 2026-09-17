# Guide Technique : Chiffrement Réversible Authentifié au Repos (AES-256-GCM)

Ce document explique comment `slack2tchap` permet aux administrateurs de déclarer des identifiants personnalisés de compte bot Matrix (mot de passe ou access token) pour des webhooks spécifiques, tout en garantissant une protection cryptographique maximale en base de données.

---

## 1. La Problématique : Hachage vs Chiffrement Réversible

Dans une architecture logicielle sécurisée :

- **Pour les mots de passe et clés d'API utilisateurs** : On utilise le **hachage à sens unique** (SHA-256 ou Argon2id). Le serveur n'a jamais besoin de relire le mot de passe en clair : il se contente de comparer le hash de l'entrée avec le hash stocké.
- **Pour les identifiants tiers (Compte Bot Matrix)** : Le serveur **doit impérativement transmettre le mot de passe ou le jeton en clair au homeserver Matrix / Tchap** via HTTP pour ouvrir la session. Le hachage est donc inapplicable : nous avons besoin d'un **chiffrement réversible au repos**.

---

## 2. Algorithme Retenu : AES-256-GCM (AEAD)

Pour chiffrer ces secrets, `slack2tchap` implémente **AES-256 en mode GCM** (Galois/Counter Mode) :

```text
                                  ┌──────────────────────┐
    Plaintext (Secret Matrix) ──> │                      │ ──> Ciphertext (Base64)
    Clé Maîtresse (256-bit)   ──> │      AES-256-GCM     │
    Nonce Unique (96-bit)     ──> │  (Chiffrement AEAD)  │ ──> Authentication Tag (128-bit)
                                  └──────────────────────┘
```

### Pourquoi AES-256-GCM ?

1. **Confidentialité forte (AES-256)** :
   Le chiffrement symétrique standard de référence recommandé par l'ANSSI, le NIST et l'ISO.
2. **Authenticité et Intégrité (Mode AEAD)** :
   Le mode GCM génère un tag d'authentification cryptographique de 128 bits. Si un attaquant modifie un seul bit du ciphertext ou tente d'injecter une charge malveillante directement dans la base de données PostgreSQL, **le déchiffrement échoue immédiatement** en levant une exception `CipherError` sans compromettre les clés.
3. **Performance matérielle** :
   Accéléré nativement sur les processeurs modernes via les instructions matérielles `AES-NI` / `ARMv8 Crypto Extensions`.

---

## 3. Gestion du Nonce / Vecteur d'Initialisation (IV)

Une règle fondamentale du mode GCM est qu'**un couple (Clé, Nonce) ne doit JAMAIS être réutilisé**, sous peine d'effondrement de la sécurité cryptographique.

Dans [`slack2tchap-core/src/slack2tchap_core/infrastructure/security/cipher.py`](../slack2tchap-core/src/slack2tchap_core/infrastructure/security/cipher.py) :
- À **chaque** opération de chiffrement, un nouveau nonce aléatoire de **96 bits (12 octets)** est généré via le générateur système cryptographiquement sûr (`os.urandom(12)`).
- Ce nonce public est encodé en Base64 et persisté dans la colonne `encryption_nonce` de la table `webhooks`.
- Le ciphertext produit contient le texte chiffré et son tag d'authentification.

---

## 4. Gestion de la Clé Maîtresse

La clé maîtresse est configurée dans le fichier d'environnement `.env` :

```env
SECRET_ENCRYPTION_KEY=une_cle_maitresse_robuste_et_secrete_d_au_moins_32_caracteres
```

- L'application dérive de manière déterministe une clé brute de 32 octets (256 bits) à partir de ce secret grâce à PBKDF2-HMAC-SHA256 (100 000 itérations avec sel applicatif).
- La clé maîtresse n'est **jamais stockée dans la base de données PostgreSQL**.
- En environnement conteneurisé ou Kubernetes, cette variable doit être injectée via un secret dédié (K8s Secret, HashiCorp Vault, AWS Secrets Manager, Scaleway Secret Manager).

---

## 5. Exemple de Flux End-to-End

### Création du Webhook (Chiffrement)
1. L'administrateur appelle `POST /api/v1/admin/webhooks` avec :
   ```json
   {
     "name": "Supervision Serveurs Sensibles",
     "matrix_room_id": "!salon_secret:agent.tchap.gouv.fr",
     "custom_matrix_user_id": "@bot-supervision:agent.tchap.gouv.fr",
     "custom_matrix_password": "MotDePasseTresSecretDuBot"
   }
   ```
2. Le Use Case [`CreateWebhookUseCase`](../slack2tchap/src/slack2tchap/application/use_cases.py) fait appel à [`AesGcmSecretCipher.encrypt()`](../slack2tchap-core/src/slack2tchap_core/infrastructure/security/cipher.py#L25).
3. Le mot de passe est chiffré.
4. En base de données PostgreSQL, les champs enregistrés sont :
   - `custom_matrix_user_id`: `@bot-supervision:agent.tchap.gouv.fr`
   - `encrypted_matrix_password`: `4dK9q...` (Base64)
   - `encryption_nonce`: `8J2vL...` (Base64)
   - `encrypted_matrix_token`: `NULL`

### Réception d'une alerte publique (Déchiffrement)
1. Un système de supervision envoie un webhook à `POST /webhook/slack/{webhook_id}`.
2. Le Use Case [`ProcessPublicWebhookUseCase`](../slack2tchap/src/slack2tchap/application/use_cases.py) extrait la ligne correspondante dans la table `webhooks`.
3. Il utilise le nonce et le ciphertext pour déchiffrer en mémoire vive le mot de passe via [`AesGcmSecretCipher.decrypt()`](../slack2tchap-core/src/slack2tchap_core/infrastructure/security/cipher.py#L40).
4. Le secret déchiffré n'est jamais consigné dans les logs et est immédiatement utilisé pour initialiser ou réutiliser la session Matrix.
