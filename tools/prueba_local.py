"""Prueba el addon fuera de Kodi con módulos xbmc* simulados.

Uso: python tools/prueba_local.py
"""
import json
import os
import runpy
import sys
import tempfile
from unittest.mock import patch
import types

RAIZ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugin.video.palantix")
sys.path.insert(0, RAIZ)
TMP = tempfile.mkdtemp(prefix="palantix_")

# ---------------------------------------------------------------- listas de ejemplo
LISTA_JSON = os.path.join(TMP, "lista.json")
LISTA_M3U = os.path.join(TMP, "lista.m3u")
json.dump({"nombre": "Prueba", "peliculas": [
    {"titulo": "Nosferatu", "anio": 1922, "tmdb_id": 653, "url": "https://ejemplo.invalid/nosferatu.mp4",
     "calidad": "720p", "grupo": "Terror"},
    {"titulo": "El chico", "anio": 1921, "url": "https://ejemplo.invalid/kid.mp4", "grupo": "Comedia"},
]}, open(LISTA_JSON, "w", encoding="utf-8"))
open(LISTA_M3U, "w", encoding="utf-8").write(
    '#EXTM3U\n#EXTINF:-1 tvg-logo="https://ejemplo.invalid/p.jpg" group-title="Clásicos",The General (1926)\n'
    'https://ejemplo.invalid/general.mp4\n')

LISTA_SERIES = os.path.join(TMP, "series.json")
_ep = dict(serie="Ficción", tmdb_id=100, temporada=1, episodio=2, grupo="Series")
json.dump([
    dict(_ep, url="https://ejemplo.invalid/ficcion.s01e02.LATINO.1080p.mkv"),
    dict(_ep, url="https://ejemplo.invalid/ficcion.s01e02.720p.mkv", idioma="CAST"),
    dict(_ep, url="https://ejemplo.invalid/ficcion.s01e02.CASTELLANO.2160p.mkv"),
    dict(_ep, url="https://ejemplo.invalid/ficcion.s01e02.HDCAM.Castellano.1080p.mkv"),
    dict(_ep, url="magnet:?xt=urn:btih:abc&dn=Ficcion.S01E02.CASTELLANO.2160p.HDR"),
    dict(_ep, episodio=3, url="https://ejemplo.invalid/ficcion.s01e03.mkv"),
    dict(_ep, episodio=1, url="https://ejemplo.invalid/ficcion.s01e01.CASTELLANO.1080p.mkv"),
], open(LISTA_SERIES, "w", encoding="utf-8"))

# ---------------------------------------------------------------- Kodi simulado
AJUSTES = {"tmdb_key": "clave-prueba", "lista_1": LISTA_JSON, "lista_2": LISTA_M3U, "lista_3": LISTA_SERIES,
           "cache_min": "60", "prov_archive_org": "false", "prov_listas": "true",
           "idioma_pref": "0", "calidad_max": "0", "solo_idioma": "false", "autoplay": "false", "inicio_plataforma": "false", "preguntado_idioma": "true"}
TMDB_FALSO = {
    "/movie/653": {"poster_path": "/nosferatu.jpg", "backdrop_path": "/nosferatu-fondo.jpg"},
    "/discover/movie": {"page": 1, "total_pages": 3, "results": [{"id": 1, "title": "Peli A", "release_date": "2001-01-01"}]},
    "/search/tv": {"page": 1, "total_pages": 1, "results": [
        {"id": 100, "name": "Ficción", "original_name": "Fiction", "first_air_date": "2020-01-01"}]},
    "/search/collection": {"results": [{"id": 10, "name": "Saga X"}]},
    "/collection/10": {"name": "Saga X", "parts": [{"id": 2, "title": "Parte 2", "release_date": "2005-01-01"},
                                                  {"id": 1, "title": "Parte 1", "release_date": "2001-01-01"}]},
    "/trending/tv/week": {"page": 1, "total_pages": 1, "results": [
        {"id": 100, "name": "Ficción", "original_name": "Fiction", "first_air_date": "2020-01-01"}]},
    "/tv/100": {"last_episode_to_air": {"season_number": 1, "episode_number": 2, "air_date": "2020-01-08"},
                "next_episode_to_air": {"season_number": 1, "episode_number": 3, "air_date": "2099-01-01"},
                "in_production": True, "poster_path": "/serie.jpg", "backdrop_path": "/fondo.jpg",
                "seasons": [{"season_number": 0, "name": "Especiales", "episode_count": 1},
                            {"season_number": 1, "name": "Temporada 1", "episode_count": 3}]},
    "/tv/100/season/1": {"episodes": [
        {"season_number": 1, "episode_number": 1, "name": "Piloto", "air_date": "2020-01-01", "runtime": 50},
        {"season_number": 1, "episode_number": 2, "name": "Dos", "air_date": "2020-01-08"},
        {"season_number": 1, "episode_number": 3, "name": "Tres", "air_date": "2099-01-01"}]},
}
REGISTRO = {"items": [], "resuelto": None, "avisos": [], "select": 0, "builtin": []}
PROPIEDADES = {}


class _Ventana:
    def __init__(self, *a): pass
    def setProperty(self, k, v): PROPIEDADES[k] = v
    def getProperty(self, k): return PROPIEDADES.get(k, "")
    def clearProperty(self, k): PROPIEDADES.pop(k, None)


class _Player:
    def __init__(self, *a): pass


LIS = []


class ListItem:
    def __init__(self, label="", label2="", path=""):
        self.label, self.path, self.props, self.menu = label, path, {}, []
        self.label2 = label2
        self.tag = _Tag()
        LIS.append(self)

    def setLabel(self, l): self.label = l
    def getLabel(self): return self.label

    def setArt(self, d): self.arte = d
    def setProperty(self, k, v): self.props[k] = v
    def addContextMenuItems(self, m): self.menu = m
    def getVideoInfoTag(self):
        return self.tag


class _Tag:
    def __init__(self):
        self.__dict__["datos"] = {}

    def __getattr__(self, nombre):  # acepta cualquier setXxx de InfoTagVideo y lo apunta
        return lambda *a: self.datos.__setitem__(nombre, a)


def _mod(nombre, **attrs):
    m = types.ModuleType(nombre)
    m.__dict__.update(attrs)
    sys.modules[nombre] = m


def _seleccionar(titulo, opciones, **ajustes):
    REGISTRO["selector"] = (titulo, opciones, ajustes)
    return REGISTRO["select"]


_mod("xbmc", LOGINFO=1, log=lambda m, l=0: print("   LOG", m),
     executebuiltin=lambda c: REGISTRO["builtin"].append(c), sleep=lambda ms: None, Player=_Player, getInfoLabel=lambda k: "", getSkinDir=lambda: "skin.estuary", getLanguage=lambda *a: "es", ISO_639_1=0, executeJSONRPC=lambda q: "{\"result\":true}",
     Monitor=lambda: types.SimpleNamespace(abortRequested=lambda: True, waitForAbort=lambda s: True), getCondVisibility=lambda c: False)
_mod("xbmcvfs", translatePath=lambda p: TMP)
_mod("xbmcaddon", Addon=lambda: types.SimpleNamespace(
    getSetting=lambda k: AJUSTES.get(k, ""), setSetting=lambda k, v: AJUSTES.__setitem__(k, v), getAddonInfo=lambda k: TMP, openSettings=lambda: None))
_mod("xbmcgui", ListItem=ListItem, NOTIFICATION_INFO=0, NOTIFICATION_WARNING=1, Window=_Ventana,
     DialogProgress=lambda: types.SimpleNamespace(create=lambda *a: None, close=lambda: None,
                                                 update=lambda *a: None, iscanceled=lambda: False),
     Dialog=lambda: types.SimpleNamespace(
         notification=lambda t, m, *a: REGISTRO["avisos"].append(m),
         ok=lambda t, m: REGISTRO.setdefault("dialogos", []).append((t, m)),
         input=lambda *a: REGISTRO.get("input", ""), contextmenu=lambda ops: (print("   MENÚ:", ops), REGISTRO.get("menu", 0))[1], select=_seleccionar))
_mod("xbmcplugin", SORT_METHOD_LABEL=1, SORT_METHOD_VIDEO_YEAR=2, SORT_METHOD_UNSORTED=0,
     addDirectoryItem=lambda h, u, li, isFolder=False: REGISTRO["items"].append((li.label, u)),
     addDirectoryItems=lambda h, its, n=0: REGISTRO["items"].extend((li.label, u) for u, li, _ in its),
     endOfDirectory=lambda h, succeeded=True, cacheToDisc=True: REGISTRO.__setitem__("fin", succeeded), setContent=lambda h, c: None,
     addSortMethod=lambda h, m: None,
     setResolvedUrl=lambda h, ok, li: (REGISTRO.__setitem__("resuelto", (ok, li.path)), REGISTRO.__setitem__("li", li)))


def abrir(consulta="", pedir_trakt=None, mostrar_guia=None):
    REGISTRO.update(items=[], resuelto=None, avisos=[], selector=None)
    del LIS[:]
    sys.argv = ["plugin://plugin.video.palantix/", "1", consulta]
    for m in [m for m in sys.modules if m.startswith("resources")]:
        del sys.modules[m]
    import resources.lib.tmdb as tm  # TMDB simulado (sin red ni clave real)
    tm.TMDB._get = lambda self, ruta, **p: TMDB_FALSO[ruta]
    if pedir_trakt:
        from resources.lib.trakt import Trakt
        Trakt._pedir = lambda self, metodo, ruta, cuerpo=None: pedir_trakt(metodo, ruta)
    if mostrar_guia:
        from resources.lib import cuadricula_tv
        cuadricula_tv.mostrar = mostrar_guia
    runpy.run_path(os.path.join(RAIZ, "main.py"), run_name="__main__")
    return REGISTRO


fallos = 0


def comprobar(nombre, cond):
    global fallos
    print(("OK    " if cond else "FALLO ") + nombre)
    fallos += 0 if cond else 1


from urllib.parse import urlencode  # noqa: E402

r = abrir("")
comprobar("menú principal incluye Cine libre y documentales",
          any(i[0] == "Cine libre y documentales" for i in r["items"]))
comprobar("menú principal ofrece TV y TV internacional",
          any(titulo == "TV" and u.endswith("?accion=tv") for titulo, u in r["items"])
          and any(i[0] == "TV internacional" for i in r["items"]))
r = abrir("?accion=deportes")
comprobar("Deportes ofrece agenda, canales y fuentes",
          [i[0] for i in r["items"]] == ["Hoy", "Eventos en directo", "Próximos eventos", "Detener reproducción", "Canales en directo", "Guía TV", "Cuadrícula de Palantix", "Mis fuentes"])
r = abrir("?accion=deportes_canales")
comprobar("Deportes incorpora Teledeporte", any(i[0] == "Teledeporte" for i in r["items"]))
cid = "a" * 40
consulta_ace = "?" + urlencode({"accion": "deportes_play", "u": "acestream://" + cid})
r = abrir(consulta_ace)
comprobar("Ace Stream sin Horus termina con un fallo controlado", r["resuelto"] == (False, ""))
visibilidad_original = sys.modules["xbmc"].getCondVisibility
addon_original = sys.modules["xbmcaddon"].Addon
try:
    kodi = sys.modules["xbmc"]
    condiciones_pvr = {"System.AddonIsEnabled(pvr.iptvsimple)"}
    kodi.getCondVisibility = lambda c: any(opcion in condiciones_pvr for opcion in c.split(" | "))
    r = abrir("?accion=deportes")
    comprobar("Deportes ofrece el acceso nativo con IPTV Simple habilitado",
              any(i[0] == "Cuadrícula de canales de Kodi" for i in r["items"]))
    r["builtin"].clear()
    r = abrir("?accion=deportes_cuadricula")
    comprobar("sin canales PVR se cierra la espera, se explica el requisito y se indica la guía propia",
              r["fin"] is False and "no tiene canales" in r["dialogos"][-1][1]
              and "Cuadrícula de Palantix" in r["dialogos"][-1][1] and not r["builtin"])
    condiciones_pvr = {"PVR.HasTVChannels"}
    r = abrir("?accion=deportes")
    comprobar("Deportes admite canales PVR de cualquier cliente",
              any(i[0] == "Cuadrícula de canales de Kodi" for i in r["items"]))
    r = abrir("?accion=deportes_cuadricula")
    comprobar("con canales PVR se abre la guía nativa",
              r["fin"] is False and r["builtin"][-1] == "ActivateWindow(TVGuide)")
finally:
    sys.modules["xbmc"].getCondVisibility = visibilidad_original

nombre_ace = "Horus"
ajustes_ace = []


def addon_simulado(addon_id=None):
    if addon_id == "script.module.horus":
        return types.SimpleNamespace(getAddonInfo=lambda clave: nombre_ace,
                                     openSettings=lambda: ajustes_ace.append(nombre_ace))
    return addon_original()


try:
    sys.modules["xbmc"].getCondVisibility = lambda c: c == "System.AddonIsEnabled(script.module.horus)"
    sys.modules["xbmcaddon"].Addon = addon_simulado
    r = abrir(consulta_ace)
    comprobar("Ace Stream delega en Horus",
              r["resuelto"] == (True, "plugin://script.module.horus?action=play&id=acestream%3A%2F%2F" + cid))
    r = abrir("?accion=deportes")
    comprobar("Horus original sin catálogo EKHorus", not any(i[0] == "Canales de EKHorus" for i in r["items"]))
    nombre_ace = "EKHorus"
    r = abrir("?accion=deportes")
    from ast import literal_eval
    from base64 import b64decode, b64encode
    from urllib.parse import unquote, urlsplit
    ruta = next((u for titulo, u in r["items"] if titulo == "Canales de EKHorus"), "")
    partes = urlsplit(ruta)
    comprobar("EKHorus abre su catálogo clásico", partes.netloc == "script.module.horus" and
              literal_eval(b64decode(unquote(partes.query)).decode()) == {"action": "catalogo", "clasico": 1})
    r = abrir("?accion=deportes_fuentes")
    comprobar("Mis fuentes identifica la variante instalada", any(i[0] == "Configurar EKHorus" for i in r["items"]))
    abrir("?accion=deportes_horus")
    comprobar("Palantix abre los ajustes de EKHorus", ajustes_ace == ["EKHorus"])
    r = abrir(consulta_ace)
    comprobar("EKHorus recibe el enlace Ace Stream", r["resuelto"][0] and r["resuelto"][1].endswith(cid))
    from pathlib import Path
    from time import time
    from urllib.parse import quote
    epg_cache = Path(TMP, "cache")
    epg_cache.mkdir(exist_ok=True)
    hora = time()
    Path(epg_cache, "epg-doblem.json").write_text(json.dumps({
        "nombres": {"Teledeporte": ["Teledeporte HD"], "La 1 HD": ["La 1"]},
        "programas": {"Teledeporte": [[hora - 60, hora + 60, "Partido"]]},
    }), encoding="utf-8")
    exportacion = Path(TMP, "ekhorus.m3u")
    enlace = "plugin://script.module.horus/?" + quote(b64encode(
        repr({"action": "play", "infohash": cid, "motor": 1}).encode()))
    exportacion.write_text("#EXTM3U\n#EXTINF:-1,Teledeporte HD\n" + enlace +
                           '\n#EXTINF:-1 group-title="España",Canal local\nhttps://ejemplo.invalid/local.m3u8\n'
                           '#EXTINF:-1 group-title="Chile, Noticias" tvg-country="CL",La 1 HD\n'
                           "https://ejemplo.invalid/chile.m3u8\n"
                           '#EXTINF:-1 group-title="España",ES | TVE 1 UHD\nhttps://ejemplo.invalid/tve.m3u8\n',
                           encoding="utf-8")
    vfs = sys.modules["xbmcvfs"]
    traducir = vfs.translatePath
    try:
        vfs.translatePath = lambda ruta: str(exportacion) if ruta.endswith("/ekhorus.m3u") else TMP
        r = abrir("?accion=deportes_epg")
        teledeporte = [(titulo, u) for titulo, u in r["items"] if titulo.startswith("Teledeporte")]
        comprobar("Guía: EKHorus tiene prioridad para Teledeporte", len(teledeporte) == 1 and
                  "Partido" in teledeporte[0][0] and
                  literal_eval(b64decode(unquote(urlsplit(teledeporte[0][1]).query)).decode()) ==
                  {"action": "play", "infohash": cid, "origen": "tv", "motor": 1})
        comprobar("Guía: Madrid avisa que falta señal directa",
                  any(t.startswith("Real Madrid TV") and "Sin señal directa" in t and not u for t, u in r["items"]))
        comprobar("Guía: conserva el directo si no está exportado",
                  any(t.startswith("Esport3") and "deportes_play" in u for t, u in r["items"]))
        r = abrir("?accion=tv_internacional")
        comprobar("TV internacional agrupa y no mezcla los canales de España",
                  [titulo for titulo, _ in r["items"]] == ["Chile, Noticias (1)"])
        r = abrir("?" + urlencode({"accion": "tv_internacional", "grupo": "Chile, Noticias"}))
        comprobar("TV internacional deja elegir el canal del grupo",
                  len(r["items"]) == 1 and "chile.m3u8" in r["items"][0][1])

        def mostrar_guia(addon, canales, programas, hora, ocultar, seleccionar):
            comprobar("TV entra directamente a la guía española y normaliza el nombre de La 1",
                      canales.get("La 1 HD", (None, None))[1] == "https://ejemplo.invalid/tve.m3u8"
                      and all("chile.m3u8" not in u for _, u in canales.values()))
            canal, directo = next(v for v in canales.values() if v[0] == "Canal local")
            return not seleccionar(canal, directo, hora, hora + 100, "")

        abrir("?accion=tv", mostrar_guia=mostrar_guia)
        comprobar("TV permite reproducir una fila sin programación",
                  REGISTRO["builtin"][-1].startswith("PlayMedia(") and "local.m3u8" in REGISTRO["builtin"][-1])
    finally:
        vfs.translatePath = traducir

finally:
    sys.modules["xbmcaddon"].Addon = addon_original
    sys.modules["xbmc"].getCondVisibility = visibilidad_original
r = abrir("?accion=cine_libre")
comprobar("cine libre: muestra categorías", any(i[0] == "Documentales" for i in r["items"]))
r = abrir("?accion=cine_libre&g=Documentales")
comprobar("cine libre: muestra el documental con reproducción directa",
          any("The Eagle Has Landed" in i[0] and "accion=reproducir_directo" in i[1] for i in r["items"]))

r = abrir("?accion=listas")
etiquetas_ = [i[0] for i in r["items"]]
comprobar("Mis listas: «Añadir», las 3 listas (pasadas desde Ajustes) con su nº de títulos y la ayuda",
          len(etiquetas_) == 5 and "Añadir una lista" in etiquetas_[0] and "2 títulos" in etiquetas_[1]
          and "1 título" in etiquetas_[2] and "Qué dirección" in etiquetas_[-1])
comprobar("Mis listas: las casillas antiguas de Ajustes quedan vacías tras pasarlas", AJUSTES.get("lista_1") == "")

r = abrir("?accion=listas&n=1")
comprobar("lista JSON agrupada (Todas + Comedia + Terror)", [i[0] for i in r["items"]] == ["[Todas] (2)", "Comedia (1)", "Terror (1)"])

r = abrir("?accion=listas&n=1&g=Terror")
comprobar("grupo Terror con Nosferatu y su etiqueta en color", r["items"] and r["items"][0][0] == "Nosferatu (1922)  [COLOR gold][720p][/COLOR]")
AJUSTES["mostrar_etiquetas"] = "false"
r = abrir("?accion=listas&n=1&g=Terror")
comprobar("etiquetas en títulos se pueden ocultar", r["items"][0][0] == "Nosferatu (1922)")
AJUSTES["mostrar_etiquetas"] = "true"

r = abrir("?accion=listas&n=2")
comprobar("lista M3U: título y año separados", r["items"] and r["items"][0][0] == "The General (1926)")

r = abrir("?" + urlencode({"accion": "reproducir_directo", "u": "https://ejemplo.invalid/kid.mp4"}))
comprobar("reproducción directa desde lista", r["resuelto"] == (True, "https://ejemplo.invalid/kid.mp4"))

REGISTRO["select"] = -1
r = abrir("?" + urlencode({"accion": "reproducir", "id": 653, "titulo": "Nosferatu", "anio": "1922"}))
comprobar("sin reproducción automática, una sola fuente requiere confirmación",
          r["resuelto"] == (False, ""))
REGISTRO["select"] = 0
r = abrir("?" + urlencode({"accion": "reproducir", "id": 653, "titulo": "Nosferatu", "anio": "1922"}))
comprobar("ficha TMDB encuentra su fuente en la lista por tmdb_id", r["resuelto"] == (True, "https://ejemplo.invalid/nosferatu.mp4"))
_, opciones, ajustes = r["selector"]
comprobar("el selector abre la vista detallada y muestra el idioma desconocido en primera línea",
          ajustes == {"useDetails": True} and
          opciones[0].label == "Idioma sin indicar · 720p · MP4" and
          "Nosferatu" in opciones[0].label2)

r = abrir("?" + urlencode({"accion": "reproducir", "id": 961, "titulo": "El maquinista de la General",
                          "original": "The General", "anio": "1926"}))
comprobar("ficha TMDB encuentra fuente en la M3U por título original", r["resuelto"] == (True, "https://ejemplo.invalid/general.mp4"))

r = abrir("?" + urlencode({"accion": "reproducir", "id": 1, "titulo": "No existe", "anio": "2001"}))
comprobar("sin fuentes: avisa y no reproduce", r["resuelto"] == (False, "") and r["avisos"])

r = abrir("?" + urlencode({"accion": "fav_poner", "id": 653, "datos": json.dumps(
    {"id": 653, "title": "Nosferatu", "release_date": "1922-03-04", "poster_path": "/x.jpg"})}))
r = abrir("?accion=favoritas")
comprobar("favorita guardada y listada", r["items"] and r["items"][0][0] == "Nosferatu (1922)")
r = abrir("?" + urlencode({"accion": "fav_quitar", "id": 653, "datos": "{}"}))
r = abrir("?accion=favoritas")
comprobar("favorita quitada", r["items"] == [])

# ---------------------------------------------------------------- series
r = abrir("?accion=m_series")
comprobar("menú Series integra seguimiento y Capítulos recientes",
          len(r["items"]) == 8 and r["items"][0][0] == "Series en seguimiento" and r["items"][1][0] == "Capítulos recientes")
r = abrir("?accion=m_peliculas")
comprobar("menú Películas con Novedades en streaming",
          len(r["items"]) == 8 and any(i[0] == "Novedades en streaming" for i in r["items"]))
r = abrir("?accion=anios&destino=anio")
comprobar("por año: empieza por el año actual", r["items"][0][0] == __import__("time").strftime("%Y"))
r = abrir("?accion=anio&a=2001")
comprobar("listado de un año con página siguiente", r["items"][0][0] == "Peli A (2001)" and "Página siguiente (2)" in r["items"][-1][0])
AJUSTES["paginas"] = "2"  # 60 por pantalla = 3 páginas de TMDB
r = abrir("?accion=anio&a=2001")
comprobar("60 por pantalla junta 3 páginas y no ofrece más (TMDB tiene 3)", len(r["items"]) == 3)
AJUSTES["paginas"] = "0"
r = abrir("?accion=sagas")
comprobar("menú de sagas con buscador y sagas conocidas", r["items"][0][0].startswith("[B]Buscar") and len(r["items"]) > 10)
r = abrir("?accion=sagas_buscar&q=Saga")
comprobar("buscar saga", r["items"] == [("Saga X", r["items"][0][1])] and "accion=saga" in r["items"][0][1])
r = abrir("?accion=saga&id=10")
comprobar("saga en orden de estreno", [i[0] for i in r["items"]] == ["Parte 1 (2001)", "Parte 2 (2005)"])
r = abrir("?accion=s_buscar&q=Ficci%C3%B3n")
r = abrir("?accion=s_buscar")
comprobar("búsquedas recientes recordadas", [i[0] for i in r["items"]][:2] == ["[B]Nueva búsqueda...[/B]", "Ficción"])
r = abrir("?accion=s_tendencias")
comprobar("tendencias de series", r["items"] and r["items"][0][0] == "Ficción (2020)")
r = abrir("?" + urlencode({"accion": "temporadas", "id": 100, "titulo": "Ficción", "original": "Fiction", "anio": "2020"}))
comprobar("temporadas con Especiales al final", [i[0] for i in r["items"]] == ["Temporada 1 (3 capítulos)", "Especiales (1 capítulos)"])
r = abrir("?" + urlencode({"accion": "capitulos", "id": 100, "s": 1, "titulo": "Ficción", "original": "Fiction", "anio": "2020"}))
comprobar("capítulos numerados y el futuro en gris", r["items"][1][0] == "1x02. Dos" and "sale el 01-01-2099" in r["items"][2][0])

EP = "?" + urlencode({"accion": "reproducir", "tipo": "episodio", "id": 100, "titulo": "Ficción", "anio": "2020", "s": 1, "e": 2})
REGISTRO["select"] = 1  # el usuario elige la 2ª del selector (la 1ª es el magnet)
r = abrir(EP)
comprobar("capítulo: selector ordenado y reproduce la elegida",
          r["resuelto"] == (True, "https://ejemplo.invalid/ficcion.s01e02.CASTELLANO.2160p.mkv"))
_, opciones, _ = r["selector"]
comprobar("la primera línea de las opciones distingue castellano y latino",
          opciones[1].label == "Castellano · 4K · MKV" and
          any(op.label == "Latino · 1080p · MKV" for op in opciones))
REGISTRO["select"] = 0
from resources.lib import etiquetas as et  # noqa: E402
from resources.lib.providers import ListaURL as LU, Peli as P  # noqa: E402
from resources.lib.providers.stremio import Stremio  # noqa: E402
fuente_stream = Stremio._fuente({
    "name": "4K",
    "description": "Película de ejemplo con un nombre largo que precede a los datos de audio [ES]\n19.33 GB",
    "url": "https://ejemplo.invalid/video.mkv",
}, "Proveedor de prueba")
comprobar("idioma y tamaño de Stremio se extraen aunque estén al final de la descripción",
          et.resumen_fuente(fuente_stream, et.analizar(fuente_stream.etiqueta)) == "Español · 4K · MKV · 19.33 GB")
fu = LU([LISTA_SERIES]).buscar(P("Ficción", tmdb_id=100, tipo="episodio", temporada=1, episodio=2))
orden = [f.url.rsplit("/", 1)[-1] for f, _ in et.ordenar(fu, idioma="CAST")]
print("   orden CAST:", orden)
comprobar("orden CAST: 4K HDR, 4K, 720p, latino, CAM", len(orden) == 5 and "HDR" in orden[0] and "2160p" in orden[1]
          and "720p" in orden[2] and "LATINO" in orden[3] and "HDCAM" in orden[4])
orden = [f.url for f, _ in et.ordenar(fu, idioma="LAT", calidad_max="1080p")]
comprobar("preferencia latino primero", "LATINO" in orden[0])
orden = [f.url for f, _ in et.ordenar(fu, idioma="CAST", calidad_max="720p")]
comprobar("tope 720p: la de 720p castellano primero", orden[0].endswith("720p.mkv"))
comprobar("ocultar otros idiomas quita la latina", not any("LATINO" in f.url for f, _ in et.ordenar(fu, idioma="CAST", solo_idioma=True)))
comprobar("el capítulo 3 no se mezcla con el 2", not any("e03" in f.url for f in fu))
from resources.lib import listas as ls  # noqa: E402
it = ls.parsear("#EXTM3U\n#EXTINF:-1,Ficción S01E03 Castellano\nhttps://x/y.mkv\n")[0]
comprobar("M3U entiende «Serie S01E03»", (it["titulo"], it["temporada"], it["episodio"], it["tipo"]) == ("Ficción", 1, 3, "episodio"))

AJUSTES["autoplay"] = "true"
r = abrir(EP)
comprobar("automático: el magnet falla (sin AllDebrid) y salta a la siguiente, castellano 4K",
          r["resuelto"] == (True, "https://ejemplo.invalid/ficcion.s01e02.CASTELLANO.2160p.mkv"))
AJUSTES["autoplay"] = "false"

# ---------------------------------------------------------------- siguiente capítulo
r = abrir(EP)
meta = json.loads(PROPIEDADES.get("palantix.meta", "{}"))
comprobar("al reproducir deja los datos para el servicio", meta.get("tipo") == "episodio" and meta.get("e") == 2)
comprobar("1x02: el 1x03 aún no se ha emitido -> no ofrece siguiente", "palantix.siguiente" not in PROPIEDADES)
r = abrir("?" + urlencode({"accion": "reproducir", "tipo": "episodio", "id": 100, "titulo": "Ficción", "anio": "2020", "s": 1, "e": 1}))
sig = json.loads(PROPIEDADES.get("palantix.siguiente", "{}"))
comprobar("1x01: deja preparado el 1x02", "e=2" in sig.get("url", "") and sig.get("etiqueta") == "Ficción 1x02. Dos")

import runpy as _rp  # noqa: E402
servicio = _rp.run_path(os.path.join(RAIZ, "service.py"), run_name="servicio")
marca_inicio = "palantix.arranque_comprobado"
kodi = sys.modules["xbmc"]
arranque = servicio["abrir_al_arrancar"]
monitor_prueba = types.SimpleNamespace(waitForAbort=lambda segundos: False)
reproductor_prueba = types.SimpleNamespace(isPlaying=lambda: False)
try:
    kodi.getCondVisibility = lambda condicion: condicion == "Window.IsActive(Home)"
    REGISTRO["builtin"] = []
    arranque(monitor_prueba, reproductor_prueba)
    AJUSTES["inicio_automatico"] = "true"
    arranque(monitor_prueba, reproductor_prueba)
    comprobar("arranque: desactivado por defecto y activar el ajuste se aplica al próximo arranque",
              not REGISTRO["builtin"])
    PROPIEDADES.pop(marca_inicio, None)
    comprobadas = []

    def cargando_inicio(condicion):
        if condicion == "Window.IsActive(Home)":
            comprobadas.append(condicion)
            return len(comprobadas) > 1
        return "Window.IsActive(Startup)" in condicion

    kodi.getCondVisibility = cargando_inicio
    arranque(monitor_prueba, reproductor_prueba)
    arranque(monitor_prueba, reproductor_prueba)
    comprobar("arranque: espera al menú de Kodi y abre Palantix una sola vez por sesión",
              REGISTRO["builtin"] == ["RunAddon(plugin.video.palantix)"] and len(comprobadas) == 2)
    PROPIEDADES.pop(marca_inicio, None)
    REGISTRO["builtin"] = []
    reproductor_prueba.isPlaying = lambda: True
    arranque(monitor_prueba, reproductor_prueba)
    comprobar("arranque: respeta una reproducción ya iniciada", not REGISTRO["builtin"])
    PROPIEDADES.pop(marca_inicio, None)
    reproductor_prueba.isPlaying = lambda: False
    kodi.getCondVisibility = lambda condicion: condicion in ("Window.IsActive(Home)", "System.HasActiveModalDialog")
    arranque(monitor_prueba, reproductor_prueba)
    comprobar("arranque: respeta un diálogo abierto en Kodi", not REGISTRO["builtin"])
finally:
    kodi.getCondVisibility = visibilidad_original
    AJUSTES.pop("inicio_automatico", None)
    PROPIEDADES.pop(marca_inicio, None)
rep = servicio["Reproductor"]()
rep.onAVStarted()
comprobar("servicio: recoge los datos y los borra de la ventana", rep.siguiente and "palantix.siguiente" not in PROPIEDADES)
rep.isPlayingVideo = lambda: True
rep.getTotalTime = lambda: 2700.0
rep.getTime = lambda: 2600.0  # faltan 100 s: aún no
REGISTRO["builtin"] = []
rep.vigilar()
comprobar("servicio: a 100 s del final todavía no ofrece nada", REGISTRO["builtin"] == [])
rep.getTime = lambda: 2680.0  # faltan 20 s
rep.vigilar()
comprobar("servicio: a 20 s del final lanza el siguiente capítulo", REGISTRO["builtin"] and "e=2" in REGISTRO["builtin"][0])
rep.vigilar()
comprobar("servicio: no lo ofrece dos veces", len(REGISTRO["builtin"]) == 1)

# Un error intermedio de Kodi se descarta si el vídeo acaba arrancando.
rep = servicio["Reproductor"]()
rep.isPlayingVideo = lambda: False
reloj = servicio["time"]
PROPIEDADES["palantix.meta"] = json.dumps({"inicio_solicitado": reloj.time()})
with patch.object(reloj, "monotonic", return_value=100):
    rep.onPlayBackError()
rep.isPlayingVideo = lambda: True
with patch.object(reloj, "monotonic", return_value=104):
    rep.comprobar_error()
comprobar("un aviso transitorio no aparece mientras el canal se reproduce",
          not PROPIEDADES.get("palantix.ultimo_error") and rep.error_pendiente is None)
rep.isPlayingVideo = lambda: False
with patch.object(reloj, "monotonic", return_value=105):
    rep.onPlayBackError()
with patch.object(reloj, "monotonic", return_value=109):
    rep.comprobar_error()
comprobar("el servicio mantiene el aviso cuando Kodi realmente se queda sin vídeo",
          bool(PROPIEDADES.get("palantix.ultimo_error")) and
          any("Kodi no pudo" in aviso for aviso in REGISTRO["avisos"]))
PROPIEDADES.pop("palantix.ultimo_error", None)

# ---------------------------------------------------------------- seguimiento de series
from resources.lib import seguimiento as sg  # noqa: E402
g = sg.Seguimiento(TMP)
m1 = {"tipo": "episodio", "tmdb": 100, "s": 1, "e": 1, "titulo": "Ficción", "original": "Fiction", "anio": 2020,
      "poster": "/p.jpg", "fanart": "/f.jpg"}
g.al_empezar(m1, None)
g.al_avanzar(m1, None, 600, 3000)
g.al_parar(m1, None, False)
comprobar("seguimiento: parar al 20 % no cuenta como visto", "100" not in sg.leer(TMP))
g.al_avanzar(m1, None, 2700, 3000)
g.al_parar(m1, None, False)
comprobar("seguimiento: al 90 % el capítulo cuenta como visto", sg.leer(TMP).get("100", {}).get("e") == 1)
r = abrir("?accion=seguir")
comprobar("Seguir viendo ofrece el 1x02 con «1 pendiente»", r["items"] and r["items"][0][0].startswith("Ficción · 1x02. Dos")
          and "1 pendiente" in r["items"][0][0] and "e=2" in r["items"][0][1])
comprobar("y la piel recibe el número de pendientes", LIS[0].props.get("UnWatchedEpisodes") == "1")
r = abrir("?" + urlencode({"accion": "capitulos", "id": 100, "s": 1, "titulo": "Ficción"}))
comprobar("capítulos: el 1x01 con marca de visto y el 1x02 sin ella",
          LIS[0].tag.datos.get("setPlaycount") == (1,) and "setPlaycount" not in LIS[1].tag.datos)
r = abrir("")
comprobar("menú: Series en seguimiento con contador de pendientes", any("1 con capítulos pendientes" in i[0] for i in r["items"]))
sg.marcar_visto(TMP, dict(m1, e=2))
sg.marcar_visto(TMP, dict(m1, e=1))
comprobar("seguimiento: volver a ver un capítulo antiguo no retrocede", sg.leer(TMP)["100"]["e"] == 2)
r = abrir("?accion=seguir")
comprobar("al día (1x03 sin emitir): se oculta y avisa", r["items"] == [] and r["avisos"])
AJUSTES["ocultar_al_dia"] = "false"
r = abrir("?accion=seguir")
comprobar("al día: si no se oculta, se muestra el estado", r["items"] and "Al día" in r["items"][0][0])
r = abrir("?accion=seguir&estado=todos")
comprobar("Series en seguimiento ofrece los tres estados",
          [i[0] for i in r["items"][:3]] == ["Nuevo (0)", "Al día (1)", "Terminada (0)"])
r = abrir("?accion=seguir&estado=al_dia")
comprobar("filtro Al día abre las temporadas", len(r["items"]) == 1 and "accion=temporadas" in r["items"][0][1])
from resources.lib import novedades as novedades_vista  # noqa: E402
datos_estado = novedades_vista.leer(TMP)
datos_estado["100"]["en_emision"] = False
datos_estado["100"]["proximo"] = None
novedades_vista._guardar(TMP, datos_estado)
r = abrir("?accion=seguir&estado=terminada")
comprobar("filtro Terminada muestra la serie completa", len(r["items"]) == 1 and "Terminada" in r["items"][0][0])
r = abrir("?accion=dejar_seguir&id=100")
comprobar("quitar de seguimiento", "100" not in sg.leer(TMP))

# ---------------------------------------------------------------- capítulo NUEVO
sg.marcar_visto(TMP, dict(m1, e=1), ahora=1546300800)  # visto el 1x01 en 2019: el 1x02 salió después
import resources.lib.tmdb as _tm  # noqa: E402
_tm.TMDB._get = lambda self, ruta, **p: TMDB_FALSO[ruta]
from resources.lib import novedades as nv  # noqa: E402
est = nv.estado(_tm.TMDB("x"), 100, 1, 1, 1546300800)
comprobar("novedades: 1 pendiente y marcado como NUEVO", est["pendientes"] == 1 and est["nuevo"] and est["siguiente"]["e"] == 2)
est = nv.estado(_tm.TMDB("x"), 100, 1, 1, __import__("time").time())
comprobar("novedades: si ya lo sabías (visto hoy), aparece en Nuevo sin repetir el aviso",
          est["pendientes"] == 1 and not est["nuevo"] and nv.estado_vista(est) == "nuevo")
r = abrir("?accion=seguir")
comprobar("Seguir viendo: distintivo ● NUEVO", r["items"] and "● NUEVO" in r["items"][0][0])
r = abrir("")
comprobar("menú: «● 1 con capítulos nuevos»", any("● 1 con capítulos nuevos" in i[0] for i in r["items"]))
r = abrir("?accion=s_tendencias")
comprobar("listado de series: la seguida lleva su marca y el contador", "● NUEVO" in r["items"][0][0]
          and LIS[0].props.get("UnWatchedEpisodes") == "1")
datos = nv.leer(TMP)
datos["100"]["ultimo"] = {"s": 1, "e": 1, "emitido": "2020-01-01"}  # como si antes el último fuese el 1x01
datos["100"]["comprobado"] = 0
nv._guardar(TMP, datos)
recien = nv.refrescar(TMP, _tm.TMDB("x"))
comprobar("aviso de capítulo nuevo al refrescar", recien == [("Ficción", {"s": 1, "e": 2, "emitido": "2020-01-08"})])
sg.quitar(TMP, 100)

# ---------------------------------------------------------------- películas a medias
from resources.lib import progreso as pg  # noqa: E402
pm = {"tipo": "pelicula", "tmdb": 653, "titulo": "Nosferatu", "anio": 1922, "poster": "/n.jpg"}
comprobar("progreso: 30 s no se apuntan", pg.apuntar(TMP, pm, 30, 5640) == "nada")
comprobar("progreso: a los 20 min se apunta", pg.apuntar(TMP, pm, 1200, 5640) == "guardado")
r = abrir("")
comprobar("menú: Continuar viendo películas (1)", any("Continuar viendo películas" in i[0] and "(1)" in i[0] for i in r["items"]))
r = abrir("?accion=a_medias")
comprobar("a medias: título con «20:00 de 1:34:00» y barra de progreso", "20:00 de 1:34:00" in r["items"][0][0]
          and LIS[0].tag.datos.get("setResumePoint") == (1200.0, 5640.0))
REGISTRO["menu"] = 0
r = abrir("?" + urlencode({"accion": "reproducir", "id": 653, "titulo": "Nosferatu", "anio": "1922"}))
comprobar("reanudar: empieza en el segundo 1200", r["resuelto"][0] and REGISTRO["li"].props.get("StartOffset") == "1200")
REGISTRO["menu"] = 1
r = abrir("?" + urlencode({"accion": "reproducir", "id": 653, "titulo": "Nosferatu", "anio": "1922"}))
comprobar("desde el principio: sin punto de inicio", r["resuelto"][0] and "StartOffset" not in REGISTRO["li"].props)
comprobar("progreso: al 95 % se da por vista y desaparece", pg.apuntar(TMP, pm, 5400, 5640) == "borrado" and not pg.peliculas(TMP))
REGISTRO["menu"] = 0

# ---------------------------------------------------------------- clave de TMDB (fallo visto en la tele)
AJUSTES["tmdb_key"] = ""
REGISTRO["input"] = "  CLAVE-NUEVA \n"
r = abrir("?accion=s_tendencias")
comprobar("sin clave: la pide en un cuadro, la limpia, la guarda y carga el catálogo al momento",
          AJUSTES["tmdb_key"] == "CLAVE-NUEVA" and r["items"] and r["items"][0][0].startswith("Ficción"))
REGISTRO["input"] = ""
AJUSTES["tmdb_key"] = ""
r = abrir("?accion=s_tendencias")
comprobar("sin clave y sin escribir nada: no se cuelga", r["items"] == [])
AJUSTES["tmdb_key"] = "clave-prueba"

# ---------------------------------------------------------------- añadir / quitar listas
NUEVA = os.path.join(TMP, "nueva.m3u")
open(NUEVA, "w", encoding="utf-8").write("#EXTM3U\n#EXTINF:-1,Peli Uno (2001)\nhttps://x/1.mp4\n#EXTINF:-1,Peli Dos (2002)\nhttps://x/2.mp4\n")
WEB = os.path.join(TMP, "web.html")
open(WEB, "w", encoding="utf-8").write("<html><body>Una web normal</body></html>")
from resources.lib import mislistas as ml  # noqa: E402
antes = len(ml.leer(TMP))
REGISTRO["input"] = WEB
abrir("?accion=lista_nueva")
comprobar("añadir lista: una página web se rechaza con explicación", len(ml.leer(TMP)) == antes)
REGISTRO["input"] = NUEVA
abrir("?accion=lista_nueva")
comprobar("añadir lista: un M3U válido se añade", len(ml.leer(TMP)) == antes + 1 and ml.leer(TMP)[-1]["origen"] == NUEVA)
abrir("?accion=lista_nueva")
comprobar("añadir lista: la misma dirección no se duplica", len(ml.leer(TMP)) == antes + 1)
REGISTRO["input"] = "Pelis de prueba"
abrir("?accion=lista_renombrar&i=%d" % antes)
comprobar("renombrar lista", ml.leer(TMP)[-1]["nombre"] == "Pelis de prueba")
REGISTRO["input"] = ""
ml.quitar(TMP, antes)
comprobar("quitar lista", len(ml.leer(TMP)) == antes)
from resources.lib import tmdb as _t  # noqa: E402
comprobar("idioma del catálogo: Latinoamérica = es-MX / MX", _t.idioma_de(1) == ("es-MX", "MX") and _t.idioma_de("x") == ("es-ES", "ES"))

# ---------------------------------------------------------------- aviso de caducidad
from resources.lib import debrid as dbr  # noqa: E402


class _S:
    def __init__(self, nombre, dias):
        self.nombre, self.d = nombre, dias

    def dias_restantes(self):
        if isinstance(self.d, Exception):
            raise self.d
        return self.d


av = dbr.avisos_caducidad([_S("Real-Debrid", 3), _S("AllDebrid", 40), _S("Premiumize", 0), _S("X", RuntimeError())])
comprobar("aviso de caducidad solo para las que caducan pronto", av == ["Real-Debrid caduca en 3 días", "Premiumize ha caducado"])

# Una temporada combina marcas de ambos historiales y conserva los huecos.
sg.quitar(TMP, 100)
sg.marcar_visto(TMP, dict(m1, e=2))
AJUSTES.update(trakt_token="sesion-prueba", trakt_activo="true")
llamadas_historial = []


def pedir_historial(metodo, ruta):
    llamadas_historial.append((metodo, ruta))
    return 200, [{"show": {"ids": {"tmdb": 100}}, "seasons": [
        {"number": 1, "episodes": [{"number": 1, "plays": 2}, {"number": 3, "plays": 0}]}
    ]}]


ruta_capitulos = "?accion=capitulos&id=100&s=1&titulo=Ficción"
abrir(ruta_capitulos, pedir_trakt=pedir_historial)
comprobar("temporada: muestra episodios vistos en Trakt y en local, sin marcar los pendientes",
          [li.tag.datos.get("setPlaycount") for li in LIS] == [(1,), (1,), None])
r = abrir("?accion=seguir&estado=al_dia", pedir_trakt=pedir_historial)
comprobar("seguimiento: usa los vistos de Trakt y reutiliza el historial recién consultado",
          len(r["items"]) == 1 and "Al día" in r["items"][0][0]
          and llamadas_historial == [("GET", "/sync/watched/shows")])
AJUSTES["trakt_token"] = "otra-sesion"


def trakt_no_disponible(metodo, ruta):
    raise OSError("conexión de prueba")


abrir(ruta_capitulos, pedir_trakt=trakt_no_disponible)
comprobar("si Trakt falla, el historial de otra cuenta no se mezcla con el local",
          [li.tag.datos.get("setPlaycount") for li in LIS] == [None, (1,), None])
AJUSTES.update(trakt_token="", trakt_activo="false")

# Historial: por título, sin Trakt obligatorio y sin marcar series a medias.
from resources.lib import historial as archivo_vistos  # noqa: E402

notas_pedidas = []
gancho_historial = archivo_vistos.Historial(
    perfil=TMP, ajustes=lambda k: AJUSTES.get(k, ""),
    valorar=lambda titulo: (notas_pedidas.append(titulo), 4)[1])
peli_vista = {"tipo": "pelicula", "tmdb": 653, "titulo": "Nosferatu", "anio": 1922}
gancho_historial.al_empezar(peli_vista, None)
gancho_historial.al_avanzar(peli_vista, None, 40, 100)
gancho_historial.al_parar(peli_vista, None, False)
comprobar("historial: una película a medias no se archiva", not archivo_vistos.leer(TMP, "pelicula"))
gancho_historial.al_avanzar(peli_vista, None, 90, 100)
gancho_historial.al_parar(peli_vista, None, False)
gancho_historial.al_valorar(peli_vista, None)
gancho_historial.al_parar(peli_vista, None, True)
gancho_historial.al_valorar(peli_vista, None)
comprobar("historial: terminar o repetir una película conserva una única valoración",
          [ficha["nota"] for ficha in archivo_vistos.leer(TMP, "pelicula")] == [4]
          and notas_pedidas == ["Nosferatu"])
r = abrir("?accion=historial_vistos&tipo=pelicula")
comprobar("historial: la carpeta muestra estrellas y permite volver a ver la película",
          r["items"] == [("Nosferatu (1922) · ★★★★ 4/5", r["items"][0][1])]
          and "accion=reproducir" in r["items"][0][1]
          and LIS[0].menu[0][0] == "Valorar o cambiar las estrellas")
REGISTRO["select"] = 3
abrir("?accion=valorar_visto&tipo=pelicula&id=653&titulo=Nosferatu")
REGISTRO["select"] = 0
comprobar("historial: editar estrellas en la carpeta cambia solo la valoración",
          [ficha["nota"] for ficha in archivo_vistos.leer(TMP, "pelicula")] == [2])

with tempfile.TemporaryDirectory() as perfil_serie:
    ficha_tmdb = {"status": "Ended", "in_production": False,
                  "last_episode_to_air": {"season_number": 1, "episode_number": 2},
                  "seasons": [{"season_number": 1, "episode_count": 2}]}
    t_historial = types.SimpleNamespace(serie=lambda sid: ficha_tmdb)
    gh_serie = archivo_vistos.Historial(perfil=perfil_serie, ajustes=lambda k: "false",
                                         cliente=lambda: t_historial, vistos_trakt=lambda sid: ["1:1"])
    episodio_final = dict(m1, e=2)
    gh_serie.al_parar(episodio_final, None, True)
    comprobar("historial: una serie con capítulos pendientes no se archiva",
              archivo_vistos.leer(perfil_serie, "serie") == [])
    sg.marcar_visto(perfil_serie, episodio_final)
    ficha_tmdb["in_production"] = True
    gh_serie.al_parar(episodio_final, None, True)
    comprobar("historial: una serie en producción no se archiva aunque esté al día",
              archivo_vistos.leer(perfil_serie, "serie") == [])
    ficha_tmdb["in_production"] = False
    gh_serie.al_parar(episodio_final, None, True)
    comprobar("historial: archiva la serie completa cuando coinciden Trakt y el seguimiento local",
              [(f["titulo"], f["nota"]) for f in archivo_vistos.leer(perfil_serie, "serie")] == [("Ficción", None)])

# Índice local: se guarda la disponibilidad y la búsqueda al abrir el título puede actualizarla.
from resources.lib import disponibilidad as indice  # noqa: E402

config = (("proveedores",), {"idioma": "CAST"})
ficha = {"id": 42, "title": "Ejemplo"}
with tempfile.TemporaryDirectory() as cache:
    with patch.object(indice.time, "time", return_value=100):
        indice.filtrar([ficha], cache, config)
        indice.comprobar_lote(cache, config, lambda f: True)
    with patch.object(indice.time, "time", return_value=10 * indice.DIA):
        comprobar("una fuente confirmada sigue visible y no vuelve a la cola al navegar",
                  indice.filtrar([ficha], cache, config) == ([ficha], False))
        indice.registrar(cache, config, ficha["id"], False)
        comprobar("una búsqueda completa sin fuentes al abrir el título actualiza el índice",
                  indice.filtrar([ficha], cache, config) == ([], False))
        otro = {"id": 43}
        indice.filtrar([otro], cache, config)

        def comprobar_en_paralelo(f):
            indice.registrar(cache, config, f["id"], True)
            return False

        indice.comprobar_lote(cache, config, comprobar_en_paralelo)
        comprobar("un lote antiguo no pisa la comprobación al abrir el título",
                  indice.filtrar([otro], cache, config) == ([otro], False))
        comprobar("una configuración distinta de idioma vuelve a comprobar",
                  indice.filtrar([otro], cache, (config[0], {"idioma": "LAT"})) == ([], True))

# Internet Archive real (necesita Internet)
from resources.lib.providers import Peli  # noqa: E402
from resources.lib.providers.archive_org import ArchiveOrg  # noqa: E402
try:
    f = ArchiveOrg().buscar(Peli("El maquinista de la General", "The General", 1926))
    print("   Internet Archive:", len(f), "fuentes;", f[0].url if f else "-")
    comprobar("Internet Archive devuelve fuentes reales", len(f) > 0)
except Exception as e:
    comprobar("Internet Archive accesible (%s)" % e, False)

print("\n%s" % ("TODO CORRECTO" if not fallos else "%d FALLOS" % fallos))
sys.exit(1 if fallos else 0)
