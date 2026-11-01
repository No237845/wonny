"""Tests automatisés des fonctions de sécurité de la console."""

import base64
import hashlib
import hmac
from pathlib import Path

import httpx
import pytest
import respx

from app import auth
from app.config import Settings
from app.registry import Registry
from app.services import AgentInput, EnrollmentError, Kibare
from app.synapse import registration_mac
from scripts.init_secrets import SECRET_NAMES, ensure_secrets, render


# --- Doubles de test pour Keycloak et Synapse -----------------------------------

class FakeKeycloak:
    def __init__(self):
        self.users: dict[str, dict] = {}
        self.calls: list[str] = []

    async def find_user(self, username):
        return self.users.get(username)

    async def create_user(self, username, first_name, last_name, password, roles):
        self.users[username] = {"id": f"id-{username}", "enabled": True, "roles": roles}
        return self.users[username]["id"]

    async def disable_and_logout(self, user_id):
        self.calls.append(f"keycloak.disable:{user_id}")
        for user in self.users.values():
            if user["id"] == user_id:
                user["enabled"] = False


class FakeSynapse:
    def __init__(self):
        self.users: dict[str, dict] = {}
        self.calls: list[str] = []
        self.rooms: list[dict] = []

    async def ensure_user(self, localpart, displayname):
        self.users[localpart] = {"displayname": displayname, "devices": ["TELEPHONE", "PC"], "active": True}

    async def list_devices(self, localpart):
        return [{"device_id": d} for d in self.users[localpart]["devices"]]

    async def deactivate(self, localpart):
        self.calls.append(f"synapse.deactivate:{localpart}")
        self.users[localpart].update(active=False, devices=[])

    async def create_classified_room(self, name, niveau, max_lifetime_ms, members, moderators):
        self.rooms.append({"name": name, "niveau": niveau, "ttl": max_lifetime_ms, "members": members})
        return "!salon:kibare.local"


@pytest.fixture
def kibare(tmp_path):
    return Kibare(FakeKeycloak(), FakeSynapse(), Registry(tmp_path / "r.sqlite3"), tmp_path)


async def enroll(kibare, username="awa.sawadogo", roles=("agent",)):
    await kibare.enroll(AgentInput(username, "Awa", "SAWADOGO", "Santé", "Directrice", list(roles)),
                        "Kibare-Demo-2026", "admin.dgtd")


# --- Enrôlement -----------------------------------------------------------------

async def test_enrolement_cree_les_comptes_keycloak_et_matrix(kibare):
    await enroll(kibare)
    assert "awa.sawadogo" in kibare.keycloak.users
    assert "awa.sawadogo" in kibare.synapse.users
    assert kibare.registry.get("awa.sawadogo")["statut"] == "actif"


@pytest.mark.parametrize("username", ["Awa", "awa sawadogo", "@awa:x", "a", "../admin"])
async def test_enrolement_refuse_les_identifiants_invalides(kibare, username):
    with pytest.raises(EnrollmentError):
        await enroll(kibare, username)


async def test_enrolement_refuse_les_doublons(kibare):
    await enroll(kibare)
    with pytest.raises(EnrollmentError):
        await enroll(kibare)


# --- Révocation -----------------------------------------------------------------

async def test_revocation_coupe_keycloak_puis_tous_les_appareils(kibare):
    await enroll(kibare)
    await kibare.revoke("awa.sawadogo", "Perte ou vol du téléphone", "admin.dgtd")

    assert kibare.keycloak.users["awa.sawadogo"]["enabled"] is False
    assert kibare.synapse.users["awa.sawadogo"]["devices"] == []
    assert kibare.synapse.users["awa.sawadogo"]["active"] is False
    # Keycloak d'abord : aucune reconnexion possible pendant la désactivation Matrix.
    assert kibare.keycloak.calls == ["keycloak.disable:id-awa.sawadogo"]
    assert kibare.synapse.calls == ["synapse.deactivate:awa.sawadogo"]
    agent = kibare.registry.get("awa.sawadogo")
    assert agent["statut"] == "révoqué" and agent["motif"] == "Perte ou vol du téléphone"
    assert kibare.registry.journal()[0]["action"] == "RÉVOCATION"


async def test_revocation_d_un_agent_inconnu_refusee(kibare):
    with pytest.raises(EnrollmentError):
        await kibare.revoke("intrus", "Départ ou mutation", "admin.dgtd")


async def test_un_agent_revoque_ne_peut_pas_etre_invite_dans_un_salon(kibare):
    await enroll(kibare)
    await enroll(kibare, "issa.compaore")
    await kibare.revoke("issa.compaore", "Départ ou mutation", "admin.dgtd")
    with pytest.raises(EnrollmentError):
        await kibare.create_classified_room("Crise", "CONFIDENTIEL", ["awa.sawadogo", "issa.compaore"], [],
                                            "admin.dgtd")


async def test_un_compte_non_enrole_ne_peut_pas_etre_invite(kibare):
    await enroll(kibare)
    with pytest.raises(EnrollmentError):
        await kibare.create_classified_room("Crise", "CONFIDENTIEL", ["awa.sawadogo", "intrus"], [],
                                            "admin.dgtd")


async def test_salon_confidentiel_expire_en_sept_jours(kibare):
    await enroll(kibare)
    await kibare.create_classified_room("Crise", "CONFIDENTIEL", ["awa.sawadogo"], [], "admin.dgtd")
    assert kibare.synapse.rooms[0]["ttl"] == 7 * 24 * 3600 * 1000


# --- Secret partagé Synapse -------------------------------------------------------

def test_registration_mac_suit_le_format_synapse():
    attendu = hmac.new(b"secret", b"nonce\x00bob\x00pw\x00admin", hashlib.sha1).hexdigest()
    assert registration_mac("secret", "nonce", "bob", "pw", True) == attendu
    assert registration_mac("secret", "nonce", "bob", "pw", False) != attendu


# --- Génération des secrets -------------------------------------------------------

def test_secrets_generes_une_seule_fois(tmp_path):
    fichier = tmp_path / "secrets.env"
    premiers = ensure_secrets(fichier)
    assert set(SECRET_NAMES) <= set(premiers)
    assert len(set(premiers.values())) == len(SECRET_NAMES)  # tous différents
    assert ensure_secrets(fichier) == premiers  # conservés au redémarrage


def test_modele_avec_variable_manquante_refuse():
    with pytest.raises(ValueError):
        render("password: ${INCONNU}", {})


# --- Connexion OIDC de la console ---------------------------------------------------

SETTINGS = Settings("kibare.local", "http://synapse:8008", "http://keycloak:8080", "http://localhost:8180",
                    "http://localhost:8090", "mtdpce", "kibare-console", "s3cret", "reg", "sess",
                    Path("."), Path("."))
TOKEN_URL = "http://keycloak:8080/realms/mtdpce/protocol/openid-connect/token"
USERINFO_URL = "http://keycloak:8080/realms/mtdpce/protocol/openid-connect/userinfo"


def test_pkce_s256():
    verifier, challenge = auth.pkce_pair()
    attendu = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == attendu


async def test_callback_avec_state_falsifie_rejete():
    session = {}
    auth.login_url(SETTINGS, session)
    async with httpx.AsyncClient() as client:
        with pytest.raises(auth.AuthError):
            await auth.complete_login(SETTINGS, session, "code", "state-falsifie", client)


@respx.mock
async def test_console_refusee_sans_role_admin():
    respx.post(TOKEN_URL).respond(json={"access_token": "jeton"})
    respx.get(USERINFO_URL).respond(json={"preferred_username": "issa.compaore", "roles": ["agent"]})
    session = {}
    auth.login_url(SETTINGS, session)
    async with httpx.AsyncClient() as client:
        with pytest.raises(auth.AuthError):
            await auth.complete_login(SETTINGS, session, "code", session["oidc_state"], client)


@respx.mock
async def test_console_acceptee_avec_role_admin():
    respx.post(TOKEN_URL).respond(json={"access_token": "jeton"})
    respx.get(USERINFO_URL).respond(json={"preferred_username": "admin.dgtd", "roles": ["admin"]})
    session = {}
    auth.login_url(SETTINGS, session)
    async with httpx.AsyncClient() as client:
        admin = await auth.complete_login(SETTINGS, session, "code", session["oidc_state"], client)
    assert admin["username"] == "admin.dgtd"
    assert "oidc_state" not in session  # le state est à usage unique
