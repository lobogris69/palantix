"""Series en seguimiento: se apunta el último capítulo VISTO de cada serie (80 % por defecto o hasta el final).

Fichero seguimiento.json en el perfil del addon: {tmdb_id: {titulo, original, anio, poster, fanart, s, e, fecha}}
El servicio lo rellena (gancho Seguimiento) y main.py lo enseña en «Seguir viendo series».
"""
import json
import os
import time

from . import ganchos

VISTO = 0.80  # a partir de este porcentaje el capítulo cuenta como visto


def umbral_visto(ajustes):
    try:
        return min(95, max(50, int(ajustes("umbral_visto") or 80))) / 100
    except (ValueError, RuntimeError):
        return VISTO


def _ruta(perfil):
    return os.path.join(perfil, "seguimiento.json")


def leer(perfil):
    try:
        with open(_ruta(perfil), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def guardar(perfil, datos):
    os.makedirs(perfil, exist_ok=True)
    with open(_ruta(perfil), "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)


def clave_capitulo(s, e):
    return "%d:%d" % (int(s), int(e))


def esta_visto(datos, s, e):
    clave = clave_capitulo(s, e)
    limite = datos.get("legado", (datos.get("s", 0), datos.get("e", 0)))
    return (clave in datos.get("vistos", [])
            or ((int(s), int(e)) <= tuple(limite) and clave not in datos.get("no_vistos", [])))


def con_historial_trakt(datos, vistos):
    """Combina marcas por episodio sin alterar el seguimiento local ni rellenar huecos."""
    if not vistos:
        return datos
    legado = datos.get("legado", (datos.get("s", 0), datos.get("e", 0)))
    return dict(datos, legado=legado, vistos=frozenset(datos.get("vistos", ())).union(vistos))


def marcar_visto(perfil, meta, ahora=None, visto=True):
    if meta.get("tipo") != "episodio" or not meta.get("tmdb"):
        return
    datos = leer(perfil)
    clave = str(meta["tmdb"])
    previo = datos.get(clave, {})
    s, e = int(meta.get("s") or 0), int(meta.get("e") or 0)
    capitulo = clave_capitulo(s, e)
    limite = previo.get("legado", [previo.get("s", 0), previo.get("e", 0)])
    vistos = set(previo.get("vistos", []))
    no_vistos = set(previo.get("no_vistos", []))
    if visto:
        vistos.add(capitulo)
        no_vistos.discard(capitulo)
    else:
        vistos.discard(capitulo)
        if (s, e) <= tuple(limite):
            no_vistos.add(capitulo)
    ficha = {k: meta.get(k) or previo.get(k, "") for k in ("titulo", "original", "anio", "poster", "fanart")}
    ultimo = max((s, e), (previo.get("s", 0), previo.get("e", 0))) if visto else (
        previo.get("s", 0), previo.get("e", 0))
    ficha.update(s=ultimo[0], e=ultimo[1], fecha=ahora or time.time(), legado=limite,
                 vistos=sorted(vistos), no_vistos=sorted(no_vistos))
    datos[clave] = ficha
    guardar(perfil, datos)


def quitar(perfil, tmdb_id):
    datos = leer(perfil)
    datos.pop(str(tmdb_id), None)
    guardar(perfil, datos)


def ordenadas(perfil):
    """[(tmdb_id, datos)] de la vista más recientemente a la más antigua."""
    return sorted(leer(perfil).items(), key=lambda kv: -kv[1].get("fecha", 0))


@ganchos.registrar
class Seguimiento:
    """Gancho del servicio: mide cuánto se ha visto y apunta el capítulo al terminar."""

    def __init__(self, perfil=None):
        if perfil is None:
            import xbmcaddon
            import xbmcvfs
            perfil = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo("profile"))
        self.perfil = perfil
        self.visto = 0.0
        self.umbral = VISTO

    def al_empezar(self, meta, reproductor):
        self.visto = 0.0
        try:
            import xbmcaddon
            self.umbral = umbral_visto(xbmcaddon.Addon().getSetting)
        except (ImportError, AttributeError, RuntimeError, ValueError):
            self.umbral = VISTO

    def al_avanzar(self, meta, reproductor, actual, total):
        if total > 0:
            self.visto = max(self.visto, actual / total)

    def al_parar(self, meta, reproductor, terminado):
        if terminado or self.visto >= self.umbral:
            marcar_visto(self.perfil, meta)
