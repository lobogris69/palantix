"""Listas propias del usuario: un enlace (http/https) o un fichero local con películas y sus URLs.

Formatos admitidos
------------------
Capítulos de series: "serie" (o "titulo") + "temporada" + "episodio", o bien «Serie S01E02» en el título.
"tmdb_id" en un capítulo es el de la SERIE. "idioma" opcional: CAST, LAT, VOSE, VO, DUAL.

JSON (recomendado, admite todos los campos):
    {"nombre": "Mi lista",
     "peliculas": [
        {"titulo": "Nosferatu", "anio": 1922, "tmdb_id": 653, "url": "https://.../video.mp4",
         "calidad": "720p", "grupo": "Terror", "poster": "https://...", "fanart": "https://...",
         "sinopsis": "..."}
     ]}
    (también vale directamente la lista [...] sin el envoltorio)

M3U:
    #EXTM3U
    #EXTINF:-1 tvg-logo="https://.../poster.jpg" group-title="Terror" tmdb-id="653",Nosferatu (1922)
    https://.../video.mp4

Solo se usa la librería estándar, así que se puede probar fuera de Kodi.
"""
import hashlib
import json
import os
import re
import time
import urllib.request

from .http import AGENTE

_ATRIB = re.compile(r'([\w-]+)="([^"]*)"')
_ANIO = re.compile(r"\s*\((\d{4})\)\s*$")


def descargar(origen, cache_dir=None, ttl=3600):
    """Devuelve el texto de la lista. Las remotas se guardan en caché `ttl` segundos."""
    origen = origen.strip()
    if not origen.lower().startswith(("http://", "https://")):
        with open(origen, encoding="utf-8-sig") as f:
            return f.read()

    cache = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache = os.path.join(cache_dir, "lista_%s.txt" % hashlib.md5(origen.encode()).hexdigest())
        if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < ttl:
            with open(cache, encoding="utf-8") as f:
                return f.read()
    try:
        req = urllib.request.Request(origen, headers={"User-Agent": AGENTE})
        with urllib.request.urlopen(req, timeout=20) as r:
            texto = r.read().decode("utf-8-sig", "replace")
    except Exception:
        if cache and os.path.exists(cache):  # sin red: tiramos de la última copia
            with open(cache, encoding="utf-8") as f:
                return f.read()
        raise
    if cache:
        with open(cache, "w", encoding="utf-8") as f:
            f.write(texto)
    return texto


_SXE = re.compile(r"[ ._-]+(?:S(\d{1,2})E(\d{1,3})|(\d{1,2})x(\d{2,3}))\b.*$", re.I)


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _entero(v):
    try:
        return int(str(v)[:4]) if v not in (None, "") else 0
    except ValueError:
        return 0


def _normaliza_item(d, canales=False):
    titulo = (d.get("serie") or d.get("titulo") or d.get("title") or "").strip()
    temporada = _num(d.get("temporada") or d.get("season"))
    episodio = _num(d.get("episodio") or d.get("episode"))
    m = _SXE.search(titulo)
    if m and not canales:  # «Serie S01E02» o «Serie 1x02» en el título
        titulo = titulo[:m.start()].strip(" -.")
        temporada, episodio = temporada or int(m.group(1) or m.group(3)), episodio or int(m.group(2) or m.group(4))
    anio = _entero(d.get("anio") or d.get("year"))
    m = _ANIO.search(titulo)
    if m and not canales:
        titulo, anio = titulo[:m.start()].strip(), anio or int(m.group(1))
    return {
        "tipo": "episodio" if temporada and episodio else "pelicula",
        "temporada": temporada,
        "episodio": episodio,
        "idioma": (d.get("idioma") or d.get("language") or "").strip().upper(),
        "titulo": titulo,
        "titulo_original": (d.get("titulo_original") or d.get("original_title") or "").strip(),
        "anio": anio,
        "tmdb_id": _num(d.get("tmdb_id") or d.get("tmdb-id")) if str(d.get("tmdb_id") or d.get("tmdb-id") or "").isdigit() else 0,
        "imdb_id": (d.get("imdb_id") or d.get("imdb-id") or "").strip(),
        "url": (d.get("url") or "").strip(),
        "calidad": (d.get("calidad") or d.get("quality") or "").strip(),
        "grupo": (d.get("grupo") or d.get("group-title") or d.get("genero") or "Sin grupo").strip(),
        "poster": (d.get("poster") or d.get("tvg-logo") or "").strip(),
        "fanart": (d.get("fanart") or "").strip(),
        "sinopsis": (d.get("sinopsis") or d.get("overview") or "").strip(),
        "autor": (d.get("autor") or "").strip(),
        "licencia": (d.get("licencia") or "").strip(),
        "licencia_url": (d.get("licencia_url") or "").strip(),
        "canal": str(d.get("canal") or d.get("channel") or "").strip(),
        "fin": d.get("fin") or d.get("stop") or "",
        "resultado_en_titulo": str(d.get("resultado-en-titulo") or d.get("resultado_en_titulo")).lower() in ("true", "1"),
        "inicio": d.get("inicio") or d.get("start") or "",
        "ficha_origen": (d.get("ficha_origen") or "").strip(),
        **({"tvg_id": str(d.get("tvg-id") or d.get("tvg_id") or "").strip(),
            "tvg_nombre": str(d.get("tvg-name") or d.get("tvg_nombre") or "").strip(),
            "pais": str(d.get("tvg-country") or d.get("pais") or d.get("country") or "").strip()}
           if canales else {}),
    }


def _parsear_m3u(texto):
    items, pendiente = [], None
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.startswith("#EXTINF"):
            partes = re.match(r'((?:[^",]|"[^"]*")*),(.*)$', linea)
            pendiente = dict(_ATRIB.findall(partes[1]), titulo=partes[2]) if partes else None
        elif linea and not linea.startswith("#") and pendiente is not None:
            pendiente["url"] = linea
            items.append(pendiente)
            pendiente = None
    return items


def parsear(texto, eventos=False, canales=False):
    t = texto.lstrip("﻿").strip()
    if t.startswith(("{", "[")):
        datos = json.loads(t)
        if isinstance(datos, dict):
            crudos = ((datos.get("canales") if canales else None) or datos.get("peliculas") or datos.get("movies")
                      or (datos.get("eventos") if eventos else None) or [])
        else:
            crudos = datos
    elif t.startswith("#EXTM3U") or "#EXTINF" in t[:2000]:
        crudos = _parsear_m3u(t)
    else:
        raise ValueError("Formato de lista no reconocido (usa JSON o M3U)")
    return [i for i in (_normaliza_item(d, canales=canales) for d in crudos) if i["titulo"] and (i["url"] or (eventos and i["inicio"]))]


def cargar(origen, cache_dir=None, ttl=3600, eventos=False, canales=False):
    return parsear(descargar(origen, cache_dir, ttl), eventos=eventos, canales=canales)
