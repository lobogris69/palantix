"""Preferencias opcionales de reproducción por serie."""
from contextlib import closing
from pathlib import Path
import sqlite3

AUDIOS = ("", "CAST", "LAT", "VO")
SUBTITULOS = ("", "off", "es", "en")


def leer(perfil, sid):
    ruta = Path(perfil) / "ajustes-series.sqlite"
    if not ruta.is_file():
        return "", ""
    with closing(sqlite3.connect(str(ruta))) as db:
        fila = db.execute("SELECT audio, subs FROM series WHERE id=?", (str(sid),)).fetchone()
    return fila or ("", "")


def guardar(perfil, sid, audio, subs):
    if audio not in AUDIOS or subs not in SUBTITULOS:
        raise ValueError("Preferencias no válidas")
    ruta = Path(perfil) / "ajustes-series.sqlite"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(ruta))) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS series (id TEXT PRIMARY KEY, audio TEXT, subs TEXT)")
        db.execute("INSERT OR REPLACE INTO series VALUES (?,?,?)", (str(sid), audio, subs))
