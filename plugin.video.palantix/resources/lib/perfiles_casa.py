"""Preferencias compartidas para escoger películas desde el mando."""
from contextlib import closing
from pathlib import Path
import sqlite3


def _abrir(perfil):
    ruta = Path(perfil) / "perfiles-casa.sqlite"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(ruta))
    with db:
        db.execute("CREATE TABLE IF NOT EXISTS perfiles (nombre TEXT PRIMARY KEY COLLATE NOCASE, genero INTEGER, minutos INTEGER)")
        db.execute("CREATE TABLE IF NOT EXISTS vistos (nombre TEXT COLLATE NOCASE, pelicula INTEGER, PRIMARY KEY(nombre,pelicula))")
    return db


def guardar(perfil, nombre, genero, minutos):
    with closing(_abrir(perfil)) as db, db:
        db.execute("INSERT OR REPLACE INTO perfiles VALUES (?,?,?)", (nombre, genero, minutos))


def leer(perfil):
    with closing(_abrir(perfil)) as db:
        return list(db.execute("SELECT nombre,genero,minutos FROM perfiles ORDER BY nombre"))


def marcar(perfil, nombre, pelicula, visto):
    with closing(_abrir(perfil)) as db, db:
        if visto:
            db.execute("INSERT OR IGNORE INTO vistos VALUES (?,?)", (nombre, pelicula))
        else:
            db.execute("DELETE FROM vistos WHERE nombre=? AND pelicula=?", (nombre, pelicula))


def criterios(perfil, primero, segundo):
    with closing(_abrir(perfil)) as db:
        vistos = {i for (i,) in db.execute(
            "SELECT pelicula FROM vistos WHERE nombre IN (?,?) GROUP BY pelicula HAVING count(*)=2",
            (primero[0], segundo[0]))}
    return list(dict.fromkeys(p[1] for p in (primero, segundo) if p[1])), min(primero[2], segundo[2]), vistos
