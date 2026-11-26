"""Lo que se ha dejado a medias (películas y capítulos), para reanudar y para la barra de progreso.

progreso.json en el perfil: {clave: {tipo, tmdb, s, e, titulo, original, anio, poster, fanart, pos, total, fecha}}
clave = "p:<tmdb>" (película) o "e:<tmdb serie>:<s>:<e>" (capítulo)
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import sqlite3
import time

from . import explorar, ganchos

MINIMO_SEG = 60     # menos de un minuto visto: no merece la pena apuntarlo
TERMINADO = 0.90    # a partir de aquí se considera vista entera


def clave(meta):
    if meta.get("tipo") == "episodio":
        return "e:%s:%s:%s" % (meta.get("tmdb"), meta.get("s"), meta.get("e"))
    return "p:%s" % meta.get("tmdb")


def _ruta(perfil):
    return os.path.join(perfil, "progreso.json")


def leer(perfil):
    try:
        with open(_ruta(perfil), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _guardar(perfil, datos):
    os.makedirs(perfil, exist_ok=True)
    with open(_ruta(perfil), "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)


def apuntar(perfil, meta, pos, total, ahora=None):
    """Guarda o borra según cuánto se ha visto. Devuelve 'guardado', 'borrado' o 'nada'."""
    if not meta.get("tmdb") or total <= 0:
        return "nada"
    datos = leer(perfil)
    k = clave(meta)
    if pos / total >= TERMINADO:
        if datos.pop(k, None) is not None:
            _guardar(perfil, datos)
        return "borrado"
    if pos < MINIMO_SEG:
        return "nada"
    d = {c: meta.get(c, "") for c in ("tipo", "tmdb", "s", "e", "titulo", "original", "anio", "poster", "fanart")}
    anterior = datos.get(k, {})
    for campo in ("poster", "fanart"):
        d[campo] = d[campo] or anterior.get(campo, "")
    d.update(pos=int(pos), total=int(total), fecha=ahora or time.time())
    datos[k] = d
    _guardar(perfil, datos)
    return "guardado"


def de(perfil, meta):
    return leer(perfil).get(clave(meta))


def peliculas(perfil):
    """Películas a medias, la más reciente primero."""
    return sorted((d for k, d in leer(perfil).items() if k.startswith("p:")), key=lambda d: -d.get("fecha", 0))


def con_caratulas(peliculas, t, cache):
    """Recupera las carátulas que faltan en puntos de reanudación de versiones antiguas."""
    if t is None or all(d.get("poster") for d in peliculas):
        return peliculas

    def recuperar(d):
        if d.get("poster"):
            return d
        try:
            ficha, _ = explorar.cargar(t, cache, "movie", {}, sid=int(d["tmdb"]))
        except (OSError, ValueError, KeyError, sqlite3.Error):
            return d
        return dict(d, poster=ficha.get("poster_path") or "",
                    fanart=d.get("fanart") or ficha.get("backdrop_path") or "")

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(recuperar, peliculas))


def quitar(perfil, k):
    datos = leer(perfil)
    if datos.pop(k, None) is not None:
        _guardar(perfil, datos)


def hhmmss(seg):
    seg = int(seg)
    h, m, s = seg // 3600, seg % 3600 // 60, seg % 60
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


@ganchos.registrar
class Progreso:
    """Gancho del servicio: guarda por dónde vas al parar."""

    def __init__(self, perfil=None):
        if perfil is None:
            import xbmcaddon
            import xbmcvfs
            perfil = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo("profile"))
        self.perfil = perfil
        self.pos = self.total = 0

    def al_empezar(self, meta, reproductor):
        self.pos = self.total = 0

    def al_avanzar(self, meta, reproductor, actual, total):
        self.pos, self.total = actual, total

    def al_parar(self, meta, reproductor, terminado):
        if terminado:
            self.pos = self.total
        apuntar(self.perfil, meta, self.pos, self.total)
