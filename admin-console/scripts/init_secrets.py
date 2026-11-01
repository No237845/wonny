"""Génère les secrets de la plateforme et rend les fichiers de configuration.

Exécuté par le service Docker "init" avant tous les autres :
  1. crée /secrets/secrets.env avec des valeurs aléatoires (une seule fois :
     les secrets existants sont conservés d'un redémarrage à l'autre) ;
  2. remplace les variables ${NOM} des modèles /templates/**/*.tmpl et écrit
     le résultat dans /rendered/ ; les autres fichiers sont copiés tels quels.

Les secrets sont tirés avec le module standard `secrets` (générateur
cryptographique du système). Aucune cryptographie n'est implémentée ici.
"""

import os
import re
import secrets
import shutil
import sys
from pathlib import Path
from string import Template

SECRETS_FILE = Path(os.environ.get("KIBARE_SECRETS_DIR", "/secrets")) / "secrets.env"
TEMPLATES_DIR = Path(os.environ.get("KIBARE_TEMPLATES_DIR", "/templates"))
RENDERED_DIR = Path(os.environ.get("KIBARE_RENDERED_DIR", "/rendered"))

# Sous-dossiers de ./config utilisés par les conteneurs via le volume "rendered".
RENDERED_SUBDIRS = ("synapse", "keycloak", "element")

SECRET_NAMES = (
    "POSTGRES_PASSWORD",
    "SYNAPSE_DB_PASSWORD",
    "KEYCLOAK_DB_PASSWORD",
    "KEYCLOAK_ADMIN_PASSWORD",
    "SYNAPSE_MACAROON_SECRET",
    "SYNAPSE_FORM_SECRET",
    "SYNAPSE_REGISTRATION_SECRET",
    "SYNAPSE_OIDC_SECRET",
    "CONSOLE_OIDC_SECRET",
    "CONSOLE_SESSION_SECRET",
)

PUBLIC_NAMES = ("PUBLIC_HOST", "SERVER_NAME", "PORT_MATRIX", "PORT_ELEMENT", "PORT_KEYCLOAK", "PORT_CONSOLE")

UNRESOLVED = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def public_urls(env: dict[str, str]) -> dict[str, str]:
    """Adresses de Synapse et Keycloak vues par les navigateurs.

    Sans PUBLIC_URL, chaque service a son port sur PUBLIC_HOST. Avec PUBLIC_URL
    (tunnel HTTPS de démonstration), tous partagent cette seule origine et Caddy
    aiguille les requêtes selon le chemin.
    """
    tunnel = env.get("PUBLIC_URL", "").strip().rstrip("/")
    host = env.get("PUBLIC_HOST", "localhost")
    return {
        "MATRIX_PUBLIC_URL": tunnel or f"http://{host}:{env.get('PORT_MATRIX', '8008')}",
        "KEYCLOAK_PUBLIC_URL": tunnel or f"http://{host}:{env.get('PORT_KEYCLOAK', '8180')}",
    }


def ensure_secrets(path: Path) -> dict[str, str]:
    """Complète le fichier de secrets sans jamais écraser une valeur existante."""
    values = read_env_file(path)
    changed = False
    for name in SECRET_NAMES:
        if not values.get(name):
            # token_hex : uniquement [0-9a-f], sans risque dans YAML, JSON ou SQL.
            values[name] = secrets.token_hex(32)
            changed = True
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
        # Le volume "secrets" n'est monté que dans les conteneurs qui en ont
        # besoin ; Keycloak et la console y lisent sous un compte non-root.
        path.chmod(0o644)
    return values


def render(text: str, variables: dict[str, str]) -> str:
    result = Template(text).safe_substitute(variables)
    missing = sorted(set(UNRESOLVED.findall(result)))
    if missing:
        raise ValueError(f"Variables non définies dans le modèle : {', '.join(missing)}")
    return result


def render_tree(templates_dir: Path, rendered_dir: Path, variables: dict[str, str]) -> None:
    for subdir in RENDERED_SUBDIRS:
        for source in sorted((templates_dir / subdir).rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(templates_dir)
            if source.suffix == ".tmpl":
                target = rendered_dir / relative.with_suffix("")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(render(source.read_text(encoding="utf-8"), variables), encoding="utf-8")
            else:
                target = rendered_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            # Lisible par les comptes non-root de Synapse et Keycloak.
            target.chmod(0o644)
            print(f"[init] {target}")


def main() -> int:
    variables = ensure_secrets(SECRETS_FILE)
    variables.update({name: os.environ[name] for name in PUBLIC_NAMES if name in os.environ})
    variables.update(public_urls(dict(os.environ)))
    render_tree(TEMPLATES_DIR, RENDERED_DIR, variables)
    print("[init] Configuration prête.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
