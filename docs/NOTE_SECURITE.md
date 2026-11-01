# Note de sécurité — Kibaré

## 1. Périmètre et hypothèses
Kibaré protège les échanges de service entre agents publics enrôlés : messages, groupes et fichiers. Nous supposons que
le serveur est hébergé par l'État, mais nous le traitons comme **potentiellement curieux ou compromis**. Le serveur ne
doit donc jamais pouvoir lire un contenu. Les terminaux des agents sont considérés comme de confiance tant qu'ils ne sont
pas déclarés perdus.

## 2. Menaces prises en compte et protections
| # | Menace | Protection mise en place |
|---|---|---|
| M1 | Lecture des messages ou fichiers sur le serveur (administrateur, intrus, sauvegarde volée) | Chiffrement de bout en bout imposé dans tous les salons (`encryption_enabled_by_default_for_room_type: all`). Olm sert entre appareils, Megolm dans les groupes, via vodozemac. Les fichiers sont chiffrés par le client avant l'envoi (AES-CTR, clé transmise dans le message chiffré). Aucun aperçu de lien n'est généré côté serveur. Vérifiable avec `scripts/verifier-serveur-aveugle.sh`. |
| M2 | Interception réseau | Le contenu est déjà chiffré de bout en bout. En production, TLS est ajouté au point d'entrée Caddy. |
| M3 | Personne non enrôlée qui tente de rejoindre la messagerie | Inscription Matrix désactivée, invités interdits, connexion par mot de passe Matrix désactivée. Seul Keycloak donne accès, et uniquement aux comptes porteurs du rôle `agent` (`attribute_requirements`). Les comptes sont créés exclusivement par la console. |
| M4 | Vol de mot de passe ou hameçonnage | Second facteur **TOTP obligatoire**, enregistré à la première connexion. Blocage après 5 échecs (protection anti-force brute de Keycloak). Mot de passe d'au moins 12 caractères. |
| M5 | Téléphone perdu, agent qui quitte son poste | **Révocation immédiate** depuis la console : compte Keycloak désactivé et sessions fermées, puis compte Synapse désactivé, ce qui supprime **tous** ses appareils et jetons et le retire de tous ses salons. Les membres restants renouvellent la session Megolm : les nouveaux messages lui sont illisibles. L'action est tracée dans le journal d'audit. |
| M6 | Nouveau membre qui lit l'historique d'un salon sensible | Salons classifiés en `history_visibility: joined` : un membre ne reçoit pas les clés des messages antérieurs à son arrivée. |
| M7 | Conservation excessive des données | Expiration automatique des messages (politique de rétention) : 30 jours en Diffusion restreinte, 7 jours en Confidentiel. Durées de conservation des IP et des messages supprimés réduites à 1 jour. |
| M8 | Fuite vers des services tiers | Fédération désactivée, aucun serveur de clés externe, aucun serveur d'identité, pas de widgets ni d'intégrations, pas de visioconférence publique, pas de notifications push via Google ou Apple. Toutes les dépendances sont auto-hébergées. |
| M9 | Accès à l'API d'administration | Les API d'administration de Synapse et de Keycloak sont bloquées sur le proxy public. La console n'écoute que sur 127.0.0.1, exige le rôle `admin` + TOTP (OIDC avec PKCE et `state`), et protège ses formulaires par jeton CSRF. |
| M10 | Secrets par défaut ou divulgués dans le dépôt | Aucun secret dans Git. Tous sont tirés aléatoirement (256 bits) au premier démarrage et stockés dans un volume Docker. |

## 3. Ce que le serveur voit malgré tout (métadonnées)
| Visible par le serveur | Pourquoi | Mesures de réduction |
|---|---|---|
| Identité des membres de chaque salon | Nécessaire pour router les messages | Pas de fédération : ces données ne sortent pas de l'infrastructure de l'État. |
| Expéditeur, salon et horodatage de chaque message chiffré | Protocole Matrix | Rétention limitée, purge automatique dans les salons classifiés. |
| Taille approximative des messages et des fichiers | Inhérent au chiffrement | — |
| Nom et sujet des salons, nom affiché des agents | Événements d'état non chiffrés dans Matrix | Consigne : choisir des noms de salon neutres. Le niveau de classification est volontairement visible, car il porte des règles. |
| Adresse IP et appareil | Connexion réseau | Conservation limitée à 1 jour. Journal d'accès HTTP réduit. |
| Indicateurs de saisie, présence | Fonctions de confort | **Désactivés**. |
| Accusés de lecture | Utiles aux instructions de service | Conservés et assumés. |

## 4. Limites connues
1. **Démonstration en HTTP sur localhost.** La production exige TLS, avec un certificat de l'État, et `skip_verification: false`.
2. **Contenus déjà déchiffrés.** Après une révocation, l'agent ne lit plus les nouveaux messages, mais l'historique déjà
   présent sur un appareil hors ligne n'est pas effacé à distance.
3. **Client web.** Il ne peut ni bloquer les captures d'écran ni interdire le transfert. Ces règles relèvent d'un client
   mobile adapté.
4. **Vérification croisée des appareils.** La sécurité contre un serveur malveillant qui ajouterait un faux appareil
   repose sur la vérification des appareils (signature croisée) par les agents. Elle est disponible dans Element, mais
   pas encore imposée.
5. **Megolm.** La confidentialité persistante est plus faible qu'avec Signal ou MLS, car une clé de session couvre
   plusieurs messages. Matrix travaille à une migration vers MLS.
6. **Point de défaillance unique.** Keycloak et Synapse ne sont pas encore redondés. Les sauvegardes sont à organiser,
   et elles restent chiffrées pour les contenus.
