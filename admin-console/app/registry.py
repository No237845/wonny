"""Registre officiel des agents et journal d'audit (SQLite, côté console).

Le registre sert d'annuaire par ministère et par fonction. Le journal garde
la trace horodatée de chaque enrôlement, révocation et création de salon.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    username    TEXT PRIMARY KEY,
    prenom      TEXT NOT NULL,
    nom         TEXT NOT NULL,
    ministere   TEXT NOT NULL,
    fonction    TEXT NOT NULL,
    roles       TEXT NOT NULL,
    statut      TEXT NOT NULL DEFAULT 'actif',
    enrole_le   TEXT NOT NULL,
    revoque_le  TEXT,
    motif       TEXT
);
CREATE TABLE IF NOT EXISTS journal (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    horodatage TEXT NOT NULL,
    auteur  TEXT NOT NULL,
    action  TEXT NOT NULL,
    cible   TEXT NOT NULL,
    details TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Registry:
    def __init__(self, path: Path | str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def get(self, username: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM agents WHERE username = ?", (username,)).fetchone()

    def add_agent(self, username: str, prenom: str, nom: str, ministere: str, fonction: str,
                  roles: list[str]) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO agents (username, prenom, nom, ministere, fonction, roles, enrole_le)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (username, prenom, nom, ministere, fonction, ",".join(roles), now()),
            )

    def mark_revoked(self, username: str, motif: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE agents SET statut = 'révoqué', revoque_le = ?, motif = ? WHERE username = ?",
                (now(), motif, username),
            )

    def directory(self, ministere: str | None = None) -> list[sqlite3.Row]:
        query = "SELECT * FROM agents"
        params: tuple = ()
        if ministere:
            query += " WHERE ministere = ?"
            params = (ministere,)
        return self.db.execute(query + " ORDER BY ministere, nom, prenom", params).fetchall()

    def ministeres(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT ministere FROM agents ORDER BY 1")]

    def log(self, auteur: str, action: str, cible: str, details: str = "") -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO journal (horodatage, auteur, action, cible, details) VALUES (?, ?, ?, ?, ?)",
                (now(), auteur, action, cible, details),
            )

    def journal(self, limit: int = 200) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM journal ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
