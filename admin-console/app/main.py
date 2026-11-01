"""Console d'administration Kibaré (FastAPI)."""

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import auth
from .config import load_settings
from .keycloak import KeycloakAdmin
from .registry import Registry
from .services import MOTIFS_REVOCATION, NIVEAUX, AgentInput, EnrollmentError, Kibare
from .synapse import SynapseAdmin

log = logging.getLogger("kibare")
logging.basicConfig(level=logging.INFO)

settings = load_settings()
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
http = httpx.AsyncClient(timeout=20)


async def bootstrap(kibare: Kibare) -> None:
    """Attend que Synapse et Keycloak répondent, puis prépare la plateforme."""
    for attempt in range(60):
        try:
            await kibare.connect_service_account(settings.registration_shared_secret)
            await kibare.seed_demo(settings.demo_file)
            log.info("Console prête.")
            return
        except Exception as exc:  # services pas encore démarrés
            log.warning("Initialisation en attente (%s/60) : %s", attempt + 1, exc)
            await asyncio.sleep(5)
    raise RuntimeError("Impossible d'initialiser la console.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app.state.kibare = Kibare(
        KeycloakAdmin(settings.keycloak_internal_url, settings.realm, settings.client_id,
                      settings.client_secret, http),
        SynapseAdmin(settings.synapse_url, settings.server_name, http),
        Registry(settings.data_dir / "registre.sqlite3"),
        settings.data_dir,
    )
    await bootstrap(app.state.kibare)
    yield
    await http.aclose()


app = FastAPI(title="Console Kibaré", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret or secrets.token_hex(32),
                   session_cookie="kibare_console", same_site="lax", max_age=3600)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


# --- Utilitaires de session ---------------------------------------------------

def current_admin(request: Request) -> dict:
    admin = request.session.get("admin")
    if not admin:
        raise HTTPException(status_code=303, headers={"Location": "/connexion"})
    return admin


def csrf_token(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]


def check_csrf(request: Request, token: str) -> None:
    if not secrets.compare_digest(request.session.get("csrf", ""), token):
        raise HTTPException(status_code=403, detail="Jeton CSRF invalide")


def render(request: Request, template: str, **context) -> HTMLResponse:
    context.update(request=request, admin=request.session.get("admin"), csrf=csrf_token(request),
                   flash=request.session.pop("flash", None))
    return templates.TemplateResponse(request, template, context)


def flash(request: Request, kind: str, message: str) -> None:
    request.session["flash"] = {"kind": kind, "message": message}


# --- Authentification ---------------------------------------------------------

@app.get("/connexion")
async def connexion(request: Request):
    return render(request, "connexion.html")


@app.get("/login")
async def login(request: Request):
    return RedirectResponse(auth.login_url(settings, request.session), status_code=303)


@app.get("/auth/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    try:
        request.session["admin"] = await auth.complete_login(settings, request.session, code, state, http)
    except auth.AuthError as exc:
        flash(request, "erreur", str(exc))
        return RedirectResponse("/connexion", status_code=303)
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(auth.logout_url(settings), status_code=303)


# --- Annuaire et révocation ---------------------------------------------------

@app.get("/")
async def annuaire(request: Request, ministere: str = ""):
    current_admin(request)
    registry = request.app.state.kibare.registry
    return render(request, "annuaire.html", agents=registry.directory(ministere or None),
                  ministeres=registry.ministeres(), ministere=ministere, motifs=MOTIFS_REVOCATION)


@app.post("/agents/{username}/revoquer")
async def revoquer(request: Request, username: str, motif: str = Form(...), csrf: str = Form(...)):
    admin = current_admin(request)
    check_csrf(request, csrf)
    try:
        await request.app.state.kibare.revoke(username, motif, admin["username"])
        flash(request, "succes", f"{username} est révoqué : accès coupé sur tous ses appareils.")
    except EnrollmentError as exc:
        flash(request, "erreur", str(exc))
    return RedirectResponse("/", status_code=303)


# --- Enrôlement ---------------------------------------------------------------

@app.get("/agents/nouveau")
async def nouvel_agent(request: Request):
    current_admin(request)
    return render(request, "enrolement.html")


@app.post("/agents")
async def enroler(request: Request, username: str = Form(...), prenom: str = Form(...), nom: str = Form(...),
                  ministere: str = Form(...), fonction: str = Form(...), mot_de_passe: str = Form(...),
                  chef_service: bool = Form(False), csrf: str = Form(...)):
    admin = current_admin(request)
    check_csrf(request, csrf)
    roles = ["agent", "chef_service"] if chef_service else ["agent"]
    agent = AgentInput(username.strip().lower(), prenom.strip(), nom.strip().upper(),
                       ministere.strip(), fonction.strip(), roles)
    try:
        await request.app.state.kibare.enroll(agent, mot_de_passe, admin["username"])
    except Exception as exc:
        flash(request, "erreur", f"Enrôlement impossible : {exc}")
        return RedirectResponse("/agents/nouveau", status_code=303)
    flash(request, "succes", f"{agent.prenom} {agent.nom} est enrôlé. Le second facteur sera exigé "
                             "à sa première connexion.")
    return RedirectResponse("/", status_code=303)


# --- Salons classifiés --------------------------------------------------------

@app.get("/salons/nouveau")
async def nouveau_salon(request: Request):
    current_admin(request)
    agents = [a for a in request.app.state.kibare.registry.directory()
              if a["statut"] == "actif" and "agent" in a["roles"].split(",")]
    return render(request, "salon.html", agents=agents, niveaux=NIVEAUX)


@app.post("/salons")
async def creer_salon(request: Request, nom: str = Form(...), niveau: str = Form(...),
                      membres: list[str] = Form(default=[]), moderateurs: list[str] = Form(default=[]),
                      csrf: str = Form(...)):
    admin = current_admin(request)
    check_csrf(request, csrf)
    try:
        await request.app.state.kibare.create_classified_room(nom.strip(), niveau, membres, moderateurs,
                                                             admin["username"])
    except Exception as exc:
        flash(request, "erreur", f"Création impossible : {exc}")
        return RedirectResponse("/salons/nouveau", status_code=303)
    flash(request, "succes", f"Salon [{niveau}] {nom} créé. Les membres ont reçu une invitation.")
    return RedirectResponse("/journal", status_code=303)


@app.get("/journal")
async def journal(request: Request):
    current_admin(request)
    return render(request, "journal.html", entries=request.app.state.kibare.registry.journal())
