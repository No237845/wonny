#!/usr/bin/env bash
# Épreuve « Le serveur ne lit rien ».
#
# Usage : ./scripts/verifier-serveur-aveugle.sh "phrase témoin"
#   1. envoyez la phrase témoin dans un salon depuis Element (et un fichier
#      texte la contenant) ;
#   2. lancez ce script : il cherche la phrase dans TOUTE la base Synapse et
#      dans tous les fichiers stockés par le serveur.
set -euo pipefail

TEMOIN="${1:?Indiquez la phrase témoin envoyée dans la messagerie}"
psql() { docker compose exec -T postgres psql -U postgres -d synapse -At "$@"; }
echec=0

echo "== 1. Types d'événements de messages stockés =="
psql -c "SELECT type, count(*) FROM events
         WHERE type IN ('m.room.message', 'm.room.encrypted', 'm.sticker')
         GROUP BY type;"

clairs=$(psql -c "SELECT count(*) FROM events WHERE type = 'm.room.message';")
if [ "$clairs" != "0" ]; then
  echo "ÉCHEC : $clairs message(s) non chiffré(s) en base."; echec=1
else
  echo "OK : aucun événement m.room.message, tout est m.room.encrypted."
fi

echo
echo "== 2. Recherche de la phrase témoin dans la base complète =="
# pg_dump couvre toutes les tables (événements, index de recherche, caches…).
if docker compose exec -T postgres pg_dump -U postgres synapse | grep -qiF -- "$TEMOIN"; then
  echo "ÉCHEC : la phrase témoin apparaît en clair dans la base."; echec=1
else
  echo "OK : phrase introuvable dans la base."
fi

echo
echo "== 3. Recherche dans les fichiers stockés (media_store) =="
if docker compose exec -T synapse grep -rqiF -- "$TEMOIN" /data/media_store 2>/dev/null; then
  echo "ÉCHEC : la phrase témoin apparaît dans un fichier stocké."; echec=1
else
  echo "OK : les fichiers stockés sont chiffrés."
fi

echo
[ "$echec" = 0 ] && echo "RÉSULTAT : le serveur ne peut lire ni les messages ni les fichiers." || exit 1
