<p align="center"><img src="config/element/kibare/logo.png" alt="Logo Kibaré" width="120"></p>

# Kibaré — la messagerie souveraine de l'administration

> Sprint technique pré-hackathon 2026 — MTDPCE / DGTD · Licence **AGPL-3.0**

Kibaré (« les nouvelles », en mooré) est une messagerie instantanée réservée aux **agents publics enrôlés**. Elle gère les
conversations privées, les groupes et l'envoi de fichiers, avec un **chiffrement de bout en bout imposé partout**. Elle
s'installe en **une seule commande** sur l'infrastructure de l'État et ne dépend d'**aucun service tiers** : ni Google, ni
Apple, ni matrix.org, ni aucun nuage étranger.

---

## Sommaire
1. [Le besoin](#1-le-besoin)
2. [Fonctionnalités](#2-fonctionnalités)
3. [Architecture](#3-architecture)
4. [Sécurité](#4-sécurité)
5. [Installation](#5-installation)
6. [Configuration](#6-configuration)
7. [Guide d'utilisation](#7-guide-dutilisation)
8. [Scénario de démonstration](#8-scénario-de-démonstration)
9. [Tests et vérifications](#9-tests-et-vérifications)
10. [Structure du dépôt](#10-structure-du-dépôt)
11. [Exploitation](#11-exploitation)
12. [Dépannage](#12-dépannage)
13. [Passage en production](#13-passage-en-production)
14. [Limites connues](#14-limites-connues)
15. [Technologies et licences](#15-technologies-et-licences)

---

## 1. Le besoin
Beaucoup d'échanges de service passent aujourd'hui par des messageries grand public. Les données y sont hébergées hors du
pays, les comptes ne sont pas liés à l'identité professionnelle de l'agent, et rien ne permet de couper l'accès d'un agent
qui perd son téléphone ou quitte son poste.

Kibaré répond à ces trois problèmes :

| Problème | Réponse de Kibaré |
|---|---|
| Données hébergées à l'étranger | Tout tourne sur les serveurs de l'État. La fédération Matrix est coupée. |
| N'importe qui peut créer un compte | Seuls les agents **enrôlés** par un administrateur peuvent se connecter, avec mot de passe **et** code TOTP. |
| Impossible de couper un accès | **Révocation en un clic**, sur tous les appareils de l'agent, tracée dans un journal d'audit. |
| Le serveur peut lire les messages | Chiffrement de bout en bout : le serveur ne stocke que des données chiffrées. Un script le prouve. |

**Niveau d'engagement open source : « Étendre et adapter ».** Kibaré s'appuie sur l'écosystème Matrix (serveur Synapse et
client Element), durci pour un usage administratif. L'équipe y ajoute une **console d'administration originale** :
enrôlement, révocation immédiate, annuaire officiel, salons classifiés et journal d'audit.
**Aucune primitive cryptographique n'a été écrite par l'équipe.**

---

## 2. Fonctionnalités

### Pour les agents (client Element, https://localhost)
- Messages privés et groupes, **chiffrés de bout en bout** dans tous les salons, sans exception.
- Envoi de fichiers et d'images, chiffrés par le client avant l'envoi.
- Connexion unique par le portail d'identité de l'administration : mot de passe + code TOTP.
- Annuaire des agents enrôlés, avec leur nom et leur fonction.
- Interface en français. Les fonctions qui fuient des données sont désactivées : aperçus de liens, indicateurs de
  saisie, présence, widgets, intégrations, appels via des serveurs publics.

### Pour les administrateurs (console Kibaré, http://localhost:8090)
| Écran | Rôle |
|---|---|
| **Annuaire** (`/`) | Liste officielle des agents par ministère, avec statut (actif ou révoqué), fonction et rôles. Filtre par ministère. |
| **Enrôlement** (`/agents/nouveau`) | Crée l'agent dans Keycloak et dans Synapse en une seule opération. Le TOTP lui sera demandé à sa première connexion. |
| **Révocation** (bouton dans l'annuaire) | Coupe immédiatement l'accès sur tous les appareils, avec un motif obligatoire : perte ou vol, départ, compromission, fin de mission. |
| **Salons classifiés** (`/salons/nouveau`) | Crée un salon chiffré, sur invitation, avec un niveau de classification, une durée de vie des messages et des modérateurs. |
| **Journal d'audit** (`/journal`) | Trace horodatée de chaque enrôlement, révocation et création de salon, avec son auteur. |

### Niveaux de classification
| Niveau | Expiration automatique des messages | Historique visible des nouveaux membres |
|---|---|---|
| NON PROTÉGÉ | aucune | non, seulement depuis l'arrivée du membre |
| DIFFUSION RESTREINTE | 30 jours | non |
| CONFIDENTIEL | 7 jours | non |

Dans un salon classifié, seuls les modérateurs peuvent inviter. Le compte technique de la console quitte le salon juste
après l'avoir créé. Comme il n'a aucun appareil, il n'a jamais reçu aucune clé de déchiffrement.

---

## 3. Architecture

```
                         ┌──────────────────────── Réseau Docker interne ─────────────────────────┐
 Navigateur / mobile     │                                                                        │
        │                │   ┌──────────────┐   messages CHIFFRÉS    ┌──────────────┐            │
        ▼                │   │ Element Web  │ ─────────────────────► │   Synapse    │──┐         │
 ┌─────────────┐ :8080 ──┼─► │ (client)     │                        │ (Matrix,     │  │         │
 │             │         │   └──────────────┘                        │ sans fédé.)  │  │         │
 │    Caddy    │ :8008 ──┼──────────────────────────────────────────►└──────┬───────┘  │         │
 │  (point     │         │        /_synapse/admin/*  → 403                    │ OIDC     │         │
 │  d'entrée   │ :8180 ──┼─► ┌──────────────┐ ◄───────────────────────────────┘          ▼         │
 │  unique)    │         │   │   Keycloak   │  mot de passe + TOTP, rôles      ┌──────────────┐   │
 │             │         │   └──────┬───────┘  /admin/* → 403                  │  PostgreSQL  │   │
 │             │ :8090 ──┼─► ┌──────┴───────┐                                  │ synapse +    │   │
 └─────────────┘ (hôte   │   │   Console    │ ── API admin Synapse/Keycloak ──►│ keycloak     │   │
                 seul)   │   │   Kibaré     │    (réseau interne uniquement)   └──────────────┘   │
                         │   └──────────────┘                                                    │
                         └────────────────────────────────────────────────────────────────────────┘
```

### Les services
| Service | Image | Rôle | Exposé |
|---|---|---|---|
| `init` | construite depuis `admin-console/` | Génère les secrets (une fois) et produit la configuration à partir des modèles, puis s'arrête. | non |
| `postgres` | `postgres:16.6-alpine` | Bases `synapse` (collation C) et `keycloak`, chacune avec son propre utilisateur. | non |
| `keycloak` | `quay.io/keycloak/keycloak:26.0.7` | Identité : comptes, mot de passe, TOTP obligatoire, rôles, anti-force brute. | via Caddy, `:8180` |
| `synapse` | `ghcr.io/element-hq/synapse:v1.120.0` | Serveur Matrix. Relaie et stocke des messages chiffrés. Fédération coupée. | via Caddy, `:8008` |
| `element` | `vectorim/element-web:v1.11.85` | Client web configuré pour Kibaré (`config/element/config.json`). | via Caddy, `:8080` |
| `console` | construite depuis `admin-console/` | Console FastAPI : enrôlement, révocation, salons, audit. | via Caddy, `127.0.0.1:8090` |
| `proxy` | `caddy:2.8.4-alpine` | Point d'entrée unique. En-têtes de sécurité. Bloque les API d'administration. | `8008`, `8080`, `8180`, `127.0.0.1:8090` |

L'ordre de démarrage est piloté par les *healthchecks* : `init` → `postgres` → `keycloak` → `synapse` → `console` → `proxy`.

### Chiffrement
- Protocoles Matrix **Olm** (entre deux appareils) et **Megolm** (groupes), implémentés par **vodozemac**, la bibliothèque
  Rust de référence, utilisée par Element via son SDK crypto.
- Synapse impose le chiffrement dans tous les salons (`encryption_enabled_by_default_for_room_type: all`).
- Les fichiers sont chiffrés dans le navigateur (AES-CTR). La clé voyage dans le message, lui-même chiffré.
- Les clés privées restent sur les appareils. Le serveur ne voit que des événements `m.room.encrypted`.

### Connexion d'un agent
1. L'agent ouvre Element, qui le redirige vers Synapse puis vers **Keycloak** (OIDC, *authorization code* + **PKCE S256**).
2. Il saisit son mot de passe et son code TOTP. À la première connexion, il enregistre d'abord le TOTP avec FreeOTP ou
   Aegis.
3. Keycloak renvoie un code à Synapse. Synapse l'échange contre un jeton directement sur le réseau interne.
4. Synapse vérifie que le jeton porte le rôle `agent` (`attribute_requirements`). Sans ce rôle, la connexion est refusée.
5. L'agent retrouve le compte Matrix créé pour lui lors de l'enrôlement.

La connexion par mot de passe Matrix, l'inscription libre et l'accès invité sont tous **désactivés** : Keycloak est la seule
porte d'entrée.

### Connexion d'un administrateur à la console
Même principe, avec le client OIDC `kibare-console` : `state` anti-CSRF à usage unique, PKCE S256, échange du code sur le
réseau interne, puis vérification du rôle **`admin`**. La session de la console dure une heure au maximum, et chaque
formulaire est protégé par un jeton CSRF.

### Révocation d'un agent
```
Console ──► Keycloak : compte désactivé + toutes les sessions SSO fermées      (plus aucune reconnexion)
        ──► Synapse  : compte désactivé → tous les appareils et jetons supprimés,
                       retrait de tous les salons
        ──► Registre : statut « révoqué », motif, horodatage + entrée au journal d'audit
```
Les membres restants renouvellent leur clé Megolm au message suivant. L'agent révoqué ne peut donc plus déchiffrer aucun
nouveau message, même s'il a conservé une copie de la base de son appareil.

### Données de la console
La console garde un registre SQLite (`/data/registre.sqlite3`, volume `console_data`) avec deux tables :
- `agents` : identifiant, prénom, nom, ministère, fonction, rôles, statut, dates d'enrôlement et de révocation, motif ;
- `journal` : horodatage UTC, auteur, action, cible, détails.

Le jeton du compte de service Synapse de la console est stocké dans le même volume, avec les droits `0600`.

---

## 4. Sécurité
L'analyse complète se trouve dans **[docs/NOTE_SECURITE.md](docs/NOTE_SECURITE.md)** : menaces, protections, métadonnées
visibles et limites. En résumé :

| Menace | Protection |
|---|---|
| Lecture des messages sur le serveur | Chiffrement de bout en bout imposé, fichiers chiffrés côté client, aucun aperçu de lien. Prouvé par `scripts/verifier-serveur-aveugle.sh`. |
| Personne non enrôlée | Inscription, invités et mot de passe Matrix désactivés. Rôle `agent` exigé. Comptes créés uniquement par la console. |
| Vol de mot de passe | TOTP obligatoire. Blocage progressif après 5 échecs. Mot de passe d'au moins 12 caractères, avec un chiffre et une majuscule, différent de l'identifiant. |
| Téléphone perdu, départ d'un agent | Révocation immédiate sur tous les appareils, tracée au journal. |
| Nouveau membre qui lit l'historique | `history_visibility: joined` dans les salons classifiés. |
| Conservation excessive | Expiration des messages (7 ou 30 jours). IP et messages supprimés conservés 1 jour seulement. |
| Fuite vers des tiers | Fédération coupée, aucun serveur de clés externe, aucun serveur d'identité, aucun widget, aucune notification push Google ou Apple, aucune statistique envoyée. |
| Accès aux API d'administration | Bloquées par Caddy (403). Console limitée à `127.0.0.1`, rôle `admin` + TOTP, CSRF. |
| Secrets dans le dépôt | Aucun. 10 secrets aléatoires générés au premier démarrage et stockés dans un volume Docker. |

**Ce que le serveur voit malgré tout :** qui est membre de quel salon, qui envoie un message à quel moment, la taille
approximative des messages, et le nom des salons et des agents. Ces métadonnées ne quittent jamais l'infrastructure de
l'État.

---

## 5. Installation

### Prérequis
- **Docker** et **Docker Compose v2** (Docker Desktop sous Windows ou macOS, Docker Engine sous Linux).
- Environ 4 Go de RAM libres et 3 Go de disque pour les images.
- Ports libres sur la machine : `80`, `443`, `8000`, `8008`, `8080`, `8180`, `8090`.

> **Windows (Docker Desktop) :** le dossier du projet doit être partagé avec Docker. Si le démarrage affiche
> `user declined directory sharing`, ajoutez le dossier dans *Settings → Resources → File sharing*, ou activez le moteur
> WSL 2. Voir [Dépannage](#12-dépannage).

### Démarrage (une seule commande)
```bash
git clone <ce dépôt> kibare && cd kibare
docker compose up -d
```
Le premier démarrage prend quelques minutes : téléchargement des images, construction de la console et import du royaume
Keycloak. La console attend que Synapse et Keycloak répondent, puis enrôle automatiquement les comptes de démonstration.

### Vérifier que tout fonctionne
```bash
docker compose ps                 # init « Exited (0) », les autres « Up » (postgres, keycloak, synapse : healthy)
docker compose logs console       # doit se terminer par « Console prête. »
```

| Service | Adresse | Résultat attendu |
|---|---|---|
| Messagerie (Element) | https://localhost | page d'accueil Kibaré |
| API Matrix | https://localhost/_matrix/client/versions | JSON des versions |
| API d'administration Synapse | https://localhost/_synapse/admin/v1/server_version | **403** (bloquée) |
| Identité (Keycloak) | https://localhost/realms/mtdpce/.well-known/openid-configuration | JSON OIDC |
| Redirection HTTP | http://localhost | **308** vers https://localhost |
| Console d'administration | http://localhost:8090 | redirection vers la page de connexion (machine hôte uniquement) |

**Faire approuver le certificat par le navigateur.** Par défaut, Caddy signe le certificat de `localhost` avec sa propre
autorité locale. Exportez-la, puis ajoutez-la aux autorités de confiance de votre compte Windows :
```bash
./scripts/appliquer-adresse-publique.sh          # crée kibare-ca-locale.crt (entre autres)
certutil -user -addstore Root kibare-ca-locale.crt   # Windows : confirmer la fenêtre de sécurité
```
Redémarrez ensuite le navigateur. Firefox utilise son propre magasin : *Paramètres → Vie privée et sécurité → Certificats
→ Afficher les certificats → Autorités → Importer*. Sur macOS : `sudo security add-trusted-cert -d -r trustRoot -k
/Library/Keychains/System.keychain kibare-ca-locale.crt`. Sous Linux, copiez le fichier dans
`/usr/local/share/ca-certificates/`, puis lancez `sudo update-ca-certificates`.

### Comptes de démonstration (entièrement fictifs)
Mot de passe commun : **`Kibare-Demo-2026`**. À la première connexion, chaque compte doit enregistrer un code TOTP avec
FreeOTP, Aegis, Google Authenticator ou toute autre application TOTP.

| Identifiant | Rôles | Ministère | Fonction |
|---|---|---|---|
| `admin.dgtd` | `admin` (console uniquement, pas de compte de messagerie) | Transition Digitale | Administrateur de la messagerie |
| `awa.sawadogo` | `agent`, `chef_service` | Santé | Directrice régionale |
| `issa.compaore` | `agent` | Santé | Chargé d'études |
| `mariam.traore` | `agent`, `chef_service` | Éducation nationale | Secrétaire générale |
| `paul.zongo` | `agent` | Transition Digitale | Ingénieur systèmes |

Ces comptes sont définis dans [config/demo/agents.json](config/demo/agents.json). Pour un déploiement réel, videz la liste
`agents` de ce fichier avant le premier démarrage.

---

## 6. Configuration

### Paramètres publics : `.env`
Ce fichier ne contient **aucun secret**.

| Variable | Défaut | Rôle |
|---|---|---|
| `PUBLIC_HOST` | `localhost` | Nom d'hôte utilisé par les navigateurs pour joindre la plateforme. |
| `SERVER_NAME` | `kibare.local` | Domaine Matrix des comptes (`@prenom.nom:kibare.local`). **Ne peut plus changer une fois la base créée.** |
| `PORT_MATRIX` | `8008` | API Matrix (Synapse). |
| `PORT_ELEMENT` | `8080` | Client web. |
| `PORT_KEYCLOAK` | `8180` | Pages de connexion Keycloak. |
| `PORT_CONSOLE` | `8090` | Console d'administration, publiée sur `127.0.0.1` seulement. |
| `PORT_TUNNEL` | `8000` | Point d'entrée d'un tunnel de démonstration, publié sur `127.0.0.1`. |
| `PUBLIC_URL` | `https://localhost` | Adresse unique d'Element, Synapse et Keycloak : `https://PUBLIC_HOST` (HTTPS par Caddy), l'adresse d'un tunnel, ou vide pour l'accès HTTP par ports. |
| `CADDY_TLS` | `internal` | Certificat HTTPS : `internal`, `/certs/kibare.crt /certs/kibare.key`, ou une adresse e-mail (ACME). |

La configuration d'Element ([config/element/config.json.tmpl](config/element/config.json.tmpl)) est générée à partir de
ces valeurs. **Après tout changement de `PUBLIC_URL`, lancez `./scripts/appliquer-adresse-publique.sh`.** Ce script
régénère la configuration, redémarre les services concernés et met à jour l'adresse de retour OIDC dans Keycloak : le
royaume déjà importé n'est pas relu.

### HTTPS avec Caddy
En HTTPS (`PUBLIC_URL=https://PUBLIC_HOST`), Caddy écoute sur le port **443** et sert les trois services sur une seule
origine, aiguillés par chemin : Element sur `/`, Synapse sur `/_matrix` et `/_synapse/client`, Keycloak sur `/realms` et
`/resources`. Les API d'administration y renvoient 403. Le port **80** redirige vers HTTPS. Les ports HTTP historiques
(8008, 8080, 8180) restent ouverts, mais ne servent plus la connexion.

| `CADDY_TLS` | Usage |
|---|---|
| `internal` | Démonstration. Autorité locale de Caddy, conservée dans le volume `kibare_caddy_data`. Le certificat racine est à faire approuver (voir [Installation](#vérifier-que-tout-fonctionne)). |
| `/certs/kibare.crt /certs/kibare.key` | Production. Déposer le certificat (chaîne complète) et la clé de l'État dans `config/caddy/certs/`. Ce dossier est exclu de Git. |
| `admin@domaine.bf` | Certificat ACME, si `PUBLIC_HOST` est un vrai nom de domaine joignable sur les ports 80 et 443. Attention : l'autorité ACME par défaut (Let's Encrypt) est un service tiers. |

La console reste en HTTP sur `127.0.0.1:8090`, car elle n'est jamais exposée au réseau.

### Ouvrir la démonstration à d'autres testeurs (tunnel ngrok)
Le port `8000` de Caddy sert la même origine unique, sans TLS : c'est ngrok qui fournit le HTTPS.

```bash
ngrok http 8000                                   # noter l'adresse https://….ngrok-free.app
# dans .env : PUBLIC_URL=https://….ngrok-free.app
./scripts/appliquer-adresse-publique.sh
```

> **Attention :** ngrok termine le HTTPS. Il voit donc les mots de passe, les codes TOTP et les jetons de session, mais pas
> le contenu des messages, qui restent chiffrés de bout en bout. **N'utilisez que les comptes fictifs.** Sans domaine
> ngrok réservé, l'adresse change à chaque redémarrage de ngrok, et il faut refaire ces étapes. Pour revenir au HTTPS
> local, remettez `PUBLIC_URL=https://localhost` et relancez le script.

### Identité visuelle
Les trois écrans que voit un utilisateur portent l'identité de Kibaré. Ils partagent :
- le logo ;
- les couleurs du logo : vert `#08801a`, rouge `#e3120b`, or `#fdc703`, vert profond `#0b3d17` ;
- la bande diagonale rouge, or et verte.

| Écran | Fichiers | Ce qui est personnalisé |
|---|---|---|
| Element | [config/element/kibare/](config/element/kibare/), [config.json.tmpl](config/element/config.json.tmpl) | Page d'accueil avant connexion (`bienvenue.html`), page « Accueil » après connexion avec les règles d'usage et les niveaux de classification (`accueil.html`), fond, logo, icônes et manifeste. Thèmes **« Kibaré »** (par défaut) et **« Kibaré sombre »**, au choix dans *Paramètres → Apparence*. |
| Connexion Keycloak | [config/keycloak/themes/kibare/](config/keycloak/themes/kibare/) | Thème `kibare` dérivé du thème `keycloak` : fond, logo, carte, boutons, pages TOTP. |
| Console | [admin-console/app/static/](admin-console/app/static/) | Bandeau, logo, favicon, boutons et cartes aux mêmes couleurs. |

Le logo source est [config/identite/logo.jpg](config/identite/logo.jpg). Après l'avoir remplacé, régénérez les images
(version détourée, icônes, favicon), puis appliquez :
```bash
python scripts/generer-images.py        # nécessite Pillow
./scripts/appliquer-adresse-publique.sh
docker compose up -d --build console
```
Caddy sert ces fichiers et remplace les icônes d'Element (`/vector-icons/*`) et son manifeste. Aucune image d'Element
n'est reconstruite.

### Secrets générés automatiquement
Au premier démarrage, le service `init` ([admin-console/scripts/init_secrets.py](admin-console/scripts/init_secrets.py))
écrit `/secrets/secrets.env` dans le volume `kibare_secrets`. Il contient 10 valeurs aléatoires de 256 bits, toutes
différentes : mots de passe PostgreSQL, Synapse et Keycloak, secrets Synapse (macaroon, formulaire, inscription), secrets
des clients OIDC et secret de session de la console. Les secrets existants sont **conservés** d'un redémarrage à l'autre.

### Modèles de configuration
Les fichiers `config/**/*.tmpl` sont des modèles. À chaque exécution, `init` remplace leurs variables `${NOM}` par les
paramètres publics et les secrets, puis écrit le résultat dans le volume `kibare_rendered`. Si une variable n'est pas
définie, le rendu échoue : aucune configuration incomplète ne peut être produite.

| Modèle | Contenu |
|---|---|
| [config/synapse/homeserver.yaml.tmpl](config/synapse/homeserver.yaml.tmpl) | Synapse durci : pas de fédération, OIDC seul, chiffrement imposé, rétention, minimisation des métadonnées. |
| [config/keycloak/realm-mtdpce.json.tmpl](config/keycloak/realm-mtdpce.json.tmpl) | Royaume `mtdpce` : rôles, politique de mot de passe, TOTP, anti-force brute, clients `synapse` et `kibare-console`. |

Pour appliquer une modification d'un modèle sur une plateforme déjà démarrée :
```bash
docker compose run --rm init                # régénère la configuration (les secrets sont conservés)
docker compose restart synapse              # ou le service concerné
```
> Keycloak n'importe le royaume que s'il **n'existe pas encore**. Une modification du royaume sur une plateforme en
> service se fait dans l'interface Keycloak, ou bien en repartant de zéro (voir [Réinitialisation](#réinitialisation-complète)).

Les fichiers non modèles (`config/caddy/Caddyfile`, `config/element/config.json`, `config/postgres/init-databases.sh`) sont
montés directement dans les conteneurs.

---

## 7. Guide d'utilisation

### Agent : première connexion
1. Ouvrez https://localhost et cliquez sur **Se connecter**. Vous êtes redirigé vers le portail d'identité.
2. Saisissez votre identifiant (par exemple `awa.sawadogo`) et votre mot de passe.
3. Scannez le QR code avec votre application TOTP, puis saisissez le code à 6 chiffres.
4. De retour dans Element, choisissez une **phrase de sécurité** pour sauvegarder vos clés de chiffrement. Notez-la : elle
   permet de relire l'historique depuis un nouvel appareil.
5. Pour démarrer une conversation, cherchez un collègue par son nom dans l'annuaire.

Conseil : vérifiez l'identité de vos interlocuteurs (*Vérifier la session*). Cela protège contre un faux appareil qui serait
ajouté par un serveur compromis.

### Administrateur : enrôler un agent
1. Ouvrez http://localhost:8090 **depuis la machine qui héberge Kibaré** et connectez-vous avec un compte `admin` (mot de
   passe + TOTP).
2. Allez dans **Enrôler un agent**. Renseignez l'identifiant (minuscules, chiffres, `.`, `_` ou `-`, de 2 à 63 caractères), le prénom,
   le nom, le ministère, la fonction et un mot de passe initial conforme à la politique. Cochez *Chef de service* si besoin.
3. Transmettez le mot de passe à l'agent par un canal sûr. Il devra enregistrer son TOTP à la première connexion.

### Administrateur : révoquer un agent
Dans l'**Annuaire**, choisissez le motif sur la ligne de l'agent, puis cliquez sur **Révoquer**. L'effet est immédiat : ses
sessions sont fermées sur tous ses appareils et il quitte tous ses salons. Le journal enregistre l'action, son auteur, le
motif et le nombre d'appareils déconnectés. Une révocation est définitive : pour réintégrer la personne, il faut un nouvel
enrôlement avec un autre identifiant.

### Administrateur : créer un salon classifié
Dans **Salon classifié**, donnez un nom neutre (le nom reste visible par le serveur), choisissez le niveau, cochez les
membres et les modérateurs. Seuls les agents actifs sont proposés. Les membres reçoivent une invitation dans Element. Le
salon s'affiche sous la forme `[CONFIDENTIEL] Nom du salon`.

---

## 8. Scénario de démonstration
Scénario en 5 minutes, pensé pour le jury :

1. **Accès réservé.** Sur https://localhost, montrez que la seule entrée possible est le portail d'identité, sans
   bouton « Créer un compte ». `curl -X POST http://localhost:8008/_matrix/client/v3/register -d '{}'` renvoie
   `Registration has been disabled`.
2. **Messagerie chiffrée.** Connectez `awa.sawadogo` dans un navigateur et `issa.compaore` dans une fenêtre privée.
   Échangez un message qui contient une phrase témoin, par exemple `Réunion budget Ouaga 14h`, puis un fichier texte qui
   contient la même phrase.
3. **Le serveur ne lit rien.** Lancez `./scripts/verifier-serveur-aveugle.sh "Réunion budget Ouaga 14h"`. Les trois
   contrôles doivent afficher OK.
4. **Salon classifié.** Dans la console (`admin.dgtd`), créez un salon `CONFIDENTIEL` avec Awa et Issa. Montrez
   l'invitation et l'expiration à 7 jours.
5. **Révocation.** Révoquez `issa.compaore` avec le motif « Perte ou vol du téléphone ». Sa fenêtre est déconnectée et il ne
   peut pas se reconnecter. Montrez l'entrée correspondante dans le **Journal d'audit**.

---

## 9. Tests et vérifications

### Tests automatisés de la console (20 tests)
```bash
cd admin-console
pip install -r requirements-dev.txt
pytest
```
Ils couvrent :
- **Enrôlement :** création dans Keycloak et dans Synapse, refus des identifiants invalides (`Awa`, `../admin`, `@awa:x`…)
  et des doublons.
- **Révocation :** Keycloak est désactivé *avant* Synapse, tous les appareils sont supprimés, le statut et le motif sont
  enregistrés, le journal est alimenté. Un agent inconnu ne peut pas être révoqué.
- **Salons :** impossible d'inviter un agent révoqué ou non enrôlé. Un salon confidentiel expire en 7 jours.
- **Secrets :** générés une seule fois, tous distincts. Un modèle avec une variable manquante est refusé.
- **Connexion OIDC :** PKCE S256 conforme à la RFC 7636, `state` falsifié rejeté, `state` à usage unique, accès refusé
  sans le rôle `admin`.
- **Synapse :** le HMAC d'inscription respecte le format imposé par Synapse.

Keycloak et Synapse y sont remplacés par des doubles de test : les tests tournent sans Docker.

### Épreuve « le serveur ne lit rien »
```bash
./scripts/verifier-serveur-aveugle.sh "phrase témoin"
```
Après l'envoi de la phrase témoin dans un salon (en message et dans un fichier), le script vérifie trois points :
1. la base Synapse ne contient **aucun** événement `m.room.message` en clair, seulement des `m.room.encrypted` ;
2. la phrase est introuvable dans un `pg_dump` **complet** de la base (événements, index de recherche, caches) ;
3. la phrase est introuvable dans les fichiers stockés par le serveur (`/data/media_store`).

Le script renvoie un code d'erreur au moindre échec. Sous Windows, lancez-le depuis Git Bash ou WSL.

### Contrôles rapides en ligne de commande
```bash
curl -s http://localhost:8008/_matrix/client/v3/login                         # seul flux : m.login.sso (oidc-keycloak)
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8008/_synapse/admin/v1/server_version   # 403
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8180/admin/                              # 403
```

---

## 10. Structure du dépôt
```
.
├── docker-compose.yml            # Toute la plateforme : 7 services, 6 volumes
├── .env                          # Paramètres publics (hôte, domaine, ports), sans secret
├── config/
│   ├── caddy/Caddyfile           # Proxy : en-têtes de sécurité, blocage des API d'admin
│   ├── demo/agents.json          # Comptes fictifs de démonstration
│   ├── caddy/certs/              # Certificat HTTPS de l'État (exclu de Git)
│   ├── element/config.json.tmpl  # Client Element : serveur imposé, thèmes, fonctions risquées désactivées
│   ├── element/kibare/           # Identité visuelle d'Element : logo, pages d'accueil, fond, icônes
│   ├── identite/logo.jpg         # Logo source
│   ├── keycloak/realm-mtdpce.json.tmpl   # Royaume d'identité (modèle)
│   ├── keycloak/themes/kibare/   # Thème des pages de connexion
│   ├── postgres/init-databases.sh        # Bases et utilisateurs dédiés
│   └── synapse/
│       ├── homeserver.yaml.tmpl  # Configuration Synapse durcie (modèle)
│       └── log.config
├── admin-console/                # Console d'administration (Python / FastAPI)
│   ├── Dockerfile                # Image de la console et du service init (utilisateur non root)
│   ├── app/
│   │   ├── main.py               # Routes web, session, CSRF, démarrage
│   │   ├── auth.py               # Connexion OIDC des administrateurs (PKCE, state, rôle admin)
│   │   ├── services.py           # Règles métier : enrôlement, révocation, salons classifiés
│   │   ├── keycloak.py           # Client de l'API d'administration Keycloak
│   │   ├── synapse.py            # Client de l'API d'administration Synapse
│   │   ├── registry.py           # Registre des agents et journal d'audit (SQLite)
│   │   ├── config.py             # Lecture des paramètres et des secrets
│   │   ├── templates/            # Pages HTML (Jinja2)
│   │   └── static/               # Feuille de style, logo, favicon
│   ├── scripts/init_secrets.py   # Génération des secrets et rendu des modèles
│   └── tests/test_securite.py    # 20 tests de sécurité
├── scripts/
│   ├── verifier-serveur-aveugle.sh       # Preuve que le serveur ne lit rien
│   ├── appliquer-adresse-publique.sh     # Applique PUBLIC_URL, le thème Keycloak, exporte l'autorité locale
│   └── generer-images.py                 # Images de l'identité visuelle à partir du logo source
├── docs/NOTE_SECURITE.md         # Analyse de sécurité détaillée
└── LICENSE                       # AGPL-3.0
```

---

## 11. Exploitation

### Commandes courantes
```bash
docker compose ps                        # état des services
docker compose logs -f synapse           # journaux d'un service
docker compose restart console           # redémarrer un service
docker compose stop                      # arrêter sans rien perdre
docker compose up -d                     # redémarrer
docker compose up -d --build console     # reconstruire la console après une modification du code
```

### Volumes
| Volume | Contenu | À sauvegarder |
|---|---|---|
| `kibare_secrets` | Secrets générés | **oui**, de façon très protégée |
| `kibare_postgres_data` | Bases Synapse et Keycloak | **oui** |
| `kibare_synapse_data` | Clé de signature du serveur, fichiers chiffrés | **oui** |
| `kibare_console_data` | Registre des agents, journal d'audit, jeton de service | **oui** |
| `kibare_caddy_data` | Autorité locale et certificats HTTPS de Caddy | oui (sinon nouvelle autorité à faire approuver) |
| `kibare_rendered` | Configuration générée | non, elle est recréée par `init` |

Exemple de sauvegarde de la base :
```bash
docker compose exec -T postgres pg_dumpall -U postgres > sauvegarde-$(date +%F).sql
```
Les messages et les fichiers sont chiffrés dans la sauvegarde. Les métadonnées et le registre, eux, ne le sont pas :
protégez les sauvegardes en conséquence.

### Réinitialisation complète
```bash
docker compose down -v      # ATTENTION : supprime tous les comptes, messages, secrets et le journal
docker compose up -d
```

### Mise à jour des composants
Les versions des images sont figées dans `docker-compose.yml`. Pour monter de version, modifiez l'étiquette, lisez les
notes de version (notamment les migrations de base Synapse), sauvegardez, puis lancez `docker compose up -d`.

---

## 12. Dépannage

| Symptôme | Cause | Solution |
|---|---|---|
| `user declined directory sharing …\config` | Docker Desktop n'a pas le droit de monter le dossier du projet. | *Settings → Resources → File sharing* : ajouter le dossier, puis *Apply & restart*. Ou activer le moteur WSL 2. |
| `Missing parameter: code_challenge_method` à la connexion | Keycloak exige PKCE, mais Synapse ne l'envoie pas. | Vérifier `pkce_method: always` dans `homeserver.yaml.tmpl`, puis `docker compose run --rm init && docker compose restart synapse`. Relancer la connexion depuis Element, sans recharger l'ancienne page d'erreur. |
| `port is already allocated` | Un port est déjà utilisé sur la machine. | Changer le port dans `.env` (et dans `config/element/config.json` pour `PORT_MATRIX`). |
| La console ne démarre pas, « Initialisation en attente » en boucle | Synapse ou Keycloak n'est pas prêt. | `docker compose logs keycloak synapse`. La console réessaie pendant 5 minutes. |
| « Accès réservé aux administrateurs Kibaré » | Le compte n'a pas le rôle `admin`. | Utiliser `admin.dgtd`, ou attribuer le rôle dans Keycloak. |
| Un agent ne peut pas se connecter à la messagerie | Pas de rôle `agent`, compte révoqué, ou verrouillé après 5 échecs. | Vérifier son statut dans l'annuaire. Le verrouillage se lève tout seul (attente maximale : 15 minutes). |
| « Impossible de déchiffrer ce message » sur un nouvel appareil | Les clés n'ont pas été récupérées. | Vérifier la session depuis un autre appareil, ou saisir la phrase de sécurité. |
| `invalid_redirect_uri` chez Keycloak | `PUBLIC_HOST` ou un port a changé après l'import du royaume. | Corriger les URI de redirection des clients dans Keycloak, ou réinitialiser. |

---

## 13. Passage en production
La démonstration tourne en HTTPS sur `localhost`, avec l'autorité locale de Caddy. Avant toute mise en service :

- [ ] **Certificat de l'État** : `CADDY_TLS=/certs/kibare.crt /certs/kibare.key`, et
      `PUBLIC_URL=https://PUBLIC_HOST` avec le vrai nom d'hôte.
- [ ] Ne publier que les ports 80 et 443. Retirer de `docker-compose.yml` les ports HTTP de démonstration (8000, 8008,
      8080, 8180).
- [ ] Ajouter l'en-tête HSTS (`Strict-Transport-Security`) sur le site HTTPS. Il n'est pas activé sur `localhost`, car il
      forcerait le HTTPS sur tous les ports de la machine, y compris pour la console.
- [ ] `PUBLIC_HOST` et `SERVER_NAME` définitifs. `SERVER_NAME` ne pourra plus changer.
- [ ] Vider `config/demo/agents.json` et créer un premier administrateur nominatif.
- [ ] Rendre la console accessible uniquement depuis le réseau d'administration (VPN ou bastion).
- [ ] Sauvegardes chiffrées et régulières des 4 volumes persistants, avec un test de restauration.
- [ ] Supervision des conteneurs et de l'espace disque.
- [ ] Redondance de PostgreSQL, Keycloak et Synapse si la disponibilité l'exige.
- [ ] Politique de vérification des appareils (signature croisée) communiquée aux agents.
- [ ] Client mobile adapté pour bloquer les captures d'écran et le transfert, si ces règles sont exigées.

---

## 14. Limites connues
- **Certificat de démonstration :** sur `localhost`, le certificat vient de l'autorité locale de Caddy, qu'il faut faire
  approuver par chaque navigateur. La production utilise un certificat de l'État.
- **Trafic interne en HTTP :** entre les conteneurs (Caddy → services, Synapse → Keycloak), le trafic reste en clair, sur
  le réseau Docker privé. C'est aussi pour cela que `skip_verification: true` reste nécessaire côté Synapse. Les
  contenus des messages restent chiffrés de bout en bout.
- **Métadonnées :** le serveur sait qui parle avec qui, quand, et connaît le nom des salons
  (voir [docs/NOTE_SECURITE.md](docs/NOTE_SECURITE.md)).
- **Contenus déjà déchiffrés :** la révocation empêche de lire les **nouveaux** messages. Ce qu'un appareil avait déjà
  déchiffré y reste tant que l'application n'est pas effacée.
- **Client web :** il ne peut ni bloquer les captures d'écran ni interdire le transfert de messages.
- **Vérification des appareils :** disponible dans Element mais pas encore imposée. Elle est nécessaire pour se protéger
  d'un serveur malveillant qui ajouterait un faux appareil.
- **Megolm :** sa confidentialité persistante est plus faible que celle de Signal ou de MLS. Matrix prépare une migration
  vers MLS.
- **Rôle `chef_service` :** il est attribué et transmis par Keycloak, mais la console ne lui donne pas encore de droits
  particuliers.
- **Haute disponibilité :** pas encore de redondance. Chaque service est un point de défaillance unique.

---

## 15. Technologies et licences
| Composant | Rôle | Licence | Projet |
|---|---|---|---|
| Synapse | Serveur Matrix | AGPL-3.0 | https://github.com/element-hq/synapse |
| Element Web | Client web | AGPL-3.0 | https://github.com/element-hq/element-web |
| vodozemac (via matrix-rust-sdk-crypto) | Olm / Megolm | Apache-2.0 | https://github.com/matrix-org/vodozemac |
| Keycloak | Identité, TOTP, rôles | Apache-2.0 | https://github.com/keycloak/keycloak |
| PostgreSQL | Base de données | PostgreSQL License | https://www.postgresql.org |
| Caddy | Proxy inverse | Apache-2.0 | https://github.com/caddyserver/caddy |
| FastAPI, Uvicorn, HTTPX, Jinja2 | Console | MIT / BSD-3 | https://fastapi.tiangolo.com |
| pytest, pytest-asyncio, respx | Tests | MIT / Apache-2.0 / BSD-3 | https://pytest.org |
| Python | Langage de la console | PSF License | https://www.python.org |

## Licence
Kibaré est distribué sous licence **GNU AGPL-3.0** (voir [LICENSE](LICENSE)). Toute version modifiée et mise à disposition
sur un réseau doit publier son code source.
