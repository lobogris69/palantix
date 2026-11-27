"""Filtros del explorador de TMDB y caché de sus páginas."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
import json
import os
import sqlite3
import time
import unicodedata

ORDENES = {"popular": "Popularidad", "nuevo": "Año · Recientes", "antiguo": "Año · Antiguas",
           "valorado": "Mejor valoradas", "titulo": "Título A–Z"}
ORDENES_BUSQUEDA = {"origen": "Relevancia", **ORDENES}
ORDENES_LISTADO = {"origen": "Orden original", **ORDENES}
MAX_PAGINAS_BUSQUEDA = 5
DURACIONES = {"0": "Cualquier duración", "99": "Menos de 100 min", "120": "Hasta 120 min"}
ESTADOS = {"todos": "Todas", "emision": "En emisión", "terminadas": "Terminadas", "seguimiento": "En seguimiento"}
FUENTES = {"todas": "Todas", "confirmadas": "Con fuente confirmada", "pendientes": "Por comprobar"}
GEN_DESTACADOS = {
    "movie": [(28, "Acción"), (35, "Comedia"), (53, "Suspense"), (12, "Aventura"),
              (18, "Drama"), (878, "Ciencia ficción"), (27, "Terror"), (80, "Crimen"),
              (16, "Animación"), (14, "Fantasía"), (10749, "Romance"), (9648, "Misterio"),
              (10751, "Familiar"), (99, "Documental")],
    "tv": [(18, "Drama"), (35, "Comedia"), (10765, "Ciencia ficción y fantasía"),
           (80, "Crimen"), (16, "Animación"), (99, "Documental")],
}


@dataclass
class Resultados:
    filas: list
    total: int
    guardados: bool
    confirmadas: set
    pendientes: set

    def estado_de(self, tid):
        tid = str(tid)
        if tid in self.confirmadas:
            return "Con fuente confirmada"
        return "Por comprobar" if tid in self.pendientes else "Sin fuente confirmada"


def campos_filtro(tipo, incluir_orden=True):
    orden = ("orden", "Orden", ORDENES)
    if tipo == "movie":
        campos = [("duracion", "Duración", DURACIONES), ("fuente", "Disponibilidad", FUENTES)]
    else:
        campos = [("estado", "Estado", ESTADOS)]
    return [orden, *campos] if incluir_orden else campos


def elegir_filtros(tipo, parametros, seleccionar, incluir_orden=True):
    elegidos = filtros(parametros)
    for clave, titulo, opciones in campos_filtro(tipo, incluir_orden):
        claves = list(opciones)
        n = seleccionar(titulo, list(opciones.values()), preselect=claves.index(elegidos[clave]))
        if n < 0:
            return None
        elegidos[clave] = claves[n]
    return elegidos


def filtros(parametros):
    resultado = {}
    for clave, opciones in (("orden", ORDENES), ("duracion", DURACIONES), ("estado", ESTADOS), ("fuente", FUENTES)):
        valor = parametros.get(clave)
        resultado[clave] = valor if valor in opciones else next(iter(opciones))
    return resultado


def consulta(tipo, genero, filtros, pagina):
    estreno = "primary_release_date" if tipo == "movie" else "first_air_date"
    nombre = "title" if tipo == "movie" else "name"
    sort = {"popular": "popularity.desc", "nuevo": estreno + ".desc", "antiguo": estreno + ".asc",
            "valorado": "vote_average.desc", "titulo": nombre + ".asc"}
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


def ordenar(resultados, tipo, orden):
    campo_fecha, campo_titulo = ("release_date", "title") if tipo == "movie" else ("first_air_date", "name")
    if orden in ("nuevo", "antiguo"):
        con_fecha = [r for r in resultados if r.get(campo_fecha)]
        sin_fecha = [r for r in resultados if not r.get(campo_fecha)]
        return sorted(con_fecha, key=lambda r: r[campo_fecha], reverse=orden == "nuevo") + sin_fecha
    if orden == "titulo":
        def titulo(r):
            nombre = unicodedata.normalize("NFKD", (r.get(campo_titulo) or "").casefold())
            return not nombre, "".join(c for c in nombre if not unicodedata.combining(c))

        return sorted(resultados, key=titulo)
    if orden in ("popular", "valorado"):
        campo = "popularity" if orden == "popular" else "vote_average"
        return sorted(resultados, key=lambda r: r.get(campo) or 0, reverse=True)
    return resultados


def buscar(t, carpeta, tipo, texto, pagina, por_pantalla, orden):
    """Parte de la relevancia de TMDB y ordena juntas sus primeras páginas si se pide otro criterio."""
    metodo = t.buscar if tipo == "movie" else t.s_buscar
    primera = (pagina - 1) * por_pantalla + 1
    inicio = primera if orden == "origen" else 1
    limite = por_pantalla if orden == "origen" else MAX_PAGINAS_BUSQUEDA

    def solicitar():
        primera_pagina = metodo(texto, inicio)
        total = min(int(primera_pagina.get("total_pages", 1)), 500)
        resultados = list(primera_pagina.get("results", []))
        siguientes = range(inicio + 1, min(inicio + limite, total + 1))
        if siguientes:
            with ThreadPoolExecutor(max_workers=4) as pool:
                for datos in pool.map(lambda n: metodo(texto, n), siguientes):
                    resultados.extend(datos.get("results", []))
        return {"results": resultados, "total_pages": total}

    datos, guardados = cargar(t, carpeta, tipo, {"buscar": texto, "inicio": inicio, "limite": limite},
                             solicitar=solicitar)
    total = datos["total_pages"]
    resultados = datos["results"]
    if orden != "origen":
        resultados = ordenar(resultados, tipo, orden)
        resultados = resultados[(pagina - 1) * por_pantalla * 20:pagina * por_pantalla * 20]
    paginas_visibles = min(total, MAX_PAGINAS_BUSQUEDA) if orden != "origen" else total
    return {"page": pagina, "total_pages": -(-paginas_visibles // por_pantalla), "results": resultados,
            "limite_busqueda": total > MAX_PAGINAS_BUSQUEDA and orden != "origen", "guardados": guardados}


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
        if genero and not any(str(g["id"]) == str(genero) for g in datos.get("genres", [])):
            return None
        return datos

    with ThreadPoolExecutor(max_workers=4) as pool:
        resultados = [r for r in pool.map(ficha, series.items()) if r is not None]
    resultados = ordenar(resultados, "tv", orden)
    limite = 20
    return {"results": resultados[(pagina - 1) * limite:pagina * limite],
            "total_pages": max(1, (len(resultados) + limite - 1) // limite)}


def cargar(t, carpeta, tipo, opciones, sid=None, solicitar=None):
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
            if solicitar is not None:
                datos = solicitar()
            elif sid is not None:
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
