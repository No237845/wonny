"""Paramètres de la console, lus dans l'environnement et le fichier de secrets."""

import os
from dataclasses import dataclass
from pathlib import Path

from scripts.init_secrets import read_env_file


@dataclass(frozen=True)
class Settings:
    server_name: str
    synapse_url: str
    keycloak_internal_url: str
    keycloak_public_url: str
    console_public_url: str
    realm: str
    client_id: str
    client_secret: str
    registration_shared_secret: str
    session_secret: str
    data_dir: Path
    demo_file: Path


def load_settings() -> Settings:
    secrets = read_env_file(Path(os.environ.get("KIBARE_SECRETS_DIR", "/secrets")) / "secrets.env")
    host = os.environ.get("PUBLIC_HOST", "localhost")
    return Settings(
        server_name=os.environ.get("SERVER_NAME", "kibare.local"),
        synapse_url=os.environ.get("SYNAPSE_INTERNAL_URL", "http://synapse:8008"),
        keycloak_internal_url=os.environ.get("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080"),
        keycloak_public_url=f"http://{host}:{os.environ.get('PORT_KEYCLOAK', '8180')}",
        console_public_url=f"http://{host}:{os.environ.get('PORT_CONSOLE', '8090')}",
        realm="mtdpce",
        client_id="kibare-console",
        client_secret=secrets.get("CONSOLE_OIDC_SECRET", ""),
        registration_shared_secret=secrets.get("SYNAPSE_REGISTRATION_SECRET", ""),
        session_secret=secrets.get("CONSOLE_SESSION_SECRET", ""),
        data_dir=Path(os.environ.get("KIBARE_DATA_DIR", "/data")),
        demo_file=Path(os.environ.get("KIBARE_DEMO_FILE", "/app/demo/agents.json")),
    )
