"""Client de l'API d'administration Keycloak, authentifié par le compte de
service du client "kibare-console" (flux OAuth2 client_credentials)."""

import time
from urllib.parse import quote

import httpx


class KeycloakError(RuntimeError):
    pass


class KeycloakAdmin:
    def __init__(self, base_url: str, realm: str, client_id: str, client_secret: str,
                 client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.client = client or httpx.AsyncClient(timeout=20)
        self._token: str | None = None
        self._token_expiry = 0.0

    async def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expiry:
            return self._token
        response = await self.client.post(
            f"{self.base_url}/realms/{self.realm}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        if response.status_code != 200:
            raise KeycloakError(f"Jeton de service refusé : {response.status_code} {response.text}")
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expiry = time.monotonic() + payload.get("expires_in", 60) - 10
        return self._token

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        token = await self._access_token()
        response = await self.client.request(
            method,
            f"{self.base_url}/admin/realms/{self.realm}{path}",
            headers={"Authorization": f"Bearer {token}"},
            **kwargs,
        )
        if response.status_code >= 400:
            raise KeycloakError(f"{method} {path} -> {response.status_code} {response.text}")
        return response

    async def find_user(self, username: str) -> dict | None:
        response = await self._request("GET", "/users", params={"username": username, "exact": "true"})
        users = response.json()
        return users[0] if users else None

    async def create_user(self, username: str, first_name: str, last_name: str, password: str,
                          roles: list[str]) -> str:
        """Crée un agent. À sa première connexion, Keycloak l'oblige à
        enregistrer un second facteur TOTP (application d'authentification)."""
        await self._request(
            "POST",
            "/users",
            json={
                "username": username,
                "firstName": first_name,
                "lastName": last_name,
                "enabled": True,
                "requiredActions": ["CONFIGURE_TOTP"],
                "credentials": [{"type": "password", "value": password, "temporary": False}],
            },
        )
        user = await self.find_user(username)
        if user is None:
            raise KeycloakError(f"Utilisateur {username} introuvable après création")
        await self.assign_realm_roles(user["id"], roles)
        return user["id"]

    async def assign_realm_roles(self, user_id: str, roles: list[str]) -> None:
        representations = [
            (await self._request("GET", f"/roles/{quote(role)}")).json() for role in roles
        ]
        await self._request("POST", f"/users/{user_id}/role-mappings/realm", json=representations)

    async def disable_and_logout(self, user_id: str) -> None:
        """Bloque toute nouvelle connexion et ferme les sessions SSO ouvertes."""
        await self._request("PUT", f"/users/{user_id}", json={"enabled": False})
        await self._request("POST", f"/users/{user_id}/logout")
