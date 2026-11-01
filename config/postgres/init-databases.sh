#!/bin/sh
# Crée une base et un utilisateur dédiés pour Synapse et pour Keycloak.
# Exécuté une seule fois, à l'initialisation du volume PostgreSQL.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
	CREATE USER synapse WITH PASSWORD '${SYNAPSE_DB_PASSWORD}';
	CREATE DATABASE synapse OWNER synapse ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0;
	CREATE USER keycloak WITH PASSWORD '${KEYCLOAK_DB_PASSWORD}';
	CREATE DATABASE keycloak OWNER keycloak;
EOSQL
