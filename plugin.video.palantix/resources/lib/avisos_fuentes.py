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


def plataformas(perfil, ficha, ids):
    with closing(_abrir(perfil)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS plataformas (id TEXT PRIMARY KEY, ficha TEXT, ids TEXT, "
                   "revision REAL DEFAULT 0, resultado TEXT DEFAULT '')")
        db.execute("INSERT OR REPLACE INTO plataformas (id,ficha,ids) VALUES (?,?,?)",
                   ("%s:%s" % (ficha["tipo"], ficha["tmdb_id"]), json.dumps(ficha), json.dumps(ids)))


def lista_plataformas(perfil, pendientes=False, ahora=0):
    if not os.path.isfile(os.path.join(perfil, "avisos-fuentes.sqlite")):
        return []
    with closing(_abrir(perfil)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='plataformas'").fetchone():
            return []
        sql = "SELECT id,ficha,ids,resultado FROM plataformas"
        if pendientes:
            filas = db.execute(sql + " WHERE resultado='' AND revision<=? ORDER BY revision,rowid LIMIT 4", (ahora,))
        else:
            filas = db.execute(sql + " ORDER BY rowid DESC")
        return [(clave, json.loads(ficha), json.loads(ids), resultado) for clave, ficha, ids, resultado in filas]


def registrar_plataforma(perfil, clave, ids, revision, resultado=""):
    with closing(_abrir(perfil)) as db, db:
        return db.execute("UPDATE plataformas SET revision=?,resultado=? WHERE id=? AND ids=? AND resultado=''",
                          (revision, resultado, clave, json.dumps(ids))).rowcount == 1


def quitar_plataformas(perfil, clave):
    with closing(_abrir(perfil)) as db, db:
        db.execute("DELETE FROM plataformas WHERE id=?", (clave,))


def proveedores_disponibles(datos, ids):
    """Cuenta ofertas de suscripción y gratuitas, con o sin anuncios."""
    return list(dict.fromkeys(p["provider_name"]
                for modalidad in ("flatrate", "free", "ads") for p in datos.get(modalidad, [])
                if p.get("provider_id") in ids and p.get("provider_name")))
