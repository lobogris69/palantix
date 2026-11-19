"""Índice local de disponibilidad de películas."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from hashlib import sha256
import json
import os
import sqlite3
import time

DIA = 86400


def _clave(configuracion):
    return sha256(json.dumps(configuracion, sort_keys=True).encode()).hexdigest()


@contextmanager
def _abrir(carpeta):
    os.makedirs(carpeta, exist_ok=True)
    db = sqlite3.connect(os.path.join(carpeta, "disponibilidad.sqlite"))
    try:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS peliculas (config TEXT, id TEXT, disponible INTEGER, "
                       "caduca INTEGER, PRIMARY KEY (config, id))")
            db.execute("CREATE TABLE IF NOT EXISTS pendientes (config TEXT, id TEXT, pelicula TEXT, "
                       "encolada INTEGER, PRIMARY KEY (config, id))")
            db.execute("CREATE TABLE IF NOT EXISTS estado (config TEXT PRIMARY KEY, comprobado INTEGER)")
            yield db
    finally:
        db.close()


def filtrar(peliculas, carpeta, configuracion):
    """Devuelve títulos ya confirmados y si queda trabajo por hacer."""
    if not peliculas:
        return [], False

    clave = _clave(configuracion)
    ahora = int(time.time())
    candidatos = {str(p["id"]): p for p in peliculas}
    with _abrir(carpeta) as db:
        marcadores = ",".join("?" for _ in candidatos)
        filas = db.execute(
            f"SELECT id, disponible, caduca FROM peliculas WHERE config = ? AND id IN ({marcadores})",
            (clave, *candidatos))
        guardadas = {i: (disponible, caduca) for i, disponible, caduca in filas}
        pendientes = []
        for i, peli in candidatos.items():
            if guardadas.get(i, (0, 0))[1] <= ahora:
                ficha = {k: peli[k] for k in ("id", "title", "original_title", "release_date", "imdb_id", "tmdb_id", "temporada", "episodio") if k in peli}
                pendientes.append((clave, i, json.dumps(ficha), ahora))
        if pendientes:
            db.executemany("INSERT OR IGNORE INTO pendientes VALUES (?, ?, ?, ?)", pendientes)

    visibles = []
    for peli in peliculas:
        disponible, caduca = guardadas.get(str(peli["id"]), (0, 0))
        if disponible and caduca + 7 * DIA > ahora:
            visibles.append(peli)
    return visibles, bool(pendientes)


def comprobar_lote(carpeta, configuracion, consultar):
    ruta = os.path.join(carpeta, "disponibilidad.sqlite")
    if not os.path.isfile(ruta):
        return
    clave = _clave(configuracion)
    ahora = int(time.time())
    with _abrir(carpeta) as db:
        db.execute("DELETE FROM pendientes WHERE encolada < ?", (ahora - DIA,))
        db.execute("DELETE FROM peliculas WHERE caduca < ?", (ahora - 7 * DIA,))
        lote = list(db.execute("SELECT id, pelicula FROM pendientes WHERE config = ? ORDER BY rowid LIMIT 4", (clave,)))
    if not lote:
        return

    with ThreadPoolExecutor(max_workers=4) as pool:
        resultados = list(pool.map(consultar, (json.loads(p) for _, p in lote)))
    ahora = int(time.time())
    with _abrir(carpeta) as db:
        db.executemany("INSERT OR REPLACE INTO peliculas VALUES (?, ?, ?, ?)",
                       [(clave, i, int(disponible), ahora + (DIA if disponible else 3600))
                        for (i, _), disponible in zip(lote, resultados)])
        db.executemany("DELETE FROM pendientes WHERE config = ? AND id = ?", [(clave, i) for i, _ in lote])
        db.execute("INSERT OR REPLACE INTO estado VALUES (?, ?)", (clave, ahora))


def resumen(carpeta, configuracion):
    if not os.path.isfile(os.path.join(carpeta, "disponibilidad.sqlite")):
        return 0, 0, None
    clave = _clave(configuracion)
    ahora = int(time.time())
    with _abrir(carpeta) as db:
        disponibles = db.execute(
            "SELECT count(*) FROM peliculas WHERE config = ? AND disponible = 1 AND caduca > ?",
            (clave, ahora - 7 * DIA)).fetchone()[0]
        pendientes = db.execute("SELECT count(*) FROM pendientes WHERE config = ? AND encolada >= ?",
                               (clave, ahora - DIA)).fetchone()[0]
        ultima = db.execute("SELECT comprobado FROM estado WHERE config = ?", (clave,)).fetchone()
    return disponibles, pendientes, ultima[0] if ultima else None
