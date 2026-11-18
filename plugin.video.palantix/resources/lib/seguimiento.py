"""Series en seguimiento: se apunta el último capítulo VISTO de cada serie (85 % o hasta el final).

Fichero seguimiento.json en el perfil del addon: {tmdb_id: {titulo, original, anio, poster, fanart, s, e, fecha}}
El servicio lo rellena (gancho Seguimiento) y main.py lo enseña en «Seguir viendo series».
"""
import json
import os
import time

from . import ganchos

VISTO = 0.85  # a partir de este porcentaje el capítulo cuenta como visto


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


def marcar_visto(perfil, meta, ahora=None):
    if meta.get("tipo") != "episodio" or not meta.get("tmdb"):
        return
    datos = leer(perfil)
    clave = str(meta["tmdb"])
    previo = datos.get(clave, {})
    # no retroceder si se vuelve a ver un capítulo antiguo
    if (previo.get("s", 0), previo.get("e", 0)) > (meta.get("s", 0), meta.get("e", 0)):
        previo["fecha"] = ahora or time.time()
        datos[clave] = previo
    else:
        datos[clave] = {k: meta.get(k, "") for k in ("titulo", "original", "anio", "poster", "fanart")}
        datos[clave].update(s=meta.get("s", 0), e=meta.get("e", 0), fecha=ahora or time.time())
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

    def al_empezar(self, meta, reproductor):
        self.visto = 0.0

    def al_avanzar(self, meta, reproductor, actual, total):
        if total > 0:
            self.visto = max(self.visto, actual / total)

    def al_parar(self, meta, reproductor, terminado):
        if terminado or self.visto >= VISTO:
            marcar_visto(self.perfil, meta)
