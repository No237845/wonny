# Kibaré — la messagerie souveraine de l'administration

> Sprint technique pré-hackathon 2026 — MTDPCE / DGTD · Licence **AGPL-3.0**

## Concept
Kibaré (« les nouvelles », en mooré) est une messagerie instantanée réservée aux agents publics enrôlés. Elle prend en charge
les messages, les groupes et les fichiers, avec un **chiffrement de bout en bout** systématique. Elle s'installe en **une
commande** sur l'infrastructure de l'État et ne dépend d'**aucun service tiers**.

**Niveau d'engagement open source : Étendre et adapter.** Nous partons de l'écosystème Matrix (Synapse + Element), que nous
durcissons pour un usage administratif. Nous y ajoutons une **console d'administration** originale : enrôlement, révocation
immédiate, annuaire officiel, salons classifiés et journal d'audit.

## Architecture
```
 Navigateur / mobile ──► Caddy (point d'entrée unique, bloque les API d'admin)
                          ├─► Element Web ............ client, chiffre et déchiffre localement (Olm/Megolm)
                          ├─► Synapse ................ relaie et stocke des messages CHIFFRÉS, sans fédération
                          ├─► Keycloak ............... identité : mot de passe + TOTP obligatoire, rôles
                          └─► Console Kibaré ......... enrôlement, révocation, salons classifiés (127.0.0.1)
                               PostgreSQL ............ bases Synapse et Keycloak (réseau interne)
```
- **Chiffrement :** protocoles Matrix **Olm** (entre appareils) et **Megolm** (groupes), implémentés par **vodozemac**, la
  bibliothèque Rust de référence, via le SDK crypto d'Element. **Aucune cryptographie n'a été développée par l'équipe.**
- **Identité :** l'inscription libre est désactivée. Un agent n'existe que s'il a été enrôlé dans la console. Synapse
  n'accepte que les connexions OIDC venant de Keycloak, et exige le rôle `agent`.
- **Révocation :** un clic désactive le compte Keycloak et ferme ses sessions. Synapse désactive ensuite le compte : tous
  ses appareils et jetons sont supprimés et il quitte tous ses salons. La clé Megolm du groupe est alors renouvelée.

## Technologies et licences
| Composant | Rôle | Licence | Projet |
|---|---|---|---|
| Synapse | Serveur Matrix | AGPL-3.0 | https://github.com/element-hq/synapse |
| Element Web | Client web | AGPL-3.0 | https://github.com/element-hq/element-web |
| vodozemac (via matrix-rust-sdk-crypto) | Olm / Megolm | Apache-2.0 | https://github.com/matrix-org/vodozemac |
| Keycloak | Identité, 2FA, rôles | Apache-2.0 | https://github.com/keycloak/keycloak |
| PostgreSQL | Base de données | PostgreSQL License | https://www.postgresql.org |
| Caddy | Proxy inverse | Apache-2.0 | https://github.com/caddyserver/caddy |
| FastAPI, Uvicorn, HTTPX, Jinja2 | Console | MIT / BSD-3 | https://fastapi.tiangolo.com |
| Python | Langage de la console | PSF License | https://www.python.org |

## Installation (une seule commande)
Prérequis : Docker et Docker Compose v2.
```bash
git clone <ce dépôt> && cd kibare
docker compose up -d
```
Au premier démarrage, le service `init` génère tous les secrets dans un volume Docker. Les adresses publiques se règlent
dans `.env` (`PUBLIC_HOST`, ports) et dans `config/element/config.json`.

| Service | Adresse |
|---|---|
| Messagerie (Element) | http://localhost:8080 |
| Console d'administration | http://localhost:8090 (machine hôte uniquement) |

## Comptes de démonstration (fictifs)
Mot de passe commun : `Kibare-Demo-2026`. À la première connexion, chaque compte doit enregistrer un code TOTP, par exemple
avec FreeOTP ou Aegis.

| Identifiant | Rôle | Ministère |
|---|---|---|
| `admin.dgtd` | Administrateur (console) | Transition Digitale |
| `awa.sawadogo` | Agent, chef de service | Santé |
| `issa.compaore` | Agent | Santé |
| `mariam.traore` | Agent, cheffe de service | Éducation nationale |
| `paul.zongo` | Agent | Transition Digitale |

## Vérifier la sécurité
```bash
./scripts/verifier-serveur-aveugle.sh "phrase témoin"   # aucun message ni fichier en clair côté serveur
cd admin-console && pip install -r requirements-dev.txt && pytest            # 19 tests de sécurité
```

## Limites connues
- La démonstration fonctionne en HTTP sur `localhost`. En production, il faut du HTTPS (certificat de l'État).
- Le serveur voit des **métadonnées** : qui est membre de quel salon, quand, et le nom des salons (voir
  `docs/NOTE_SECURITE.md`).
- La révocation empêche de lire les **nouveaux** messages. Ce qu'un appareil avait déjà déchiffré y reste stocké tant
  que l'application n'est pas effacée.
- Blocage des captures d'écran et interdiction du transfert : ces règles ne sont pas imposées par le client web.
