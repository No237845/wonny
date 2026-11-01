"""Règles métier de la console : enrôlement, révocation, salons classifiés."""

import json
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from .keycloak import KeycloakAdmin
from .registry import Registry
from .synapse import SynapseAdmin

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}$")

# Niveaux de classification proposés et durée de vie par défaut des messages.
NIVEAUX = {
    "NON PROTÉGÉ": None,
    "DIFFUSION RESTREINTE": 30 * 24 * 3600 * 1000,
    "CONFIDENTIEL": 7 * 24 * 3600 * 1000,
}

MOTIFS_REVOCATION = (
    "Perte ou vol du téléphone",
    "Départ ou mutation",
    "Suspicion de compromission",
    "Fin de mission",
)


class EnrollmentError(ValueError):
    pass


@dataclass
class AgentInput:
    username: str
    prenom: str
    nom: str
    ministere: str
    fonction: str
    roles: list[str] = field(default_factory=lambda: ["agent"])

    @property
    def displayname(self) -> str:
        return f"{self.prenom} {self.nom} ({self.fonction})"


class Kibare:
    SERVICE_TOKEN_FILE = "synapse_service_token"

    def __init__(self, keycloak: KeycloakAdmin, synapse: SynapseAdmin, registry: Registry, data_dir: Path):
        self.keycloak = keycloak
        self.synapse = synapse
        self.registry = registry
        self.data_dir = data_dir

    async def connect_service_account(self, shared_secret: str) -> None:
        """Réutilise le jeton du compte de service, ou en crée un nouveau."""
        token_file = self.data_dir / self.SERVICE_TOKEN_FILE
        if token_file.exists():
            self.synapse.token = token_file.read_text().strip()
            try:
                await self.synapse.whoami()
                return
            except Exception:
                self.synapse.token = None
        localpart = f"kibare-console-{secrets.token_hex(4)}"
        # Mot de passe jetable : la connexion par mot de passe est désactivée
        # sur Synapse, seul le jeton renvoyé à la création est utilisé.
        token = await self.synapse.register_service_account(shared_secret, localpart, secrets.token_urlsafe(32))
        token_file.write_text(token)
        token_file.chmod(0o600)

    async def enroll(self, agent: AgentInput, password: str, auteur: str) -> None:
        if not USERNAME_RE.match(agent.username):
            raise EnrollmentError("Identifiant invalide : minuscules, chiffres, '.', '_' ou '-' uniquement.")
        if self.registry.get(agent.username):
            raise EnrollmentError(f"L'agent {agent.username} est déjà enrôlé.")

        if await self.keycloak.find_user(agent.username) is None:
            await self.keycloak.create_user(agent.username, agent.prenom, agent.nom, password, agent.roles)
        if "agent" in agent.roles:
            await self.synapse.ensure_user(agent.username, agent.displayname)

        self.registry.add_agent(agent.username, agent.prenom, agent.nom, agent.ministere,
                                agent.fonction, agent.roles)
        self.registry.log(auteur, "ENRÔLEMENT", agent.username,
                          f"{agent.ministere} — {agent.fonction} — rôles : {', '.join(agent.roles)}")

    async def revoke(self, username: str, motif: str, auteur: str) -> None:
        """Révocation immédiate, sur tous les appareils de l'agent.

        1. Keycloak : compte désactivé et sessions SSO fermées, donc aucune
           reconnexion possible.
        2. Synapse : compte désactivé, ce qui supprime TOUS ses appareils et
           jetons d'accès et le fait quitter tous ses salons. Les membres
           restants changent de clé Megolm au prochain message : l'agent
           révoqué ne peut pas déchiffrer les nouveaux messages.
        """
        agent = self.registry.get(username)
        if agent is None:
            raise EnrollmentError(f"Agent inconnu : {username}")
        if agent["statut"] == "révoqué":
            raise EnrollmentError(f"L'agent {username} est déjà révoqué.")

        kc_user = await self.keycloak.find_user(username)
        if kc_user is not None:
            await self.keycloak.disable_and_logout(kc_user["id"])

        devices = []
        if "agent" in agent["roles"].split(","):
            devices = await self.synapse.list_devices(username)
            await self.synapse.deactivate(username)

        self.registry.mark_revoked(username, motif)
        self.registry.log(auteur, "RÉVOCATION", username,
                          f"Motif : {motif} — {len(devices)} appareil(s) déconnecté(s)")

    async def create_classified_room(self, name: str, niveau: str, members: list[str],
                                     moderators: list[str], auteur: str) -> str:
        if niveau not in NIVEAUX:
            raise EnrollmentError(f"Niveau de classification inconnu : {niveau}")
        actifs = {a["username"] for a in self.registry.directory() if a["statut"] == "actif"}
        inconnus = [m for m in members + moderators if m not in actifs]
        if inconnus:
            raise EnrollmentError(f"Agents non enrôlés ou révoqués : {', '.join(inconnus)}")
        room_id = await self.synapse.create_classified_room(
            name, niveau, NIVEAUX[niveau], sorted(set(members) | set(moderators)), moderators
        )
        self.registry.log(auteur, "SALON CLASSIFIÉ", room_id,
                          f"[{niveau}] {name} — {len(set(members) | set(moderators))} membre(s)")
        return room_id

    async def seed_demo(self, demo_file: Path) -> None:
        """Enrôle les comptes fictifs de démonstration s'ils n'existent pas."""
        if not demo_file.exists():
            return
        demo = json.loads(demo_file.read_text(encoding="utf-8"))
        for entry in demo["agents"]:
            if self.registry.get(entry["username"]):
                continue
            await self.enroll(AgentInput(**entry), demo["mot_de_passe_demo"], auteur="initialisation")
