"""Prueba el addon fuera de Kodi con módulos xbmc* simulados.

Uso: python tools/prueba_local.py
"""
import json
import os
import runpy
import sys
import tempfile
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
           "idioma_pref": "0", "calidad_max": "0", "solo_idioma": "false", "autoplay": "false", "inicio_plataforma": "false"}
TMDB_FALSO = {
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
    def __init__(self, label="", path=""):
        self.label, self.path, self.props, self.menu = label, path, {}, []
        self.tag = _Tag()
        LIS.append(self)

    def setLabel(self, l): self.label = l
    def getLabel(self): return self.label

    def setArt(self, d): pass
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


_mod("xbmc", LOGINFO=1, log=lambda m, l=0: print("   LOG", m),
     executebuiltin=lambda c: REGISTRO["builtin"].append(c), sleep=lambda ms: None, Player=_Player, getInfoLabel=lambda k: "", getSkinDir=lambda: "skin.estuary",
     Monitor=lambda: types.SimpleNamespace(abortRequested=lambda: True, waitForAbort=lambda s: True), getCondVisibility=lambda c: False)
_mod("xbmcvfs", translatePath=lambda p: TMP)
_mod("xbmcaddon", Addon=lambda: types.SimpleNamespace(
    getSetting=lambda k: AJUSTES.get(k, ""), setSetting=lambda k, v: AJUSTES.__setitem__(k, v), getAddonInfo=lambda k: TMP, openSettings=lambda: None))
_mod("xbmcgui", ListItem=ListItem, NOTIFICATION_INFO=0, Window=_Ventana,
     DialogProgress=lambda: types.SimpleNamespace(create=lambda *a: None, close=lambda: None,
                                                 update=lambda *a: None, iscanceled=lambda: False),
     Dialog=lambda: types.SimpleNamespace(
         notification=lambda t, m, *a: REGISTRO["avisos"].append(m), ok=lambda *a: None,
         input=lambda *a: REGISTRO.get("input", ""), contextmenu=lambda ops: (print("   MENÚ:", ops), REGISTRO.get("menu", 0))[1], select=lambda t, ops: (print("   SELECTOR:", ops), REGISTRO["select"])[1]))
_mod("xbmcplugin", SORT_METHOD_LABEL=1, SORT_METHOD_VIDEO_YEAR=2, SORT_METHOD_UNSORTED=0,
     addDirectoryItem=lambda h, u, li, isFolder=False: REGISTRO["items"].append((li.label, u)),
     addDirectoryItems=lambda h, its, n=0: REGISTRO["items"].extend((li.label, u) for u, li, _ in its),
     endOfDirectory=lambda h, succeeded=True, cacheToDisc=True: REGISTRO.__setitem__("fin", succeeded), setContent=lambda h, c: None,
     addSortMethod=lambda h, m: None,
     setResolvedUrl=lambda h, ok, li: (REGISTRO.__setitem__("resuelto", (ok, li.path)), REGISTRO.__setitem__("li", li)))


def abrir(consulta=""):
    REGISTRO.update(items=[], resuelto=None, avisos=[])
    del LIS[:]
    sys.argv = ["plugin://plugin.video.palantix/", "1", consulta]
    for m in [m for m in sys.modules if m.startswith("resources")]:
        del sys.modules[m]
    import resources.lib.tmdb as tm  # TMDB simulado (sin red ni clave real)
    tm.TMDB._get = lambda self, ruta, **p: TMDB_FALSO[ruta]
    runpy.run_path(os.path.join(RAIZ, "main.py"), run_name="__main__")
    return REGISTRO


fallos = 0


def comprobar(nombre, cond):
    global fallos
    print(("OK    " if cond else "FALLO ") + nombre)
    fallos += 0 if cond else 1


from urllib.parse import urlencode  # noqa: E402

r = abrir("")
comprobar("menú principal: Películas, Series, Continuar viendo, Seguimiento, Favoritas, Listas, Ajustes, Actualizar", len(r["items"]) == 8)

r = abrir("?accion=listas")
comprobar("Mis listas muestra las 3 listas", len(r["items"]) == 3)

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

r = abrir("?" + urlencode({"accion": "reproducir", "id": 653, "titulo": "Nosferatu", "anio": "1922"}))
comprobar("ficha TMDB encuentra su fuente en la lista por tmdb_id", r["resuelto"] == (True, "https://ejemplo.invalid/nosferatu.mp4"))

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
comprobar("menú Series con 6 entradas (con Por año)", len(r["items"]) == 6)
r = abrir("?accion=m_peliculas")
comprobar("menú Películas con 8 entradas (con Por año y Sagas)", len(r["items"]) == 8)
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
print("   (selector de fuentes, mejor arriba:)")
r = abrir(EP)
comprobar("capítulo: selector ordenado y reproduce la elegida",
          r["resuelto"] == (True, "https://ejemplo.invalid/ficcion.s01e02.CASTELLANO.2160p.mkv"))
REGISTRO["select"] = 0
from resources.lib import etiquetas as et  # noqa: E402
from resources.lib.providers import ListaURL as LU, Peli as P  # noqa: E402
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
comprobar("al día: si no se oculta, sale en gris", r["items"] and "al día" in r["items"][0][0])
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
comprobar("novedades: si ya lo sabías (visto hoy) es pendiente pero no NUEVO", est["pendientes"] == 1 and not est["nuevo"])
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
