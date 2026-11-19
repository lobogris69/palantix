"""Caché de disponibilidad de películas. Guarda resultados, nunca enlaces de vídeo."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
import sqlite3
import time


def filtrar(peliculas, consultar, carpeta, configuracion, progreso=lambda hechos, total: True):
    if not peliculas:
        return []

    clave = sha256(json.dumps(configuracion, sort_keys=True).encode()).hexdigest()
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, "disponibilidad.sqlite")
    ids = list(dict.fromkeys(str(p["id"]) for p in peliculas))
    pendientes = {str(p["id"]): p for p in peliculas}
    ahora = int(time.time())
    with sqlite3.connect(ruta) as db:
        db.execute("CREATE TABLE IF NOT EXISTS peliculas (config TEXT, id TEXT, disponible INTEGER, "
                   "caduca INTEGER, PRIMARY KEY (config, id))")
        db.execute("DELETE FROM peliculas WHERE caduca <= ?", (ahora,))
        encontrados = dict(db.execute("SELECT id, disponible FROM peliculas WHERE config = ?", (clave,)))

    faltan = [i for i in ids if i not in encontrados]
    nuevos = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for inicio in range(0, len(faltan), 6):
            if not progreso(len(ids) - len(faltan) + inicio, len(ids)):
                break
            lote = faltan[inicio:inicio + 6]
            for i, disponible in zip(lote, pool.map(consultar, (pendientes[i] for i in lote))):
                if disponible is None:
                    continue
                encontrados[i] = disponible
                ttl = 1800 if disponible else 120
                nuevos.append((clave, i, int(disponible), int(time.time()) + ttl))

    if nuevos:
        with sqlite3.connect(ruta) as db:
            db.executemany("INSERT OR REPLACE INTO peliculas VALUES (?, ?, ?, ?)", nuevos)
    return [p for p in peliculas if encontrados.get(str(p["id"]))]
