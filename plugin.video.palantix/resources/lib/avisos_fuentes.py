"""Títulos que el usuario quiere comprobar, guardados en el perfil de Kodi."""
from contextlib import closing
import json
import os
import sqlite3


def _abrir(perfil):
    os.makedirs(perfil, exist_ok=True)
    db = sqlite3.connect(os.path.join(perfil, "avisos-fuentes.sqlite"))
    with db:
        db.execute("CREATE TABLE IF NOT EXISTS avisos (id TEXT PRIMARY KEY, ficha TEXT, avisado INTEGER DEFAULT 0)")
    return db


def guardar(perfil, ficha):
    with closing(_abrir(perfil)) as db, db:
        db.execute("INSERT OR IGNORE INTO avisos (id,ficha) VALUES (?,?)",
                   (str(ficha["id"]), json.dumps(ficha, ensure_ascii=False)))


def quitar(perfil, clave):
    with closing(_abrir(perfil)) as db, db:
        db.execute("DELETE FROM avisos WHERE id=?", (clave,))


def leer(perfil):
    if not os.path.isfile(os.path.join(perfil, "avisos-fuentes.sqlite")):
        return []
    with closing(_abrir(perfil)) as db:
        return [(json.loads(ficha), bool(avisado)) for ficha, avisado in
                db.execute("SELECT ficha,avisado FROM avisos ORDER BY rowid DESC")]


def avisar(perfil, clave):
    with closing(_abrir(perfil)) as db, db:
        return db.execute("UPDATE avisos SET avisado=1 WHERE id=? AND avisado=0", (str(clave),)).rowcount == 1
