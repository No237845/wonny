"""Client de l'API d'administration Synapse (réseau Docker interne uniquement).

Documentation : https://element-hq.github.io/synapse/latest/usage/administration/admin_api/
"""

import hashlib
import hmac
from urllib.parse import quote

import httpx

MEGOLM_ALGORITHM = "m.megolm.v1.aes-sha2"
CLASSIFICATION_EVENT = "bf.gouv.kibare.classification"


def registration_mac(shared_secret: str, nonce: str, username: str, password: str, admin: bool) -> str:
    """HMAC-SHA1 exigé par l'API d'inscription par secret partagé de Synapse.

    Format imposé par Synapse : nonce, nom d'utilisateur, mot de passe et
    "admin"/"notadmin" séparés par un octet nul. On utilise le module standard
    `hmac` : aucune primitive cryptographique n'est réimplémentée.
    """
    mac = hmac.new(shared_secret.encode(), digestmod=hashlib.sha1)
    mac.update(nonce.encode())
    mac.update(b"\x00")
    mac.update(username.encode())
    mac.update(b"\x00")
    mac.update(password.encode())
    mac.update(b"\x00")
    mac.update(b"admin" if admin else b"notadmin")
    return mac.hexdigest()


class SynapseError(RuntimeError):
    pass


class SynapseAdmin:
    def __init__(self, base_url: str, server_name: str, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.server_name = server_name
        self.token: str | None = None
        self.client = client or httpx.AsyncClient(timeout=20)

    def user_id(self, localpart: str) -> str:
        return f"@{localpart}:{self.server_name}"

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        response = await self.client.request(method, self.base_url + path, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise SynapseError(f"{method} {path} -> {response.status_code} {response.text}")
        return response.json() if response.content else {}

    # --- Compte de service ---------------------------------------------------

    async def register_service_account(self, shared_secret: str, localpart: str, password: str) -> str:
        """Crée le compte administrateur technique de la console et renvoie son jeton."""
        nonce = (await self._request("GET", "/_synapse/admin/v1/register"))["nonce"]
        body = {
            "nonce": nonce,
            "username": localpart,
            "password": password,
            "admin": True,
            "mac": registration_mac(shared_secret, nonce, localpart, password, True),
        }
        result = await self._request("POST", "/_synapse/admin/v1/register", json=body)
        self.token = result["access_token"]
        return self.token

    async def whoami(self) -> str:
        return (await self._request("GET", "/_matrix/client/v3/account/whoami"))["user_id"]

    # --- Agents ----------------------------------------------------------------

    async def ensure_user(self, localpart: str, displayname: str) -> None:
        """Pré-crée le compte Matrix (sans mot de passe) pour l'annuaire.

        L'agent s'y connectera exclusivement via Keycloak (OIDC).
        """
        await self._request(
            "PUT",
            f"/_synapse/admin/v2/users/{quote(self.user_id(localpart))}",
            json={"displayname": displayname, "admin": False},
        )

    async def list_devices(self, localpart: str) -> list[dict]:
        result = await self._request("GET", f"/_synapse/admin/v2/users/{quote(self.user_id(localpart))}/devices")
        return result.get("devices", [])

    async def deactivate(self, localpart: str) -> None:
        """Désactive le compte : supprime tous ses appareils et jetons d'accès,
        et le retire de tous ses salons. Les clients restants renouvellent
        alors leur session Megolm : l'agent ne peut plus rien déchiffrer de neuf."""
        await self._request(
            "POST",
            f"/_synapse/admin/v1/deactivate/{quote(self.user_id(localpart))}",
            json={"erase": False},
        )

    # --- Salons classifiés ---------------------------------------------------

    async def create_classified_room(
        self,
        name: str,
        niveau: str,
        max_lifetime_ms: int | None,
        members: list[str],
        moderators: list[str],
    ) -> str:
        """Crée un salon chiffré, sur invitation, à historique restreint.

        Le compte de service quitte le salon juste après sa création : il n'a
        aucun appareil et n'a donc jamais reçu de clé de déchiffrement.
        """
        me = await self.whoami()
        initial_state = [
            {"type": "m.room.encryption", "state_key": "", "content": {"algorithm": MEGOLM_ALGORITHM}},
            {"type": "m.room.history_visibility", "state_key": "", "content": {"history_visibility": "joined"}},
            {"type": "m.room.guest_access", "state_key": "", "content": {"guest_access": "forbidden"}},
            {"type": CLASSIFICATION_EVENT, "state_key": "", "content": {"niveau": niveau}},
        ]
        if max_lifetime_ms:
            initial_state.append(
                {"type": "m.room.retention", "state_key": "", "content": {"max_lifetime": max_lifetime_ms}}
            )
        power_users = {me: 100, **{self.user_id(m): 100 for m in moderators}}
        body = {
            "name": f"[{niveau}] {name}",
            "preset": "private_chat",
            "visibility": "private",
            "invite": [self.user_id(m) for m in members],
            "initial_state": initial_state,
            "power_level_content_override": {
                "users": power_users,
                # Seuls les modérateurs peuvent inviter dans un salon classifié.
                "invite": 50,
            },
        }
        room_id = (await self._request("POST", "/_matrix/client/v3/createRoom", json=body))["room_id"]
        await self._request("POST", f"/_matrix/client/v3/rooms/{quote(room_id)}/leave", json={})
        return room_id
