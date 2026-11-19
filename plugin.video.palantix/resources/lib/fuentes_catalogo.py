"""Configuración compartida por la reproducción y el índice de fuentes."""
from . import etiquetas
from .providers import ListaURL, Peli, buscar_fuentes
from .providers.stremio import Stremio

IDIOMAS_PRIORIDAD = {
    "CAST": "Castellano",
    "LAT": "Latino",
    "VOSE": "Versión original subtitulada",
    "VO": "Versión original",
}
IDIOMAS_AJUSTE = list(IDIOMAS_PRIORIDAD) + [""]
CALIDADES_AJUSTE = ["4K", "1080p", "720p"]


def _entero(ajustes, clave, defecto):
    try:
        return int(ajustes(clave))
    except ValueError:
        return defecto


def preferencias(ajustes):
    i = _entero(ajustes, "idioma_pref", 0)
    c = _entero(ajustes, "calidad_max", 0)
    prioridad = tuple(dict.fromkeys(
        codigo for codigo in ajustes("prioridad_idiomas").split(",")
        if codigo in IDIOMAS_PRIORIDAD
    ))
    idioma = prioridad[0] if prioridad else (IDIOMAS_AJUSTE[i] if 0 <= i < len(IDIOMAS_AJUSTE) else "")
    return {
        "idioma": idioma,
        "prioridad_idiomas": prioridad,
        "calidad_primero": _entero(ajustes, "orden_fuentes", 0) == 1,
        "calidad_max": CALIDADES_AJUSTE[c] if 0 <= c < len(CALIDADES_AJUSTE) else "4K",
        "solo_idioma": ajustes("solo_idioma") == "true",
    }


def consulta(t, ajustes, listas_url, cache, log):
    archivo_activo = ajustes("prov_archive_org") != "false"
    listas_url = listas_url if ajustes("prov_listas") != "false" else []
    manifiestos = []
    if ajustes("prov_stremio") == "true":
        for n in range(1, 4):
            origen = ajustes("stremio_%d" % n).strip()
            if origen:
                manifiestos.append((n, origen))
    extra = [ListaURL(listas_url, cache, max(1, _entero(ajustes, "cache_min", 60)) * 60, log)] if any(listas_url) else []
    extra += [Stremio(origen, n, log) for n, origen in manifiestos]

    def buscar(peli):
        if manifiestos and not peli.imdb_id and t and peli.tmdb_id:
            try:
                peli.imdb_id = t.imdb_id(peli.tmdb_id, "tv" if peli.tipo == "episodio" else "movie")
            except Exception:
                log("No se pudo obtener el identificador IMDb")
        return buscar_fuentes(peli, activo=lambda _: archivo_activo, log=log, extra=extra)

    return buscar, (archivo_activo, listas_url, manifiestos)


def hay_fuentes(m, buscar, preferencias):
    anio = str(m.get("release_date") or "")[:4]
    peli = Peli(titulo=m.get("title") or "", titulo_original=m.get("original_title") or "",
                anio=int(anio) if anio.isdigit() else 0, tmdb_id=m.get("tmdb_id", m["id"]), imdb_id=m.get("imdb_id") or "",
                tipo="episodio" if "episodio" in m else "pelicula",
                temporada=m.get("temporada", 0), episodio=m.get("episodio", 0))
    return bool(etiquetas.ordenar(buscar(peli), **preferencias))
