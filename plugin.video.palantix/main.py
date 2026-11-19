"""Punto de entrada del addon. Kodi lo llama con: sys.argv = [url_base, handle, '?parametros']."""
import json
import os
import sys
import time
from urllib.parse import parse_qsl, urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from resources.lib import disponibilidad, etiquetas, listas
from resources.lib import actualizar, debrid, inicio, mislistas, novedades, progreso, seguimiento, subtitulos, trakt
from resources.lib import tmdb as tmdb_mod
from resources.lib.providers import ListaURL, Peli, buscar_fuentes
from resources.lib.providers.stremio import Stremio

ADDON = xbmcaddon.Addon()
BASE = sys.argv[0]
HANDLE = int(sys.argv[1])
PARAMS = dict(parse_qsl(sys.argv[2][1:]))
PERFIL = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
CACHE = os.path.join(PERFIL, "cache")
FAVORITAS = os.path.join(PERFIL, "favoritas.json")
BUSQUEDAS = os.path.join(PERFIL, "busquedas.json")
ORDENES = ["popularidad", "estreno", "valoracion", "titulo"]
COLORES = ["", "gold", "deepskyblue", "lime", "orange", "violet", "white"]


# ---------------------------------------------------------------- utilidades
def url(**kw):
    return BASE + "?" + urlencode(kw)


def log(msg):
    xbmc.log("[Palantix] %s" % msg, xbmc.LOGINFO)


def aviso(msg):
    xbmcgui.Dialog().notification("Palantix", msg, xbmcgui.NOTIFICATION_INFO, 4000)


def ajuste_int(clave, defecto):
    try:
        return int(ADDON.getSetting(clave))
    except ValueError:
        return defecto


def mis_listas_guardadas():
    """Listas del usuario. La primera vez pasa aquí las direcciones de las casillas antiguas de Ajustes."""
    antiguas = [ADDON.getSetting("lista_%d" % i) for i in (1, 2, 3)]
    if any(a.strip() for a in antiguas):
        mislistas.migrar(PERFIL, antiguas)
        for i in (1, 2, 3):
            ADDON.setSetting("lista_%d" % i, "")
    return mislistas.leer(PERFIL)


def origenes_listas():
    return [l["origen"] for l in mis_listas_guardadas()]


def ttl_listas():
    return max(1, ajuste_int("cache_min", 60)) * 60


def clave_tmdb():
    # instancia NUEVA del addon: la global guarda los valores de cuando arrancó y no ve lo recién guardado
    return tmdb_mod.limpiar_clave(xbmcaddon.Addon().getSetting("tmdb_key"))


def pedir_clave_tmdb():
    """Pide la clave en un cuadro directo, la comprueba con TMDB y la guarda."""
    for _ in range(3):
        texto = xbmcgui.Dialog().input("Clave de TMDB (la «Clave de la API» corta o el «Token» largo)")
        clave = tmdb_mod.limpiar_clave(texto or "")
        if not clave:
            return None
        ok = tmdb_mod.validar(clave)
        if ok is False:
            xbmcgui.Dialog().ok("Palantix", "TMDB no acepta esa clave.\nRevísala en themoviedb.org > Ajustes > API "
                                            "y vuelve a escribirla.")
            continue
        xbmcaddon.Addon().setSetting("tmdb_key", clave)
        aviso("Clave de TMDB guardada" + ("" if ok else " (no se pudo comprobar: ¿hay Internet?)"))
        return clave
    return None


def comprobar_tmdb():
    clave = clave_tmdb()
    if not clave:
        return pedir_clave_tmdb()
    ok = tmdb_mod.validar(clave)
    if ok:
        xbmcgui.Dialog().ok("Palantix", "La clave de TMDB funciona correctamente.")
    elif ok is False:
        xbmcgui.Dialog().ok("Palantix", "TMDB no acepta la clave guardada. Escríbela de nuevo.")
        pedir_clave_tmdb()
    else:
        xbmcgui.Dialog().ok("Palantix", "No se pudo conectar con TMDB. ¿Hay Internet?")


def api(obligatoria=True):
    clave = clave_tmdb()
    if not clave and obligatoria:
        clave = pedir_clave_tmdb()
    if not clave:
        return None
    i = ajuste_int("orden_listas", 0)
    idioma, region = tmdb_mod.idioma_de(ADDON.getSetting("idioma_cat") or 0)
    return tmdb_mod.TMDB(clave, idioma, region,
                         orden=ORDENES[i] if 0 <= i < len(ORDENES) else "popularidad")


def marcas_visibles(a):
    """Etiquetas [CAST] [1080p]... para los títulos, según Ajustes (mostrar y color)."""
    if ADDON.getSetting("mostrar_etiquetas") == "false":
        return ""
    texto = etiquetas.texto_etiquetas(a)
    i = ajuste_int("color_etiquetas", 1)
    color = COLORES[i] if 0 <= i < len(COLORES) else ""
    return "[COLOR %s]%s[/COLOR]" % (color, texto) if texto and color else texto


VERDE, AZUL, GRIS = "lime", "deepskyblue", "gray"


def color(texto, c):
    return "[COLOR %s]%s[/COLOR]" % (c, texto)


_CACHE = {}


def mi_progreso():
    if "progreso" not in _CACHE:
        _CACHE["progreso"] = progreso.leer(PERFIL)
    return _CACHE["progreso"]


def mis_novedades():
    if "novedades" not in _CACHE:
        _CACHE["novedades"] = novedades.leer(PERFIL)
    return _CACHE["novedades"]


def mis_series():
    if "seguimiento" not in _CACHE:
        _CACHE["seguimiento"] = seguimiento.leer(PERFIL)
    return _CACHE["seguimiento"]


def marca_serie(sid):
    """Distintivo de una serie en seguimiento: ● NUEVO o «N pendientes»."""
    n = mis_novedades().get(str(sid)) or {}
    if n.get("nuevo"):
        return color("● NUEVO", VERDE)
    if n.get("pendientes"):
        return color("%d pendiente%s" % (n["pendientes"], "" if n["pendientes"] == 1 else "s"), AZUL)
    return ""


def fecha_es(iso):
    return "%s-%s-%s" % (iso[8:10], iso[5:7], iso[0:4]) if iso and len(iso) >= 10 else (iso or "")


def paginas_por_pantalla():
    return (1, 2, 3)[min(max(ajuste_int("paginas", 0), 0), 2)]


def varias_paginas(funcion, pagina):
    """Junta 1-3 páginas de TMDB (20/40/60 elementos) en una sola pantalla."""
    k = paginas_por_pantalla()
    primera = (pagina - 1) * k + 1
    datos = funcion(primera)
    resultados = list(datos.get("results", []))
    total = int(datos.get("total_pages", 1))
    for n in range(primera + 1, min(primera + k, total + 1)):
        resultados += funcion(n).get("results", [])
    return {"page": pagina, "total_pages": -(-total // k), "results": resultados}


# Vistas de la piel Estuary: 51 Póster, 500 Mosaico, 54 Mosaico con información, 55 Lista ancha, 50 Lista
VISTAS = {"movies": (51, 500, 54, 50), "tvshows": (51, 500, 54, 50), "seasons": (51, 500, 54, 50),
          "episodes": (55, 55, 54, 50)}


def vista(contenido):
    """Pone la vista de carátulas que toca. Solo con Estuary: otras pieles usan otros números."""
    if xbmc.getSkinDir() != "skin.estuary" or contenido not in VISTAS:
        return
    i = min(max(ajuste_int("vista_listados", 0), 0), 3)
    xbmc.executebuiltin("Container.SetViewMode(%d)" % VISTAS[contenido][i])


def fin_listado(contenido=None, ok=True):
    xbmcplugin.endOfDirectory(HANDLE, succeeded=ok, cacheToDisc=False)
    if ok and contenido:
        vista(contenido)


LOGO = ADDON.getAddonInfo("icon")
FONDO = ADDON.getAddonInfo("fanart")


def carpeta(etiqueta, destino, icono="DefaultFolder.png"):
    """Entrada de menú: icono pequeño de la lista, y el logo y el fondo de Palantix en grande."""
    li = xbmcgui.ListItem(etiqueta)
    li.setArt({"icon": icono, "thumb": LOGO, "poster": LOGO, "fanart": FONDO})
    xbmcplugin.addDirectoryItem(HANDLE, destino, li, isFolder=True)


# ---------------------------------------------------------------- Debrid
class Ajustes:
    """Puente entre los ajustes de Kodi y los módulos que no dependen de Kodi."""
    def get(self, k):
        return ADDON.getSetting(k)

    def set(self, k, v):
        ADDON.setSetting(k, v)


AJ = Ajustes()


def _kw():
    return {"cache_dir": CACHE, "log": log, "espera": lambda s: xbmc.sleep(int(s * 1000))}


def _elegir_fichero(videos):
    return xbmcgui.Dialog().select("Elige fichero", ["%s (%.1f GB)" % (v[0], v[1] / 1e9) for v in videos])


def resolver(enlace, avisar=True, elegir=_elegir_fichero, privada=False):
    """Devuelve la URL final reproducible, o None si no se pudo (avisa si `avisar`)."""
    opciones = _kw()
    if privada:
        opciones["log"] = lambda _: None
    servicios = debrid.activos(AJ, **opciones)
    progreso = None
    try:
        if servicios and (enlace.startswith("magnet:") or any(s.admite(enlace) for s in servicios)):
            progreso = xbmcgui.DialogProgress()
            progreso.create("Palantix", "Pidiendo el enlace al servicio Debrid...")
        return debrid.resolver(enlace, servicios, elegir=elegir,
                               cancelado=progreso.iscanceled if progreso else (lambda: False),
                               log=opciones["log"])
    except (debrid.DebridError, debrid.NoListo) as e:
        if not privada:
            log("Debrid: %s" % e)
        if avisar:
            aviso(debrid.mensaje_privado(e) if privada else str(e))
        return None
    except Exception as e:
        if not privada:
            log("Debrid fallo inesperado: %s" % e)
        if avisar:
            aviso("El servicio Debrid no responde")
        return None
    finally:
        if progreso:
            progreso.close()


def servicio_por_id(sid):
    return trakt.Trakt(AJ, log=log) if sid == "trakt" else debrid.por_id(sid, AJ, **_kw())


def vincular():
    s = servicio_por_id(PARAMS["s"])
    if s.tipo_vinculo == "clave":
        clave = xbmcgui.Dialog().input("Clave de la API de %s (la ves en tu cuenta, en la web)" % s.nombre)
        if not clave:
            return
        AJ.set(s.id + "_apikey", clave.strip())
        try:
            texto = s.cuenta()
        except Exception as e:
            AJ.set(s.id + "_apikey", "")
            return xbmcgui.Dialog().ok(s.nombre, "La clave no funciona: %s" % e)
        AJ.set(s.id + "_activo", "true")
        return xbmcgui.Dialog().ok(s.nombre, "Cuenta vinculada.\n" + texto)
    if PARAMS["s"] == "trakt" and not s.configurado():
        return xbmcgui.Dialog().ok("Trakt", "Primero crea tu aplicación en trakt.tv/oauth/applications\n"
                                   "(redirect: urn:ietf:wg:oauth:2.0:oob) y pega aquí Client ID y Client Secret.")
    try:
        pin = s.iniciar_pin()
    except Exception as e:
        return aviso("No se pudo pedir el código: %s" % e)
    progreso = xbmcgui.DialogProgress()
    progreso.create("Vincular %s" % s.nombre,
                    "Entra en [B]%s[/B] desde el móvil o el ordenador\ne introduce el código: [B]%s[/B]"
                    % (pin["url"], pin["codigo"]))
    paso = max(5, pin["intervalo"])
    for i in range(0, pin["expira"], paso):
        if progreso.iscanceled():
            break
        progreso.update(int(100 * i / pin["expira"]))
        try:
            if s.comprobar_pin(pin["datos"]):
                progreso.close()
                return xbmcgui.Dialog().ok(s.nombre, "Cuenta vinculada correctamente.")
        except (debrid.DebridError, trakt.TraktError) as e:
            progreso.close()
            return aviso(str(e))
        xbmc.sleep(paso * 1000)
    progreso.close()
    aviso("No se completó la vinculación")


def ver_cuenta():
    s = servicio_por_id(PARAMS["s"])
    if not s.vinculado():
        return xbmcgui.Dialog().ok(s.nombre, "Aún no has vinculado la cuenta.")
    try:
        xbmcgui.Dialog().ok(s.nombre, s.cuenta())
    except Exception as e:
        xbmcgui.Dialog().ok(s.nombre, str(e))


# ---------------------------------------------------------------- favoritas
def leer_favoritas():
    try:
        with open(FAVORITAS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def guardar_favoritas(lista):
    os.makedirs(PERFIL, exist_ok=True)
    with open(FAVORITAS, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False)


# ---------------------------------------------------------------- fichas
def _arte(d):
    return {
        "poster": tmdb_mod.TMDB.imagen(d.get("poster_path")),
        "thumb": tmdb_mod.TMDB.imagen(d.get("poster_path"), "w342"),
        "fanart": tmdb_mod.TMDB.imagen(d.get("backdrop_path"), "w1280"),
    }


def ficha_pelicula(m):
    """Convierte un resultado de TMDB (o una favorita guardada) en un elemento reproducible."""
    titulo = m.get("title") or m.get("original_title") or "?"
    anio = (m.get("release_date") or "")[:4]
    li = xbmcgui.ListItem("%s (%s)" % (titulo, anio) if anio else titulo)
    li.setArt(_arte(m))
    tag = li.getVideoInfoTag()  # Kodi 20+
    tag.setTitle(titulo)
    tag.setOriginalTitle(m.get("original_title", ""))
    tag.setPlot(m.get("overview", ""))
    tag.setMediaType("movie")
    tag.setRating(float(m.get("vote_average") or 0), int(m.get("vote_count") or 0))
    if anio.isdigit():
        tag.setYear(int(anio))
    li.setProperty("IsPlayable", "true")
    prog = mi_progreso().get("p:%s" % m["id"])
    if prog:  # barra de progreso sobre la carátula
        tag.setResumePoint(float(prog["pos"]), float(prog["total"]))

    guardable = {k: m.get(k) for k in ("id", "title", "original_title", "release_date", "overview",
                                       "poster_path", "backdrop_path", "vote_average", "vote_count")}
    es_fav = any(f.get("id") == m["id"] for f in leer_favoritas())
    li.addContextMenuItems([
        ("Ver tráiler", "RunPlugin(%s)" % url(accion="trailer", id=m["id"])),
        ("Elegir fuente", "PlayMedia(%s)" % url(accion="reproducir", id=m["id"], titulo=titulo,
                                                original=m.get("original_title", ""), anio=anio, elegir=1)),
        ("Quitar de Favoritas" if es_fav else "Añadir a Favoritas",
         "RunPlugin(%s)" % url(accion="fav_quitar" if es_fav else "fav_poner",
                               id=m["id"], datos=json.dumps(guardable))),
    ])
    destino = url(accion="reproducir", id=m["id"], titulo=titulo,
                  original=m.get("original_title", ""), anio=anio)
    return destino, li, False


def ficha_serie(s):
    titulo = s.get("name") or s.get("original_name") or "?"
    anio = (s.get("first_air_date") or "")[:4]
    li = xbmcgui.ListItem("%s (%s)" % (titulo, anio) if anio else titulo)
    li.setArt(_arte(s))
    tag = li.getVideoInfoTag()
    tag.setTitle(titulo)
    tag.setTvShowTitle(titulo)
    tag.setOriginalTitle(s.get("original_name", ""))
    tag.setPlot(s.get("overview", ""))
    tag.setMediaType("tvshow")
    tag.setRating(float(s.get("vote_average") or 0), int(s.get("vote_count") or 0))
    if anio.isdigit():
        tag.setYear(int(anio))
    li.addContextMenuItems([("Ver tráiler", "RunPlugin(%s)" % url(accion="trailer", id=s["id"], tipo="tv"))])
    nov = mis_novedades().get(str(s["id"])) or {}
    if nov.get("pendientes"):  # la piel pinta el número de capítulos pendientes sobre la carátula
        li.setProperty("UnWatchedEpisodes", str(nov["pendientes"]))
        li.setLabel("%s  %s" % (li.getLabel(), marca_serie(s["id"])))
    destino = url(accion="temporadas", id=s["id"], titulo=titulo, original=s.get("original_name", ""), anio=anio)
    return destino, li, True


def ficha_lista(it):
    """Elemento de una lista propia: se reproduce directamente con su URL."""
    if it["tipo"] == "episodio":
        etiqueta = "%s %dx%02d" % (it["titulo"], it["temporada"], it["episodio"])
    else:
        etiqueta = "%s (%d)" % (it["titulo"], it["anio"]) if it["anio"] else it["titulo"]
    a = etiquetas.analizar(it["idioma"], it["calidad"], it["url"].rsplit("/", 1)[-1])
    marcas = marcas_visibles(a)
    li = xbmcgui.ListItem(etiqueta + ("  " + marcas if marcas else ""))
    li.setArt({"poster": it["poster"], "thumb": it["poster"], "fanart": it["fanart"]})
    tag = li.getVideoInfoTag()
    tag.setTitle(etiqueta)
    tag.setPlot(it["sinopsis"])
    if it["tipo"] == "episodio":
        tag.setMediaType("episode")
        tag.setTvShowTitle(it["titulo"])
        tag.setSeason(it["temporada"])
        tag.setEpisode(it["episodio"])
    else:
        tag.setMediaType("movie")
    if it["anio"]:
        tag.setYear(it["anio"])
    li.setProperty("IsPlayable", "true")
    return url(accion="reproducir_directo", u=it["url"]), li, False


def listar(datos, accion, ficha=ficha_pelicula, contenido="movies", **extra):
    xbmcplugin.setContent(HANDLE, contenido)
    resultados = datos.get("results", [])
    if contenido == "movies":
        resultados = peliculas_disponibles(resultados)
    items = [ficha(m) for m in resultados]
    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    pagina, total = int(datos.get("page", 1)), int(datos.get("total_pages", 1))
    if pagina < min(total, 500):  # TMDB no sirve más allá de la página 500
        carpeta("Página siguiente (%d) >>" % (pagina + 1), url(accion=accion, page=pagina + 1, **extra))
    fin_listado(contenido)


def listar_series(datos, accion, **extra):
    listar(datos, accion, ficha=ficha_serie, contenido="tvshows", **extra)


# ---------------------------------------------------------------- pantallas
def menu():
    carpeta("Películas", url(accion="m_peliculas"), "DefaultMovies.png")
    carpeta("Series", url(accion="m_series"), "DefaultTVShows.png")
    a_medias = len(progreso.peliculas(PERFIL))
    carpeta("Continuar viendo películas" + ("  " + color("(%d)" % a_medias, AZUL) if a_medias else ""),
            url(accion="a_medias"), "DefaultInProgressShows.png")
    nuevas, pendientes = novedades.resumen(PERFIL)
    extra = color("● %d con capítulos nuevos" % nuevas, VERDE) if nuevas else (
        color("%d con capítulos pendientes" % pendientes, AZUL) if pendientes else "")
    carpeta("Series en seguimiento" + ("  " + extra if extra else ""), url(accion="seguir"), "DefaultTVShows.png")
    tk = trakt.Trakt(AJ, log=log)
    if tk.encendido():
        carpeta("Trakt", url(accion="trakt"), "DefaultAddonService.png")
        if ADDON.getSetting("trakt_listas_auto") != "false":
            try:
                for lid, nombre, n in tk.listas():
                    carpeta("%s  %s" % (nombre, color("(%d) · Trakt" % n, GRIS)), url(accion="trakt_lista", id=lid))
            except Exception as e:
                log("Trakt listas: %s" % e)
    carpeta("Mis favoritas", url(accion="favoritas"), "DefaultFavourites.png")
    carpeta("Mis listas", url(accion="listas"), "DefaultPlaylist.png")
    carpeta("Ajustes", url(accion="ajustes"), "DefaultAddonService.png")
    carpeta("Actualizar Palantix  " + color("(versión %s)" % ADDON.getAddonInfo("version"), GRIS),
            url(accion="actualizar"), "DefaultAddonsUpdates.png")
    xbmcplugin.endOfDirectory(HANDLE)


def menu_peliculas():
    carpeta("Tendencias de la semana", url(accion="tendencias"))
    carpeta("Populares", url(accion="populares"))
    carpeta("En cines", url(accion="en_cines"))
    carpeta("Mejor valoradas", url(accion="mejor_valoradas"))
    carpeta("Géneros", url(accion="generos"))
    carpeta("Por año", url(accion="anios", destino="anio"))
    carpeta("Sagas", url(accion="sagas"))
    carpeta("Buscar película", url(accion="buscar"), "DefaultAddonsSearch.png")
    xbmcplugin.endOfDirectory(HANDLE)


def menu_series():
    carpeta("Tendencias de la semana", url(accion="s_tendencias"))
    carpeta("Populares", url(accion="s_populares"))
    carpeta("Mejor valoradas", url(accion="s_mejor_valoradas"))
    carpeta("Géneros", url(accion="s_generos"))
    carpeta("Por año", url(accion="anios", destino="s_anio"))
    carpeta("Buscar serie", url(accion="s_buscar"), "DefaultAddonsSearch.png")
    xbmcplugin.endOfDirectory(HANDLE)


def generos(lista, accion):
    for g in lista:
        carpeta(g["name"], url(accion=accion, gid=g["id"]))
    xbmcplugin.endOfDirectory(HANDLE)


def leer_busquedas():
    try:
        with open(BUSQUEDAS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def apuntar_busqueda(tipo, texto):
    if ADDON.getSetting("recordar_busquedas") == "false":
        return
    todas = leer_busquedas()
    lista = [x for x in todas.get(tipo, []) if x.lower() != texto.lower()]
    todas[tipo] = ([texto] + lista)[:15]
    os.makedirs(PERFIL, exist_ok=True)
    with open(BUSQUEDAS, "w", encoding="utf-8") as f:
        json.dump(todas, f, ensure_ascii=False)


def buscar(funcion, accion, pregunta, lista_fn):
    texto = PARAMS.get("q")
    if not texto and not PARAMS.get("nueva"):
        anteriores = leer_busquedas().get(accion, []) if ADDON.getSetting("recordar_busquedas") != "false" else []
        if anteriores:  # primero, la pantalla con las búsquedas recientes
            carpeta("[B]Nueva búsqueda...[/B]", url(accion=accion, nueva=1), "DefaultAddonsSearch.png")
            for q in anteriores:
                carpeta(q, url(accion=accion, q=q))
            return xbmcplugin.endOfDirectory(HANDLE)
    texto = texto or xbmcgui.Dialog().input(pregunta)
    if not texto:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return
    apuntar_busqueda(accion, texto)
    lista_fn(varias_paginas(lambda n: funcion(texto, n), int(PARAMS.get("page", 1))), accion, q=texto)


def anios(destino):
    hoy = int(time.strftime("%Y"))
    for a in range(hoy, 1919, -1):
        carpeta(str(a), url(accion=destino, a=a))
    xbmcplugin.endOfDirectory(HANDLE)


def sagas(t):
    carpeta("[B]Buscar saga...[/B]", url(accion="sagas_buscar"), "DefaultAddonsSearch.png")
    for nombre in tmdb_mod.SAGAS:
        carpeta(nombre, url(accion="sagas_buscar", q=nombre))
    xbmcplugin.endOfDirectory(HANDLE)


def sagas_buscar(t):
    texto = PARAMS.get("q") or xbmcgui.Dialog().input("Buscar saga")
    if not texto:
        return xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    for c in t.buscar_saga(texto).get("results", []):
        li = xbmcgui.ListItem(c.get("name", "?"))
        li.setArt(_arte(c))
        li.getVideoInfoTag().setPlot(c.get("overview", ""))
        xbmcplugin.addDirectoryItem(HANDLE, url(accion="saga", id=c["id"]), li, True)
    xbmcplugin.endOfDirectory(HANDLE)


def seguir_viendo(t):
    """Series en seguimiento: primero las que tienen capítulos NUEVOS, luego pendientes y al final las que están al día."""
    if t:
        novedades.refrescar(PERFIL, t, log=log)
        _CACHE.pop("novedades", None)
    xbmcplugin.setContent(HANDLE, "episodes")
    ocultar = ADDON.getSetting("ocultar_al_dia") != "false"
    nov = mis_novedades()
    filas = []
    for sid, d in seguimiento.ordenadas(PERFIL):
        n = nov.get(sid) or {}
        prioridad = 0 if n.get("nuevo") else (1 if n.get("pendientes") else 2)
        filas.append((prioridad, -d.get("fecha", 0), sid, d, n))
    hay = False
    for prioridad, _, sid, d, n in sorted(filas, key=lambda f: (f[0], f[1])):
        comun = {"id": sid, "titulo": d.get("titulo", ""), "original": d.get("original", ""), "anio": d.get("anio", "")}
        sig = n.get("siguiente")
        if not sig and prioridad == 2 and ocultar:
            continue
        if sig:
            cabecera = "%s · %dx%02d. %s" % (d["titulo"], sig["s"], sig["e"], sig["nombre"])
            li = xbmcgui.ListItem("%s  %s" % (cabecera, marca_serie(sid)))
            li.setProperty("IsPlayable", "true")
            destino = url(accion="reproducir", tipo="episodio", s=sig["s"], e=sig["e"],
                          poster=d.get("poster", ""), fondo=d.get("fanart", ""), **comun)
            es_carpeta = False
            texto = "[B]Siguiente:[/B] %dx%02d · %s\n[B]Emitido:[/B] %s\n[B]Te quedan:[/B] %d capítulo%s\n\n%s" % (
                sig["s"], sig["e"], sig["nombre"], fecha_es(sig.get("emitido")), n.get("pendientes", 0),
                "" if n.get("pendientes") == 1 else "s", sig.get("sinopsis", ""))
        else:
            prox = n.get("proximo") or {}
            cola = ("próximo %sx%02d el %s" % (prox["s"], int(prox["e"]), fecha_es(prox["emitido"]))
                    if prox.get("s") and prox.get("emitido") else ("en emisión" if n.get("en_emision") else "terminada"))
            li = xbmcgui.ListItem("%s  %s" % (d["titulo"], color("al día · " + cola, GRIS)))
            destino, es_carpeta = url(accion="temporadas", **comun), True
            texto = "Has visto hasta el %sx%02d.\nEstado: %s." % (d["s"], int(d["e"]), cola)
        tag = li.getVideoInfoTag()
        tag.setMediaType("episode" if sig else "tvshow")
        tag.setTvShowTitle(d.get("titulo", ""))
        tag.setPlot(texto)
        if sig:
            tag.setSeason(int(sig["s"]))
            tag.setEpisode(int(sig["e"]))
            tag.setFirstAired(sig.get("emitido") or "")
        li.setProperty("UnWatchedEpisodes", str(n.get("pendientes", 0)))
        li.setArt({"poster": tmdb_mod.TMDB.imagen(d.get("poster")),
                   "thumb": tmdb_mod.TMDB.imagen((sig or {}).get("still"), "w500") or tmdb_mod.TMDB.imagen(d.get("fanart"), "w780"),
                   "fanart": tmdb_mod.TMDB.imagen(d.get("fanart"), "w1280")})
        li.addContextMenuItems([("Ver temporadas", "Container.Update(%s)" % url(accion="temporadas", **comun)),
                                ("Quitar de seguimiento", "RunPlugin(%s)" % url(accion="dejar_seguir", id=sid))])
        xbmcplugin.addDirectoryItem(HANDLE, destino, li, es_carpeta)
        hay = True
    if not hay:
        aviso("No hay capítulos pendientes: las series se apuntan solas al ver un capítulo")
    fin_listado("episodes")


def a_medias():
    """Películas sin terminar, con su barra de progreso."""
    xbmcplugin.setContent(HANDLE, "movies")
    pelis = progreso.peliculas(PERFIL)
    candidatos = [dict(d, id=d["tmdb"], title=d["titulo"], original_title=d.get("original"),
                       release_date=str(d.get("anio") or "")) for d in pelis]
    pelis = peliculas_disponibles(candidatos)
    for d in pelis:
        etiqueta = "%s (%s)" % (d["titulo"], d["anio"]) if d.get("anio") else d["titulo"]
        li = xbmcgui.ListItem("%s  %s" % (etiqueta, color("%s de %s" % (progreso.hhmmss(d["pos"]), progreso.hhmmss(d["total"])), AZUL)))
        li.setArt({"poster": tmdb_mod.TMDB.imagen(d.get("poster")), "fanart": tmdb_mod.TMDB.imagen(d.get("fanart"), "w1280")})
        tag = li.getVideoInfoTag()
        tag.setMediaType("movie")
        tag.setTitle(d["titulo"])
        tag.setResumePoint(float(d["pos"]), float(d["total"]))
        tag.setPlot("Te quedaste en el %s (%d %%). Te quedan %s." % (
            progreso.hhmmss(d["pos"]), 100 * d["pos"] // max(1, d["total"]), progreso.hhmmss(d["total"] - d["pos"])))
        li.setProperty("IsPlayable", "true")
        li.addContextMenuItems([("Quitar de Continuar viendo", "RunPlugin(%s)" % url(accion="quitar_medias", k="p:%s" % d["tmdb"]))])
        xbmcplugin.addDirectoryItem(HANDLE, url(accion="reproducir", id=d["tmdb"], titulo=d["titulo"],
                                                original=d.get("original", ""), anio=d.get("anio", ""),
                                                poster=d.get("poster", ""), fondo=d.get("fanart", "")), li, False)
    if not pelis:
        aviso("No hay películas a medias para mostrar")
    fin_listado("movies")


def quitar_medias():
    progreso.quitar(PERFIL, PARAMS["k"])
    xbmc.executebuiltin("Container.Refresh")


def _fichas_tmdb(t, elementos):
    """[(tipo, tmdb_id)] -> fichas completas de TMDB (carátula, sinopsis...), pedidas en paralelo."""
    from concurrent.futures import ThreadPoolExecutor

    def una(e):
        tipo, tid = e
        try:
            datos = t.detalle(tid) if tipo == "pelicula" else t.serie(tid)
            datos.setdefault("id", tid)
            return tipo, datos
        except Exception as ex:
            log("TMDB %s %s: %s" % (tipo, tid, ex))
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        fichas = [f for f in pool.map(una, elementos[:60]) if f]
    visibles = {str(m["id"]) for m in peliculas_disponibles(
        [datos for tipo, datos in fichas if tipo == "pelicula"], t)}
    return [ficha_pelicula(datos) if tipo == "pelicula" else ficha_serie(datos)
            for tipo, datos in fichas if tipo != "pelicula" or str(datos["id"]) in visibles]


def menu_trakt():
    carpeta("Películas pendientes", url(accion="trakt_pend", tipo="movies"), "DefaultMovies.png")
    carpeta("Series pendientes", url(accion="trakt_pend", tipo="shows"), "DefaultTVShows.png")
    try:
        for lid, nombre, n in trakt.Trakt(AJ, log=log).listas():
            carpeta("%s  %s" % (nombre, color("(%d)" % n, GRIS)), url(accion="trakt_lista", id=lid))
    except Exception as e:
        aviso(str(e))
    xbmcplugin.endOfDirectory(HANDLE)


def trakt_pendientes(t):
    tipo = PARAMS.get("tipo", "movies")
    elems = [("pelicula" if tipo == "movies" else "serie", tid) for tid, _, _ in trakt.Trakt(AJ, log=log).pendientes(tipo)]
    xbmcplugin.setContent(HANDLE, "movies" if tipo == "movies" else "tvshows")
    fichas = _fichas_tmdb(t, elems)
    xbmcplugin.addDirectoryItems(HANDLE, fichas, len(fichas))
    xbmcplugin.endOfDirectory(HANDLE)


def trakt_lista(t):
    elems = [(tipo, tid) for tipo, tid, _, _ in trakt.Trakt(AJ, log=log).lista(PARAMS["id"])]
    xbmcplugin.setContent(HANDLE, "movies")
    fichas = _fichas_tmdb(t, elems)
    xbmcplugin.addDirectoryItems(HANDLE, fichas, len(fichas))
    xbmcplugin.endOfDirectory(HANDLE)


def dejar_seguir():
    seguimiento.quitar(PERFIL, PARAMS["id"])
    aviso("Quitada de seguimiento")
    xbmc.executebuiltin("Container.Refresh")


def temporadas(t):
    s = t.serie(PARAMS["id"])
    xbmcplugin.setContent(HANDLE, "seasons")
    comunes = {k: PARAMS.get(k, "") for k in ("id", "titulo", "original", "anio")}
    # Los «Especiales» (temporada 0) al final
    for temp in sorted(s.get("seasons", []), key=lambda x: (x["season_number"] == 0, x["season_number"])):
        li = xbmcgui.ListItem("%s (%d capítulos)" % (temp.get("name") or "Temporada %d" % temp["season_number"],
                                                      temp.get("episode_count") or 0))
        li.setArt({"poster": tmdb_mod.TMDB.imagen(temp.get("poster_path") or s.get("poster_path")),
                   "fanart": tmdb_mod.TMDB.imagen(s.get("backdrop_path"), "w1280")})
        tag = li.getVideoInfoTag()
        tag.setMediaType("season")
        tag.setTvShowTitle(PARAMS.get("titulo", ""))
        tag.setSeason(temp["season_number"])
        tag.setPlot(temp.get("overview") or s.get("overview", ""))
        xbmcplugin.addDirectoryItem(HANDLE, url(accion="capitulos", s=temp["season_number"],
                                                poster=s.get("poster_path") or "", fondo=s.get("backdrop_path") or "",
                                                **comunes), li, True)
    fin_listado("seasons")


def capitulos(t):
    temp = t.temporada(PARAMS["id"], PARAMS["s"])
    xbmcplugin.setContent(HANDLE, "episodes")
    serie = PARAMS.get("titulo", "")
    hoy = time.strftime("%Y-%m-%d")
    seg = mis_series().get(str(PARAMS["id"])) or {}
    visto_hasta = (int(seg.get("s") or 0), int(seg.get("e") or 0))
    visto_dia = time.strftime("%Y-%m-%d", time.localtime(seg["fecha"])) if seg.get("fecha") else ""
    for ep in temp.get("episodes", []):
        emitido = ep.get("air_date") or ""
        n_s, n_e = ep["season_number"], ep["episode_number"]
        nombre = "%dx%02d. %s" % (n_s, n_e, ep.get("name") or "")
        if not emitido or emitido > hoy:
            nombre = color("%s (sale el %s)" % (nombre, fecha_es(emitido) or "?"), GRIS)
        elif seg and (n_s, n_e) > visto_hasta and emitido > visto_dia:
            nombre = "%s  %s" % (nombre, color("● NUEVO", VERDE))
        li = xbmcgui.ListItem(nombre)
        li.setArt({"thumb": tmdb_mod.TMDB.imagen(ep.get("still_path"), "w300"),
                   "poster": tmdb_mod.TMDB.imagen(temp.get("poster_path"))})
        tag = li.getVideoInfoTag()
        tag.setMediaType("episode")
        tag.setTitle(ep.get("name") or "")
        tag.setTvShowTitle(serie)
        tag.setSeason(n_s)
        tag.setEpisode(n_e)
        tag.setPlot(ep.get("overview") or "")
        tag.setFirstAired(emitido)
        if ep.get("runtime"):
            tag.setDuration(int(ep["runtime"]) * 60)
        if seg and (n_s, n_e) <= visto_hasta:
            tag.setPlaycount(1)  # marca de visto
        prog = mi_progreso().get("e:%s:%s:%s" % (PARAMS["id"], n_s, n_e))
        if prog:
            tag.setResumePoint(float(prog["pos"]), float(prog["total"]))
        li.setProperty("IsPlayable", "true")
        destino = url(accion="reproducir", tipo="episodio", id=PARAMS["id"], titulo=serie,
                      original=PARAMS.get("original", ""), anio=PARAMS.get("anio", ""), s=n_s, e=n_e,
                      poster=PARAMS.get("poster", ""), fondo=PARAMS.get("fondo", ""))
        li.addContextMenuItems([("Elegir fuente", "PlayMedia(%s&elegir=1)" % destino)])
        xbmcplugin.addDirectoryItem(HANDLE, destino, li, False)
    fin_listado("episodes")


def favoritas():
    listar({"results": leer_favoritas(), "page": 1, "total_pages": 1}, "favoritas")


def fav_cambiar(poner):
    favs = [f for f in leer_favoritas() if str(f.get("id")) != PARAMS["id"]]
    if poner:
        favs.insert(0, json.loads(PARAMS["datos"]))
    guardar_favoritas(favs)
    aviso("Añadida a Favoritas" if poner else "Quitada de Favoritas")
    xbmc.executebuiltin("Container.Refresh")


def mis_listas():
    """Nivel 1: las listas configuradas. Nivel 2: sus grupos. Nivel 3: las películas y capítulos."""
    n = PARAMS.get("n")
    if not n:
        carpeta("[B]➕  Añadir una lista[/B]", url(accion="lista_nueva"), "DefaultAddSource.png")
        for i, l in enumerate(mis_listas_guardadas(), 1):
            try:
                total = len(listas.cargar(l["origen"], CACHE, ttl_listas()))
                cola = color("%d título%s" % (total, "" if total == 1 else "s"), AZUL)
            except Exception:
                cola = color("no se puede leer", "red")
            li = xbmcgui.ListItem("%s   %s" % (l["nombre"], cola))
            li.setArt({"icon": "DefaultPlaylist.png", "thumb": LOGO, "fanart": FONDO})
            li.getVideoInfoTag().setPlot("[B]Dirección:[/B]\n%s" % l["origen"])
            li.addContextMenuItems([
                ("Renombrar", "RunPlugin(%s)" % url(accion="lista_renombrar", i=i - 1)),
                ("Recargar ahora", "RunPlugin(%s)" % url(accion="lista_recargar", i=i - 1)),
                ("Quitar esta lista", "RunPlugin(%s)" % url(accion="lista_quitar", i=i - 1))])
            xbmcplugin.addDirectoryItem(HANDLE, url(accion="listas", n=i), li, True)
        carpeta("ⓘ  Qué dirección puedo poner", url(accion="lista_ayuda"), "DefaultIconInfo.png")
        return xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)

    try:
        items = listas.cargar(origenes_listas()[int(n) - 1], CACHE, ttl_listas())
    except Exception as e:
        log("Lista %s: %s" % (n, e))
        aviso("No se pudo leer la lista %s" % n)
        return xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

    grupo = PARAMS.get("g")
    grupos = sorted({it["grupo"] for it in items})
    if grupo is None and len(grupos) > 1:
        carpeta("[Todas] (%d)" % len(items), url(accion="listas", n=n, g=""))
        for g in grupos:
            carpeta("%s (%d)" % (g, sum(1 for it in items if it["grupo"] == g)), url(accion="listas", n=n, g=g))
        return xbmcplugin.endOfDirectory(HANDLE)

    elegidos = [it for it in items if not grupo or it["grupo"] == grupo]
    elegidos.sort(key=lambda it: (it["titulo"].lower(), it["temporada"], it["episodio"]))
    xbmcplugin.setContent(HANDLE, "movies")
    fichas = [ficha_lista(it) for it in elegidos]
    xbmcplugin.addDirectoryItems(HANDLE, fichas, len(fichas))
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_VIDEO_YEAR)
    xbmcplugin.endOfDirectory(HANDLE)


def lista_nueva():
    origen = (xbmcgui.Dialog().input("Dirección de la lista (empieza por http o https)") or "").strip()
    if not origen:
        return
    barra = xbmcgui.DialogProgress()
    barra.create("Palantix", "Comprobando la lista...")
    try:
        texto = listas.descargar(origen)
        items = listas.parsear(texto)
    except Exception as e:
        barra.close()
        log("Lista nueva: %s" % e)
        return xbmcgui.Dialog().ok("Palantix", "Esa dirección no es una lista que Palantix pueda leer.\n"
                                   "Tiene que ser un fichero M3U o JSON, no una página web.\n"
                                   "Mira «Qué dirección puedo poner» en Mis listas.")
    barra.close()
    if not items:
        return xbmcgui.Dialog().ok("Palantix", "La lista se lee, pero no tiene ningún título con enlace.")
    sugerido = mislistas.nombre_por_defecto(origen)
    try:
        sugerido = json.loads(texto.lstrip("\ufeff")).get("nombre") or sugerido
    except (ValueError, AttributeError):
        pass
    nombre = xbmcgui.Dialog().input("Ponle un nombre a la lista", sugerido) or sugerido
    if not mislistas.anadir(PERFIL, nombre, origen):
        return aviso("Esa lista ya estaba añadida")
    xbmcgui.Dialog().ok("Palantix", "Lista «%s» añadida: %d título%s." % (nombre, len(items), "" if len(items) == 1 else "s"))
    xbmc.executebuiltin("Container.Refresh")


def lista_renombrar():
    i = int(PARAMS["i"])
    actual = mis_listas_guardadas()[i]["nombre"]
    nombre = xbmcgui.Dialog().input("Nuevo nombre", actual)
    if nombre:
        mislistas.renombrar(PERFIL, i, nombre)
        xbmc.executebuiltin("Container.Refresh")


def lista_recargar():
    import hashlib
    origen = mis_listas_guardadas()[int(PARAMS["i"])]["origen"]
    ruta = os.path.join(CACHE, "lista_%s.txt" % hashlib.md5(origen.encode()).hexdigest())
    if os.path.exists(ruta):
        os.remove(ruta)
    aviso("Lista recargada")
    xbmc.executebuiltin("Container.Refresh")


def lista_quitar():
    i = int(PARAMS["i"])
    l = mis_listas_guardadas()[i]
    if xbmcgui.Dialog().yesno("Palantix", "¿Quitar la lista «%s»?" % l["nombre"]):
        mislistas.quitar(PERFIL, i)
        xbmc.executebuiltin("Container.Refresh")


def kodi_en_espanol(preguntar=False):
    """Pone todo Kodi (botones, menús, ajustes) en español: instala el idioma si falta y lo activa."""
    if preguntar and not xbmcgui.Dialog().yesno("Palantix", "Kodi está en otro idioma (por eso ves «Settings», «Cancel»...).\n"
                                                "¿Lo pongo todo en español?"):
        return
    paquete = "resource.language.es_es"
    if not xbmc.getCondVisibility("System.HasAddon(%s)" % paquete):
        xbmc.executebuiltin("InstallAddon(%s)" % paquete, True)
        for _ in range(90):
            if xbmc.getCondVisibility("System.HasAddon(%s)" % paquete):
                break
            xbmc.sleep(1000)
    respuesta = xbmc.executeJSONRPC(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "Settings.SetSettingValue",
                                                "params": {"setting": "locale.language", "value": paquete}}))
    log("Idioma de Kodi: %s" % respuesta)
    if '"result":true' not in respuesta.replace(" ", ""):
        xbmcgui.Dialog().ok("Palantix", "No se pudo cambiar solo. Hazlo a mano:\nSettings > Interface > Regional > "
                                        "Language > Spanish.")


def ofrecer_espanol_una_vez():
    if ADDON.getSetting("preguntado_idioma") == "true" or xbmc.getLanguage(xbmc.ISO_639_1) == "es":
        return
    ADDON.setSetting("preguntado_idioma", "true")
    kodi_en_espanol(preguntar=True)


def trailer():
    t = api()
    clave = t.trailer_youtube(PARAMS["id"], PARAMS.get("tipo", "movie")) if t else None
    if not clave:
        return aviso("No hay tráiler en TMDB")
    if not xbmc.getCondVisibility("System.HasAddon(plugin.video.youtube)"):
        return aviso("Instala el addon de YouTube para ver tráileres")
    xbmc.executebuiltin("PlayMedia(plugin://plugin.video.youtube/play/?video_id=%s)" % clave)


# ---------------------------------------------------------------- reproducción
IDIOMAS_PRIORIDAD = {
    "CAST": "Castellano",
    "LAT": "Latino",
    "VOSE": "Versión original subtitulada",
    "VO": "Versión original",
}
IDIOMAS_AJUSTE = list(IDIOMAS_PRIORIDAD) + [""]
ORDENES_FUENTES = ("Idioma primero", "Calidad primero")
CALIDADES_AJUSTE = ["4K", "1080p", "720p"]


def configurar_prioridad_idiomas():
    dialogo = xbmcgui.Dialog()
    accion = dialogo.select("Prioridad de idiomas", ["Elegir orden", "Usar idioma preferido"])
    if accion == 1:
        ADDON.setSetting("prioridad_idiomas", "")
        return
    if accion != 0:
        return

    pendientes = list(IDIOMAS_PRIORIDAD)
    prioridad = []
    while len(pendientes) > 1:
        opciones = [IDIOMAS_PRIORIDAD[codigo] for codigo in pendientes]
        n = dialogo.select("Idioma en el puesto %d" % (len(prioridad) + 1), opciones)
        if n < 0:
            return
        prioridad.append(pendientes.pop(n))
    prioridad.extend(pendientes)
    ADDON.setSetting("prioridad_idiomas", ",".join(prioridad))
    aviso(" → ".join(IDIOMAS_PRIORIDAD[codigo] for codigo in prioridad))


def preferencias():
    i = ajuste_int("idioma_pref", 0)
    c = ajuste_int("calidad_max", 0)
    prioridad = tuple(dict.fromkeys(
        codigo for codigo in ADDON.getSetting("prioridad_idiomas").split(",")
        if codigo in IDIOMAS_PRIORIDAD
    ))
    idioma = prioridad[0] if prioridad else (IDIOMAS_AJUSTE[i] if 0 <= i < len(IDIOMAS_AJUSTE) else "")
    return {
        "idioma": idioma,
        "prioridad_idiomas": prioridad,
        "calidad_primero": ajuste_int("orden_fuentes", 0) == 1,
        "calidad_max": CALIDADES_AJUSTE[c] if 0 <= c < len(CALIDADES_AJUSTE) else "4K",
        "solo_idioma": ADDON.getSetting("solo_idioma") == "true",
    }


def consulta_fuentes(t):
    listas_activas = ADDON.getSetting("prov_listas") != "false"
    archivo_activo = ADDON.getSetting("prov_archive_org") != "false"
    listas_url = origenes_listas() if listas_activas else []
    manifiestos = []
    if ADDON.getSetting("prov_stremio") == "true":
        for n in range(1, 4):
            origen = ADDON.getSetting("stremio_%d" % n).strip()
            if origen:
                manifiestos.append((n, origen))
    extra = [ListaURL(listas_url, CACHE, ttl_listas(), log)] if any(listas_url) else []
    extra += [Stremio(origen, n, log) for n, origen in manifiestos]

    def buscar(peli):
        if manifiestos and not peli.imdb_id and t and peli.tmdb_id:
            try:
                peli.imdb_id = t.imdb_id(peli.tmdb_id, "tv" if peli.tipo == "episodio" else "movie")
            except Exception:
                log("No se pudo obtener el identificador IMDb")
        return buscar_fuentes(peli, activo=lambda _: archivo_activo, log=log, extra=extra)

    return buscar, (archivo_activo, listas_url, manifiestos)


def peliculas_disponibles(peliculas, t=None):
    if not peliculas or ADDON.getSetting("solo_peliculas_con_fuentes") != "true":
        return peliculas

    buscar, proveedores = consulta_fuentes(t or api(obligatoria=False))
    pref = preferencias()
    barra = None

    def consultar(m):
        anio = str(m.get("release_date") or "")[:4]
        peli = Peli(titulo=m.get("title") or "", titulo_original=m.get("original_title") or "",
                    anio=int(anio) if anio.isdigit() else 0, tmdb_id=m["id"], imdb_id=m.get("imdb_id") or "")
        return bool(etiquetas.ordenar(buscar(peli), **pref))

    def avance(hechos, total):
        nonlocal barra
        if barra is None:
            barra = xbmcgui.DialogProgress()
            barra.create("Palantix", "Comprobando fuentes de películas…")
        barra.update(100 * hechos // total, "Comprobando fuentes de películas…")
        return not barra.iscanceled()

    try:
        visibles = disponibilidad.filtrar(peliculas, consultar, CACHE, (proveedores, pref), avance)
    finally:
        if barra is not None:
            barra.close()
    if not visibles:
        aviso("No se encontraron fuentes para las películas de esta página")
    return visibles


def no_reproducir():
    xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())


def reproducir():
    episodio = PARAMS.get("tipo") == "episodio"
    peli = Peli(
        titulo=PARAMS.get("titulo", ""),
        titulo_original=PARAMS.get("original", ""),
        anio=int(PARAMS["anio"]) if PARAMS.get("anio", "").isdigit() else 0,
        tmdb_id=int(PARAMS.get("id", 0)),
        tipo="episodio" if episodio else "pelicula",
        temporada=int(PARAMS.get("s", 0)),
        episodio=int(PARAMS.get("e", 0)),
    )
    nombre = "%s %dx%02d" % (peli.titulo, peli.temporada, peli.episodio) if episodio else peli.titulo
    desde = 0
    previo = progreso.de(PERFIL, {"tipo": peli.tipo, "tmdb": peli.tmdb_id, "s": peli.temporada, "e": peli.episodio})
    if previo and not PARAMS.get("desde_cero"):
        n = xbmcgui.Dialog().contextmenu(["Reanudar desde %s" % progreso.hhmmss(previo["pos"]), "Desde el principio"])
        if n < 0:
            return no_reproducir()
        desde = previo["pos"] if n == 0 else 0
    barra = xbmcgui.DialogProgress()
    barra.create("Palantix", "Buscando fuentes para «%s»..." % nombre)
    try:
        buscar, _ = consulta_fuentes(api(obligatoria=False))
        fuentes = buscar(peli)
    finally:
        barra.close()

    pref = preferencias()
    ordenadas = etiquetas.ordenar(fuentes, **pref)
    if not ordenadas:
        aviso("No hay fuentes para «%s»%s" % (nombre, " en tu idioma" if fuentes else ""))
        return no_reproducir()

    automatico = ADDON.getSetting("autoplay") == "true" and not PARAMS.get("elegir")
    if automatico or len(ordenadas) == 1:
        candidatas = ordenadas  # si la mejor falla, se prueba la siguiente
    else:
        textos = ["%s  %s · %s" % (marcas_visibles(a) or etiquetas.texto_etiquetas(a), f.proveedor, f.etiqueta)
                  for f, a in ordenadas]
        n = xbmcgui.Dialog().select("Elige fuente · " + ORDENES_FUENTES[pref["calidad_primero"]], textos)
        if n < 0:
            return no_reproducir()
        candidatas = [ordenadas[n]]

    for i, (f, a) in enumerate(candidatas):
        ultima = i == len(candidatas) - 1
        def elegir(videos):
            if f.archivo:
                coincidencias = [n for n, v in enumerate(videos)
                                 if v[0].replace("\\", "/").rsplit("/", 1)[-1] == f.archivo]
                if len(coincidencias) == 1:
                    return coincidencias[0]
            return _elegir_fichero(videos)

        ruta = resolver(f.url, avisar=ultima, elegir=elegir, privada=f.privada)
        if not ruta:
            if not f.privada:
                log("Fuente descartada: %s" % f.etiqueta)
            continue
        if f.cabeceras:  # convención de Kodi para mandar cabeceras HTTP
            ruta += "|" + urlencode(f.cabeceras)
        if automatico and len(candidatas) > 1:
            aviso("%s %s" % (etiquetas.texto_etiquetas(a), f.proveedor))
        if not f.privada:
            log("Reproduciendo %s" % f.url)
        prioridad_audio = pref["prioridad_idiomas"] or (pref["idioma"],)
        avisar_al_servicio(peli, prioridad_audio)
        li = xbmcgui.ListItem(path=ruta)
        if desde:
            li.setProperty("StartOffset", str(int(desde)))
        sub = poner_subtitulos(peli, a, pref)
        if sub:
            li.setSubtitles([sub])
        return xbmcplugin.setResolvedUrl(HANDLE, True, li)
    no_reproducir()


def poner_subtitulos(peli, analisis, pref):
    """Descarga el mejor subtítulo en tu idioma si el audio de la fuente no lo es (o siempre, según Ajustes)."""
    clave = ADDON.getSetting("os_apikey").strip()
    modo = ajuste_int("subs_modo", 1)
    if not clave or not subtitulos.hace_falta(modo, analisis["idiomas"], pref["idioma"]):
        return None
    cliente = subtitulos.OpenSubtitles(clave, ADDON.getSetting("os_usuario"), ADDON.getSetting("os_clave"), log=log)
    try:
        lista = cliente.buscar(peli.tmdb_id, ADDON.getSetting("subs_idiomas") or "es",
                               peli.temporada if peli.tipo == "episodio" else 0,
                               peli.episodio if peli.tipo == "episodio" else 0)
        if not lista:
            aviso("No hay subtítulos en tu idioma para «%s»" % peli.titulo)
            return None
        carpeta = os.path.join(PERFIL, "subtitulos")
        ruta = cliente.descargar(lista[0]["file_id"], carpeta, peli.titulo)
        viejos = sorted((os.path.join(carpeta, f) for f in os.listdir(carpeta)), key=os.path.getmtime)
        for f in viejos[:-30]:  # guardamos solo los 30 últimos
            os.remove(f)
        aviso("Subtítulos en español puestos")
        return ruta
    except subtitulos.SubError as e:
        aviso(str(e))
    except Exception as e:
        log("Subtítulos: %s" % e)
    return None


def avisar_al_servicio(peli, prioridad_audio=()):
    """Deja en la ventana principal qué va a sonar y cuál es el siguiente capítulo (lo lee service.py)."""
    ventana = xbmcgui.Window(10000)
    meta = {"tipo": peli.tipo, "tmdb": peli.tmdb_id, "s": peli.temporada, "e": peli.episodio,
            "titulo": peli.titulo, "original": peli.titulo_original, "anio": peli.anio,
            "poster": PARAMS.get("poster", ""), "fanart": PARAMS.get("fondo", ""),
            "prioridad_audio": prioridad_audio}
    ventana.setProperty("palantix.meta", json.dumps(meta))
    ventana.clearProperty("palantix.siguiente")
    if peli.tipo != "episodio" or ADDON.getSetting("siguiente_activo") == "false":
        return
    t = api(obligatoria=False)
    sig = t.siguiente(peli.tmdb_id, peli.temporada, peli.episodio) if t else None
    if sig:
        destino = url(accion="reproducir", tipo="episodio", id=peli.tmdb_id, titulo=peli.titulo,
                      original=peli.titulo_original, anio=peli.anio or "", s=sig["temporada"], e=sig["episodio"],
                      poster=PARAMS.get("poster", ""), fondo=PARAMS.get("fondo", ""))
        ventana.setProperty("palantix.siguiente", json.dumps({
            "url": destino, "etiqueta": "%s %dx%02d. %s" % (peli.titulo, sig["temporada"], sig["episodio"], sig["nombre"])}))


def reproducir_directo():
    ruta = resolver(PARAMS["u"])
    xbmcplugin.setResolvedUrl(HANDLE, bool(ruta), xbmcgui.ListItem(path=ruta or ""))


# ---------------------------------------------------------------- enrutador
SIN_TMDB = {
    "m_peliculas": menu_peliculas,
    "m_series": menu_series,
    "reproducir": reproducir,
    "reproducir_directo": reproducir_directo,
    "vincular": vincular,
    "cuenta": ver_cuenta,
    "ad_pin": lambda: (PARAMS.__setitem__("s", "ad"), vincular()),  # compatibilidad con ajustes antiguos
    "favoritas": favoritas,
    "fav_poner": lambda: fav_cambiar(True),
    "fav_quitar": lambda: fav_cambiar(False),
    "listas": mis_listas,
    "anios": lambda: anios(PARAMS["destino"]),
    "dejar_seguir": dejar_seguir,
    "a_medias": a_medias,
    "trakt": menu_trakt,
    "quitar_medias": quitar_medias,
    "trailer": trailer,
    "ajustes": ADDON.openSettings,
    "orden_idiomas": configurar_prioridad_idiomas,
    "tmdb_clave": comprobar_tmdb,
    "actualizar": lambda: buscar_actualizacion(),
    "lista_nueva": lambda: lista_nueva(),
    "lista_renombrar": lambda: lista_renombrar(),
    "lista_recargar": lambda: lista_recargar(),
    "lista_quitar": lambda: lista_quitar(),
    "lista_ayuda": lambda: xbmcgui.Dialog().textviewer("Mis listas", mislistas.AYUDA),
    "kodi_es": lambda: kodi_en_espanol(),
}


def con_tmdb(t, accion, page):
    gid, anio = PARAMS.get("gid"), PARAMS.get("a")
    vp = varias_paginas
    if accion in ("tendencias", "populares", "en_cines", "mejor_valoradas"):
        listar(vp(getattr(t, accion), page), accion)
    elif accion in ("s_tendencias", "s_populares", "s_mejor_valoradas"):
        listar_series(vp(getattr(t, accion), page), accion)
    elif accion == "anio":
        listar(vp(lambda n: t.por_anio(anio, n), page), "anio", a=anio)
    elif accion == "s_anio":
        listar_series(vp(lambda n: t.s_por_anio(anio, n), page), "s_anio", a=anio)
    elif accion == "sagas":
        sagas(t)
    elif accion == "sagas_buscar":
        sagas_buscar(t)
    elif accion == "saga":
        listar(t.saga(PARAMS["id"]), "saga", id=PARAMS["id"])
    elif accion == "seguir":
        seguir_viendo(t)
    elif accion == "trakt_pend":
        trakt_pendientes(t)
    elif accion == "trakt_lista":
        trakt_lista(t)
    elif accion == "generos":
        generos(t.generos(), "genero")
    elif accion == "s_generos":
        generos(t.s_generos(), "s_genero")
    elif accion == "genero":
        listar(vp(lambda n: t.por_genero(gid, n), page), "genero", gid=gid)
    elif accion == "s_genero":
        listar_series(vp(lambda n: t.s_por_genero(gid, n), page), "s_genero", gid=gid)
    elif accion == "buscar":
        buscar(t.buscar, "buscar", "Buscar película", listar)
    elif accion == "s_buscar":
        buscar(t.s_buscar, "s_buscar", "Buscar serie", listar_series)
    elif accion == "temporadas":
        temporadas(t)
    elif accion == "capitulos":
        capitulos(t)


def buscar_actualizacion():
    local = ADDON.getAddonInfo("version")
    try:
        remota = actualizar.version_remota()
    except Exception as e:
        return xbmcgui.Dialog().ok("Palantix", "No se pudo comprobar si hay versión nueva (¿hay Internet?).\n%s" % e)
    if not remota:
        return xbmcgui.Dialog().ok("Palantix", "No se pudo leer la versión publicada en el repositorio.")
    if not actualizar.hay_nueva(local, remota):
        return xbmcgui.Dialog().ok("Palantix", "Ya tienes la última versión: %s" % local)
    if actualizar.pedir_a_kodi(log):
        pasos = ("Kodi está comprobando las actualizaciones del repositorio. "
                 "Si la instalación automática no se inicia, abre la ficha de Palantix en "
                 "Complementos → Mis complementos → Complementos de vídeo y selecciona Actualizar.")
    else:
        pasos = ("Activa Repositorio Palantix en Complementos → Mis complementos → Repositorios de complementos. "
                 "Si no aparece, instálalo desde la fuente de Palantix y vuelve a buscar la actualización.")
    xbmcgui.Dialog().ok("Palantix", "Hay una versión nueva (%s). Tienes la %s.\n%s" % (remota, local, pasos))



def abrir_inicio():
    """Pantalla de inicio estilo plataforma. Se cierra el listado vacío y se abre la ventana encima."""
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    t = api(obligatoria=True)
    try:
        tk = trakt.Trakt(AJ, log=log).encendido()
    except Exception:
        tk = False
    try:
        inicio.abrir(ADDON, PERFIL, t, url, favoritas=leer_favoritas(), con_trakt=tk, log=log,
                     filtrar_peliculas=lambda pelis: peliculas_disponibles(pelis, t))
    except Exception as e:  # si la pantalla nueva fallase en alguna tele, que no te quedes sin Palantix
        log("Inicio falló, abro el menú clásico: %s" % e)
        xbmc.executebuiltin("Container.Update(%s)" % url(accion="clasico"))


def main():
    accion = PARAMS.get("accion")
    if not accion:
        try:
            ofrecer_espanol_una_vez()
        except Exception as e:
            log("Idioma: %s" % e)
        if ADDON.getSetting("inicio_plataforma") != "false":
            return abrir_inicio()
        return menu()
    if accion == "clasico":
        return menu()
    if accion in SIN_TMDB:
        return SIN_TMDB[accion]()

    t = api()
    if t is None:
        return xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    try:
        con_tmdb(t, accion, int(PARAMS.get("page", 1)))
    except Exception as e:
        log("Error en %s: %s" % (accion, e))
        aviso("No se pudo cargar el catálogo (¿clave de TMDB correcta? ¿hay Internet?)")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


main()
