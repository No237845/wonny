#!/usr/bin/env bash
# Applique PUBLIC_URL (.env) à une plateforme déjà installée.
#
# Usage : ./scripts/appliquer-adresse-publique.sh
#   1. régénère la configuration (les secrets sont conservés) ;
#   2. redémarre les services qui en dépendent ;
#   3. met à jour dans Keycloak l'adresse de retour OIDC du client "synapse"
#      et le thème de connexion (le royaume, importé au premier démarrage,
#      n'est pas relu ensuite) ;
#   4. en HTTPS avec l'autorité locale de Caddy, exporte son certificat racine
#      dans kibare-ca-locale.crt, à faire approuver par les navigateurs.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1  # Git Bash sous Windows : ne pas réécrire les chemins

echo "== 1. Configuration"
docker compose run --rm init | tail -1

echo "== 2. Redémarrage"
docker compose up -d --quiet-pull 2>&1 | grep -E "Recreated|Error" || true
docker compose restart synapse keycloak proxy >/dev/null
for _ in $(seq 1 60); do
  etats=$(docker compose ps --format '{{.Service}}={{.Health}}' synapse keycloak)
  echo "$etats" | grep -qv "=healthy" || break
  sleep 3
done
echo "$etats"

echo "== 3. Adresse de retour OIDC dans Keycloak"
docker compose exec -T keycloak bash -c '
set -e; . /secrets/secrets.env
base=$(sed -n "s|^public_baseurl: \"\(.*\)/\"$|\1|p" /rendered/synapse/homeserver.yaml)
K=/opt/keycloak/bin/kcadm.sh
$K config credentials --server http://localhost:8080 --realm master \
  --user kc-bootstrap --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null 2>&1
id=$($K get clients -r mtdpce -q clientId=synapse --fields id --format csv --noquotes)
$K update "clients/$id" -r mtdpce -s "redirectUris=[\"$base/_synapse/client/oidc/callback\"]"
# HSTS a max-age=0 : sur localhost, il imposerait HTTPS a tous les ports (dont
# la console en HTTP). En production, Caddy le pose sur le vrai domaine.
# Les autres en-tetes absents de la liste gardent leur valeur par defaut.
$K update realms/mtdpce -s loginTheme=kibare \
  -s "browserSecurityHeaders={\"strictTransportSecurity\": \"max-age=0\"}"
echo "$base/_synapse/client/oidc/callback"'

url=$(sed -n 's/^PUBLIC_URL=//p' .env | tr -d '\r')
tls=$(sed -n 's/^CADDY_TLS=//p' .env | tr -d '\r')
host=$(sed -n 's/^PUBLIC_HOST=//p' .env | tr -d '\r')
if [ "${tls:-internal}" = internal ] && [ "$url" = "https://${host:-localhost}" ]; then
  echo "== 4. Autorité de certification locale de Caddy"
  for _ in $(seq 1 20); do
    docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt kibare-ca-locale.crt >/dev/null 2>&1 && break
    sleep 1
  done
  if [ -f kibare-ca-locale.crt ]; then
    echo "Certificat racine exporté : kibare-ca-locale.crt"
    echo "Windows : certutil -user -addstore Root kibare-ca-locale.crt"
  fi
fi

echo "== Prêt : ${url:-http://localhost:8080}"
