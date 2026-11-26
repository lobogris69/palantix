"""Filtros del explorador de TMDB y caché de sus páginas."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
import sqlite3
import time

ORDENES = {"popular": "Populares", "nuevo": "Novedades", "valorado": "Mejor valoradas"}
DURACIONES = {"0": "Cualquier duración", "99": "Menos de 100 min", "120": "Hasta 120 min"}
ESTADOS = {"todos": "Todas", "emision": "En emisión", "terminadas": "Terminadas", "seguimiento": "En seguimiento"}
FUENTES = {"todas": "Todas", "confirmadas": "Con fuente confirmada", "pendientes": "Por comprobar"}
GEN_DESTACADOS = {
    "movie": [(28, "Acción"), (35, "Comedia"), (878, "Ciencia ficción"), (27, "Terror"),
              (53, "Suspense"), (99, "Documental")],
    "tv": [(18, "Drama"), (35, "Comedia"), (10765, "Ciencia ficción y fantasía"),
           (80, "Crimen"), (16, "Animación"), (99, "Documental")],
}


def filtros(parametros):
    resultado = {}
    for clave, opciones in (("orden", ORDENES), ("duracion", DURACIONES), ("estado", ESTADOS), ("fuente", FUENTES)):
        valor = parametros.get(clave)
        resultado[clave] = valor if valor in opciones else next(iter(opciones))
    return resultado


def consulta(tipo, genero, filtros, pagina):
    estreno = "primary_release_date" if tipo == "movie" else "first_air_date"
    sort = {"popular": "popularity.desc", "nuevo": estreno + ".desc", "valorado": "vote_average.desc"}
    opciones = {"page": pagina, "sort_by": sort[filtros["orden"]],
                estreno + ".lte": time.strftime("%Y-%m-%d")}
    if genero:
        opciones["with_genres"] = genero
    if filtros["orden"] == "valorado":
        opciones["vote_count.gte"] = 25
    if tipo == "movie" and filtros["duracion"] != "0":
        opciones["with_runtime.lte"] = filtros["duracion"]
    if tipo == "tv" and filtros["estado"] in ("emision", "terminadas"):
        opciones["with_status"] = "0" if filtros["estado"] == "emision" else "3|4"
    return opciones


def seguidas(t, carpeta, series, genero, orden, pagina):
    """Parte del seguimiento local, incluso cuando las series no son populares."""
    def ficha(fila):
        sid, anterior = fila
        try:
            datos, _ = cargar(t, carpeta, "tv", {}, sid=sid)
        except (OSError, ValueError, sqlite3.Error):
            if genero:
                return None
            datos = {"id": int(sid), "name": anterior.get("titulo"), "poster_path": anterior.get("poster"),
                     "first_air_date": str(anterior.get("anio") or "")}
        if genero and not any(str(g["id"]) == genero for g in datos.get("genres", [])):
            return None
        return datos

    with ThreadPoolExecutor(max_workers=4) as pool:
        resultados = [r for r in pool.map(ficha, series.items()) if r is not None]
    campo = {"nuevo": "first_air_date", "valorado": "vote_average", "popular": "popularity"}[orden]
    defecto = "" if orden == "nuevo" else 0
    resultados.sort(key=lambda r: r.get(campo) or defecto, reverse=True)
    limite = 20
    return {"results": resultados[(pagina - 1) * limite:pagina * limite],
            "total_pages": max(1, (len(resultados) + limite - 1) // limite)}


def cargar(t, carpeta, tipo, opciones, sid=None):
    clave = json.dumps([t.idioma, t.region, tipo, opciones, sid], sort_keys=True)
    os.makedirs(carpeta, exist_ok=True)
    with closing(sqlite3.connect(os.path.join(carpeta, "explorar.sqlite"))) as db:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS paginas (clave TEXT PRIMARY KEY, fecha REAL, datos TEXT)")
        fila = db.execute("SELECT fecha, datos FROM paginas WHERE clave=?", (clave,)).fetchone()
        ahora = time.time()
        if fila and ahora - fila[0] < 900:
            return json.loads(fila[1]), False
        try:
            if sid is not None:
                datos = t.detalle(sid) if tipo == "movie" else t.serie(sid)
            else:
                datos = t.explorar(tipo, opciones)
        except (OSError, ValueError):
            if fila:
                return json.loads(fila[1]), True
            raise
        with db:
            db.execute("DELETE FROM paginas WHERE fecha < ?", (ahora - 7 * 86400,))
            db.execute("INSERT OR REPLACE INTO paginas VALUES (?,?,?)", (clave, ahora, json.dumps(datos)))
        return datos, False
