"""Connexion des administrateurs à la console via Keycloak (OpenID Connect).

Flux « authorization code » avec PKCE :
  1. /login : on génère un `state` (anti-CSRF) et un `code_verifier` PKCE,
     gardés dans la session, puis on redirige le navigateur vers Keycloak ;
  2. l'administrateur saisit mot de passe + code TOTP chez Keycloak ;
  3. /auth/callback : Keycloak renvoie un `code` à usage unique. On vérifie le
     `state`, puis la console échange le code (avec le `code_verifier` et son
     secret client) contre un jeton, directement auprès de Keycloak sur le
     réseau interne ;
  4. avec ce jeton, la console lit l'identité (userinfo) et exige le rôle "admin".

Les primitives (SHA-256, base64, aléa) viennent de la bibliothèque standard.
"""

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx

from .config import Settings


class AuthError(RuntimeError):
    pass


def pkce_pair() -> tuple[str, str]:
    """Renvoie (code_verifier, code_challenge) selon la RFC 7636 (méthode S256)."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def redirect_uri(settings: Settings) -> str:
    return f"{settings.console_public_url}/auth/callback"


def login_url(settings: Settings, session: dict) -> str:
    state = secrets.token_urlsafe(32)
    verifier, challenge = pkce_pair()
    session["oidc_state"] = state
    session["oidc_verifier"] = verifier
    params = {
        "client_id": settings.client_id,
        "response_type": "code",
        "scope": "openid profile",
        "redirect_uri": redirect_uri(settings),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{settings.keycloak_public_url}/realms/{settings.realm}/protocol/openid-connect/auth?{urlencode(params)}"


def logout_url(settings: Settings) -> str:
    params = {"client_id": settings.client_id, "post_logout_redirect_uri": f"{settings.console_public_url}/"}
    return f"{settings.keycloak_public_url}/realms/{settings.realm}/protocol/openid-connect/logout?{urlencode(params)}"


async def complete_login(settings: Settings, session: dict, code: str, state: str,
                         client: httpx.AsyncClient) -> dict:
    expected_state = session.pop("oidc_state", None)
    verifier = session.pop("oidc_verifier", None)
    if not expected_state or not secrets.compare_digest(expected_state, state):
        raise AuthError("Paramètre state invalide : requête rejetée.")

    base = f"{settings.keycloak_internal_url}/realms/{settings.realm}/protocol/openid-connect"
    token_response = await client.post(
        f"{base}/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(settings),
            "client_id": settings.client_id,
            "client_secret": settings.client_secret,
            "code_verifier": verifier,
        },
    )
    if token_response.status_code != 200:
        raise AuthError("Échange du code refusé par Keycloak.")
    access_token = token_response.json()["access_token"]

    userinfo = await client.get(f"{base}/userinfo", headers={"Authorization": f"Bearer {access_token}"})
    if userinfo.status_code != 200:
        raise AuthError("Identité introuvable.")
    claims = userinfo.json()
    if "admin" not in claims.get("roles", []):
        raise AuthError("Accès réservé aux administrateurs Kibaré.")
    return {"username": claims["preferred_username"], "name": claims.get("name", "")}
