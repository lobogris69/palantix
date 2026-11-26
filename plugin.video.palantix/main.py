"""Punto de entrada del addon. Kodi lo llama con: sys.argv = [url_base, handle, '?parametros']."""
from hashlib import sha256
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from urllib.parse import parse_qsl, urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from resources.lib import ajustes_serie, avisos_fuentes, perfiles_casa, cuadricula_tv, deportes, disponibilidad, epg, etiquetas, explorar, fuentes_catalogo, listas, preferencias_copia
from resources.lib import actualizar, debrid, historial, inicio, mislistas, novedades, progreso, seguimiento, subtitulos, trakt, tv
from resources.lib import tmdb as tmdb_mod
from resources.lib.providers import Peli
from resources.lib.providers import cine_libre
from resources.lib.providers.stremio import Stremio, motivo_error

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
    """Estado visible en la ficha de una serie en seguimiento."""
    n = mis_novedades().get(str(sid)) or {}
    if str(sid) not in mis_series():
        return ""
    estado = novedades.estado_vista(n)
    if estado == "nuevo":
        pendientes = n["pendientes"]
        return color("● NUEVO · %d pendiente%s" % (pendientes, "" if pendientes == 1 else "s"), VERDE)
    return color(novedades.ESTADOS_VISTA.get(estado, "En seguimiento"), AZUL)


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


def vincular(sid=None):
    sid = sid or PARAMS["s"]
    s = servicio_por_id(sid)
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
    if sid == "trakt" and not s.configurado():
        return xbmcgui.Dialog().ok("Trakt", "En developer.trakt.tv/apps, crea una app Development o usa la de Palantix\n"
                                   "y pon su Client ID en Ajustes → Trakt.")
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


def accion_aviso_fuente(li, ficha):
    li.addContextMenuItems([("Avísame cuando tenga fuente", "RunPlugin(%s)" %
                            url(accion="aviso_fuente", ficha=json.dumps(ficha, ensure_ascii=False)))])


def guardar_aviso_fuente():
    ficha = json.loads(PARAMS["ficha"])
    avisos_fuentes.guardar(PERFIL, ficha)
    aviso("Te avisaremos cuando se confirme una fuente")


def lista_avisos_fuentes():
    items = avisos_fuentes.leer(PERFIL)
    if not items:
        aviso("Activa un aviso desde el menú contextual de una película o capítulo")
    for ficha, disponible in items:
        li = xbmcgui.ListItem("%s · %s" % (ficha["title"], "Fuente confirmada" if disponible else "Por comprobar"))
        li.setProperty("IsPlayable", "true")
        li.addContextMenuItems([("Quitar aviso", "RunPlugin(%s)" % url(accion="quitar_aviso_fuente", id=ficha["id"]))])
        extra = {"tipo": "episodio", "s": ficha["temporada"], "e": ficha["episodio"]} if "episodio" in ficha else {}
        xbmcplugin.addDirectoryItem(HANDLE, url(accion="reproducir", id=ficha["tmdb_id"], titulo=ficha["title"],
                                                original=ficha.get("original_title", ""), elegir=1, **extra), li, False)
    return fin_listado()


def quitar_aviso_fuente():
    avisos_fuentes.quitar(PERFIL, PARAMS["id"])
    xbmc.executebuiltin("Container.Refresh")


def accion_donde_ver(li, tipo, tid):
    li.addContextMenuItems([("Dónde ver", "Container.Update(%s)" %
                            url(accion="donde_ver", tipo=tipo, id=tid))])


def configurar_aviso_plataforma(t):
    tipo = "tv" if PARAMS.get("tipo") == "tv" else "movie"
    titulo = PARAMS.get("titulo") or "Título"
    proveedores = sorted(t.plataformas(tipo), key=lambda p: (p.get("display_priority", 999), p["provider_name"]))
    seleccion = xbmcgui.Dialog().multiselect("Plataformas que usas", [p["provider_name"] for p in proveedores])
    if seleccion:
        ficha = {"tipo": tipo, "tmdb_id": int(PARAMS["id"]), "title": titulo}
        avisos_fuentes.plataformas(PERFIL, ficha, [proveedores[n]["provider_id"] for n in seleccion])
        aviso("Aviso de plataformas guardado")
    return fin_listado()


def lista_avisos_plataforma():
    registros = avisos_fuentes.lista_plataformas(PERFIL)
    if not registros:
        aviso("Crea un aviso desde Dónde ver")
    for clave, ficha, _, resultado in registros:
        destino = url(accion="donde_ver", tipo=ficha["tipo"], id=ficha["tmdb_id"])
        li = xbmcgui.ListItem(ficha["title"] + " · " + (resultado or "Pendiente de disponibilidad"))
        li.addContextMenuItems([("Quitar aviso", "RunPlugin(%s)" %
                                url(accion="quitar_aviso_plataforma", id=clave))])
        xbmcplugin.addDirectoryItem(HANDLE, destino, li, True)
    return fin_listado()


def quitar_aviso_plataforma():
    avisos_fuentes.quitar_plataformas(PERFIL, PARAMS["id"])
    xbmc.executebuiltin("Container.Refresh")


def donde_ver(t):
    tipo = PARAMS.get("tipo", "movie")
    if tipo not in ("movie", "tv"):
        return fin_listado(ok=False)
    tid = int(PARAMS["id"])
    ficha = t.detalle(tid) if tipo == "movie" else t.serie(tid)
    if tipo == "movie":
        titulo = ficha.get("title") or ""
        li = xbmcgui.ListItem("Buscar fuentes configuradas en Kodi")
        li.setProperty("IsPlayable", "true")
        xbmcplugin.addDirectoryItem(HANDLE, url(accion="reproducir", id=tid, titulo=titulo,
                                                original=ficha.get("original_title", ""), elegir=1), li, False)
    else:
        carpeta("Ver temporadas y fuentes en Kodi", url(accion="temporadas", id=tid, titulo=ficha.get("name", "")))
    carpeta("Avísame cuando esté en mis plataformas",
            url(accion="aviso_plataforma", tipo=tipo, id=tid, titulo=ficha.get("title") or ficha.get("name") or ""))
    try:
        datos = t.donde_ver(tipo, tid)
    except (OSError, ValueError):
        aviso("No se pudo consultar la disponibilidad de las plataformas")
        return fin_listado()
    enlace = datos.get("link", "")
    for clave, etiqueta in (("flatrate", "Suscripción"), ("free", "Gratis"), ("ads", "Con anuncios"),
                            ("rent", "Alquiler"), ("buy", "Compra")):
        for proveedor in datos.get(clave, []):
            nombre = proveedor.get("provider_name")
            if nombre:
                carpeta("%s · %s" % (nombre, etiqueta),
                        url(accion="oferta_streaming", nombre=nombre, enlace=enlace))
    return fin_listado()


def oferta_streaming():
    xbmcgui.Dialog().textviewer("Disponibilidad de JustWatch", "%s\n\nConsulta la ficha de disponibilidad en:\n%s" %
                                 (PARAMS.get("nombre", ""), PARAMS.get("enlace", "")))
    return fin_listado()


def accion_historial(li, tipo, tmdb, titulo, original="", anio="", poster="", fondo="", nuevo=False):
    destino = url(accion="valorar_visto", tipo=tipo, id=tmdb, titulo=titulo, original=original or "",
                  anio=anio, poster=poster or "", fondo=fondo or "", nuevo=int(nuevo))
    etiqueta = "Añadir a vistos y valorar" if nuevo else "Valorar o cambiar las estrellas"
    li.addContextMenuItems([(etiqueta, "RunPlugin(%s)" % destino)])


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
                                                original=m.get("original_title", ""), anio=anio, elegir=1,
                                                poster=m.get("poster_path") or "", fondo=m.get("backdrop_path") or "")),
        ("Quitar de Favoritas" if es_fav else "Añadir a Favoritas",
         "RunPlugin(%s)" % url(accion="fav_quitar" if es_fav else "fav_poner",
                               id=m["id"], datos=json.dumps(guardable))),
    ])
    accion_historial(li, "pelicula", m["id"], titulo, m.get("original_title"), anio,
                     m.get("poster_path"), m.get("backdrop_path"), nuevo=True)
    acciones_trakt(li, "movies", m["id"])
    accion_donde_ver(li, "movie", m["id"])
    li.addContextMenuItems([("Visto en un perfil de casa", "RunPlugin(%s)" %
                            url(accion="perfiles_visto", id=m["id"]))])
    accion_aviso_fuente(li, {"id": str(m["id"]), "tmdb_id": m["id"], "title": titulo,
                            "original_title": m.get("original_title") or "", "release_date": anio})
    destino = url(accion="reproducir", id=m["id"], titulo=titulo, original=m.get("original_title", ""),
                  anio=anio, poster=m.get("poster_path") or "", fondo=m.get("backdrop_path") or "")
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
    marca = marca_serie(s["id"])
    if marca:
        li.setLabel("%s  %s" % (li.getLabel(), marca))
    accion_historial(li, "serie", s["id"], titulo, s.get("original_name"), anio,
                     s.get("poster_path"), s.get("backdrop_path"), nuevo=True)
    acciones_trakt(li, "shows", s["id"])
    accion_donde_ver(li, "tv", s["id"])
    li.addContextMenuItems([("Audio y subtítulos de esta serie", "RunPlugin(%s)" %
                            url(accion="ajustes_serie", id=s["id"]))])
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
    creditos = [("%s: %s" % (nombre, it[clave])) for nombre, clave in (
        ("Autor", "autor"), ("Licencia", "licencia"), ("Condiciones", "licencia_url"), ("Ficha original", "ficha_origen")
    ) if it.get(clave)]
    tag.setPlot("\n".join(filter(None, (it["sinopsis"], *creditos))))
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
    carpeta("Hoy para ti", url(accion="hoy_para_ti"))
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
    carpeta("Historial de vistos", url(accion="historial_vistos"), "DefaultInProgressShows.png")
    carpeta("Mis favoritas", url(accion="favoritas"), "DefaultFavourites.png")
    carpeta(cine_libre.TITULO, url(accion="cine_libre"), "DefaultMovies.png")
    carpeta("TV", url(accion="tv"), "DefaultTVShows.png")
    carpeta("TV internacional", url(accion="tv_internacional"), "DefaultTVShows.png")
    carpeta("Mis listas", url(accion="listas"), "DefaultPlaylist.png")
    carpeta("Ajustes", url(accion="ajustes"), "DefaultAddonService.png")
    carpeta("Actualizar Palantix  " + color("(versión %s)" % ADDON.getAddonInfo("version"), GRIS),
            url(accion="actualizar"), "DefaultAddonsUpdates.png")
    xbmcplugin.endOfDirectory(HANDLE)


def hoy_para_ti():
    carpeta("Continuar películas", url(accion="a_medias"))
    carpeta("Series y próximos capítulos", url(accion="seguir"), "DefaultTVShows.png")
    carpeta("Avisos de disponibilidad", url(accion="lista_avisos_fuentes"))
    carpeta("Avisos de plataformas", url(accion="lista_avisos_plataforma"))
    carpeta("Perfiles para elegir juntos", url(accion="perfiles_elegir"))
    carpeta("Ya disponible en tu lista", url(accion="favoritas_disponibles"), "DefaultFavourites.png")
    carpeta("Deportes hoy", url(accion="deportes_hoy"))
    carpeta("Elegid algo para ver", url(accion="elegir_juntos"), "DefaultMovies.png")
    return fin_listado()


def favoritas_disponibles():
    _, proveedores = consulta_fuentes(None)
    confirmadas, pendientes = disponibilidad.filtrar(leer_favoritas(), CACHE, (proveedores, preferencias()))
    if not confirmadas:
        aviso("Comprobando tus favoritas" if pendientes else "Tu lista aún no tiene fuentes confirmadas")
    for ficha in confirmadas:
        destino, li, es_carpeta = ficha_pelicula(ficha)
        xbmcplugin.addDirectoryItem(HANDLE, destino, li, es_carpeta)
    return fin_listado("movies")


def configurar_perfil_elegir(t):
    dialogo = xbmcgui.Dialog()
    nombres = [nombre for nombre, _, _ in perfiles_casa.leer(PERFIL)]
    n = dialogo.select("Perfiles para elegir juntos", ["Crear perfil"] + nombres)
    if n < 0:
        return fin_listado()
    nombre = nombres[n - 1] if n else (dialogo.input("Nombre del perfil") or "").strip()[:24]
    if not nombre:
        return fin_listado()
    generos = t.generos()
    n = dialogo.select("Género favorito", ["Cualquiera"] + [g["name"] for g in generos])
    if n < 0:
        return fin_listado()
    genero = generos[n - 1]["id"] if n else 0
    duraciones = (90, 120, 150, 180)
    n = dialogo.select("Duración máxima", ["Hasta %d min" % d for d in duraciones])
    if n >= 0:
        perfiles_casa.guardar(PERFIL, nombre, genero, duraciones[n])
        aviso("Perfil guardado: " + nombre)
    return fin_listado()


def visto_en_perfil():
    perfiles = perfiles_casa.leer(PERFIL)
    dialogo = xbmcgui.Dialog()
    n = dialogo.select("¿Quién ha visto esta película?", [p[0] for p in perfiles]) if perfiles else -1
    if n >= 0:
        estado = dialogo.select("Estado", ["Marcar como vista", "Marcar como no vista"])
        if estado >= 0:
            perfiles_casa.marcar(PERFIL, perfiles[n][0], int(PARAMS["id"]), estado == 0)
            aviso("Estado guardado para " + perfiles[n][0])


def elegir_juntos(t):
    dialogo = xbmcgui.Dialog()
    perfiles = perfiles_casa.leer(PERFIL)
    if len(perfiles) >= 2:
        primero = dialogo.select("Primer perfil", [p[0] for p in perfiles])
        if primero < 0:
            return fin_listado()
        segundo = dialogo.select("Segundo perfil", [p[0] for p in perfiles if p != perfiles[primero]])
        if segundo < 0:
            return fin_listado()
        otros = [p for p in perfiles if p != perfiles[primero]]
        generos, minutos, vistas = perfiles_casa.criterios(PERFIL, perfiles[primero], otros[segundo])
        return resultados_juntos(t, generos, minutos, vistas)
    return elegir_juntos_manual(t, dialogo)


def elegir_juntos_manual(t, dialogo):
    generos = t.generos()[:12]
    categorias = ["Cualquiera"] + [g["name"] for g in generos]
    elegidos = []
    for persona in (1, 2):
        seleccion = dialogo.select("Persona %d · género" % persona, categorias)
        if seleccion < 0:
            return fin_listado()
        if seleccion:
            elegidos.append(generos[seleccion - 1]["id"])
    duraciones = (90, 120, 180)
    seleccion = dialogo.select("Tiempo que tenéis disponible", ["Hasta %d min" % n for n in duraciones])
    if seleccion < 0:
        return fin_listado()
    return resultados_juntos(t, elegidos, duraciones[seleccion], set())


def resultados_juntos(t, generos, minutos, vistas):
    fichas = [f for f in t.elegir_juntos(generos, minutos).get("results", []) if f["id"] not in vistas]
    _, proveedores = consulta_fuentes(None)
    confirmadas, pendientes = disponibilidad.filtrar(fichas, CACHE, (proveedores, preferencias()))
    for ficha in confirmadas[:3]:
        destino, li, es_carpeta = ficha_pelicula(ficha)
        xbmcplugin.addDirectoryItem(HANDLE, destino, li, es_carpeta)
    if not confirmadas:
        aviso("Comprobando disponibilidad. Vuelve en un momento." if pendientes else "No hay coincidencias con fuente confirmada")
    return fin_listado("movies")


def menu_peliculas():
    carpeta("Tendencias de la semana", url(accion="tendencias"))
    carpeta("Populares", url(accion="populares"))
    carpeta("Novedades en streaming", url(accion="novedades_streaming"))
    carpeta("Mejor valoradas", url(accion="mejor_valoradas"))
    carpeta("Géneros", url(accion="explorar_generos", tipo="movie"))
    carpeta("Por año", url(accion="anios", destino="anio"))
    carpeta("Sagas", url(accion="sagas"))
    carpeta("Buscar película", url(accion="buscar"), "DefaultAddonsSearch.png")
    xbmcplugin.endOfDirectory(HANDLE)


def menu_series():
    carpeta("Series en seguimiento", url(accion="seguir", estado="todos"), "DefaultInProgressShows.png")
    carpeta("Capítulos recientes", url(accion="s_capitulos_recientes"))
    carpeta("Tendencias de la semana", url(accion="s_tendencias"))
    carpeta("Populares", url(accion="s_populares"))
    carpeta("Mejor valoradas", url(accion="s_mejor_valoradas"))
    carpeta("Géneros", url(accion="explorar_generos", tipo="tv"))
    carpeta("Por año", url(accion="anios", destino="s_anio"))
    carpeta("Buscar serie", url(accion="s_buscar"), "DefaultAddonsSearch.png")
    xbmcplugin.endOfDirectory(HANDLE)


def explorar_generos(t):
    tipo = "tv" if PARAMS.get("tipo") == "tv" else "movie"
    generos = t.s_generos() if tipo == "tv" else t.generos()
    carpeta("Todos los géneros", url(accion="explorar", tipo=tipo))
    for genero in generos:
        carpeta(genero["name"], url(accion="explorar", tipo=tipo, gid=genero["id"], genero=genero["name"]))
    return fin_listado()


def explorar_catalogo(t, pagina):
    tipo = "tv" if PARAMS.get("tipo") == "tv" else "movie"
    gid = PARAMS.get("gid", "")
    genero = PARAMS.get("genero") or "Todos los géneros"
    filtros = explorar.filtros(PARAMS)
    comunes = dict(tipo=tipo, gid=gid, genero=genero, **filtros)
    campos = [("orden", "Orden", explorar.ORDENES)]
    if tipo == "movie":
        campos += [("duracion", "Duración", explorar.DURACIONES), ("fuente", "Disponibilidad", explorar.FUENTES)]
    else:
        campos.append(("estado", "Estado", explorar.ESTADOS))
    valores = [opciones[filtros[clave]] for clave, _, opciones in campos]
    carpeta("Filtros · " + " · ".join([genero] + valores),
            url(accion="explorar_filtros", **comunes), "DefaultAddonService.png")
    if filtros != explorar.filtros({}):
        carpeta("Quitar filtros", url(accion="explorar", tipo=tipo, gid=gid, genero=genero))

    try:
        if tipo == "tv" and filtros["estado"] == "seguimiento":
            datos = explorar.seguidas(t, CACHE, mis_series(), gid, filtros["orden"], pagina)
            guardados = False
        else:
            datos, guardados = explorar.cargar(t, CACHE, tipo, explorar.consulta(tipo, gid, filtros, pagina))
    except (OSError, ValueError, sqlite3.Error):
        aviso("No se pudo cargar este género")
        return fin_listado()
    if guardados:
        aviso("Mostrando los últimos resultados guardados")
    filas = datos.get("results", [])
    confirmadas, pendientes = set(), set()
    if tipo == "movie":
        _, proveedores = consulta_fuentes(None)
        resultados, _ = disponibilidad.filtrar(filas, CACHE, (proveedores, preferencias()),
                                               ids_pendientes=pendientes)
        confirmadas = {str(f["id"]) for f in resultados}
        if filtros["fuente"] == "confirmadas":
            filas = resultados
        elif filtros["fuente"] == "pendientes":
            filas = [f for f in filas if str(f["id"]) in pendientes and str(f["id"]) not in confirmadas]
    for ficha in filas:
        _, li, _ = ficha_serie(ficha) if tipo == "tv" else ficha_pelicula(ficha)
        tid = str(ficha["id"])
        if tipo == "movie":
            estado = ("Con fuente confirmada" if tid in confirmadas else
                      "Por comprobar" if tid in pendientes else "Sin fuente confirmada")
            li.setLabel(li.getLabel() + " · " + estado)
        li.setProperty("IsPlayable", "false")
        xbmcplugin.addDirectoryItem(HANDLE, url(accion="explorar_ficha", tipo=tipo, id=tid), li, True)
    if pagina < min(datos.get("total_pages", 1), 500):
        carpeta("Página siguiente", url(accion="explorar", page=pagina + 1, **comunes))
    if not filas:
        aviso("No hay resultados con estos filtros en esta página")
    return fin_listado()


def explorar_filtros():
    tipo = "tv" if PARAMS.get("tipo") == "tv" else "movie"
    campos = [("orden", "Orden", explorar.ORDENES)]
    if tipo == "movie":
        campos += [("duracion", "Duración", explorar.DURACIONES), ("fuente", "Disponibilidad", explorar.FUENTES)]
    else:
        campos.append(("estado", "Estado", explorar.ESTADOS))
    filtros = explorar.filtros(PARAMS)
    dialogo = xbmcgui.Dialog()
    for clave, titulo, opciones in campos:
        claves = list(opciones)
        n = dialogo.select(titulo, list(opciones.values()), preselect=claves.index(filtros[clave]))
        if n < 0:
            return fin_listado()
        filtros[clave] = claves[n]
    destino = url(accion="explorar", tipo=tipo, gid=PARAMS.get("gid", ""),
                  genero=PARAMS.get("genero", ""), **filtros)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    xbmc.executebuiltin("Container.Update(%s,replace)" % destino)


def explorar_ficha(t):
    tipo = "tv" if PARAMS.get("tipo") == "tv" else "movie"
    tid = int(PARAMS["id"])
    datos = t.serie(tid) if tipo == "tv" else t.detalle(tid)
    destino, li, carpeta_ficha = ficha_serie(datos) if tipo == "tv" else ficha_pelicula(datos)
    tag = li.getVideoInfoTag()
    generos = " · ".join(g["name"] for g in datos.get("genres", []))
    duracion = datos.get("runtime") or next(iter(datos.get("episode_run_time") or []), 0)
    siguiente = (mis_novedades().get(str(tid)) or {}).get("siguiente") if tipo == "tv" else None
    detalle = [generos, "%d min" % duracion if duracion else ""]
    if siguiente:
        detalle.append("Siguiente: %dx%02d · %s" % (siguiente["s"], siguiente["e"], siguiente["nombre"]))
    tag.setPlot("\n".join(filter(None, (*detalle, datos.get("overview", "")))))
    li.setLabel("Ver temporadas · " + li.getLabel() if tipo == "tv" else "Reproducir · " + li.getLabel())
    xbmcplugin.addDirectoryItem(HANDLE, destino, li, carpeta_ficha)
    carpeta("Dónde ver", url(accion="donde_ver", tipo=tipo, id=tid))
    return fin_listado("tvshows" if tipo == "tv" else "movies")


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


def fuentes_episodios(sid, datos, capitulos):
    """Encola capítulos emitidos y devuelve los que ya tienen fuente confirmada."""
    if not capitulos or ADDON.getSetting("comprobar_fuentes_episodios") != "true":
        return set(), False

    _, proveedores = consulta_fuentes(None)
    configuracion = (proveedores, preferencias(), "episodios")
    confirmados, pendientes = set(), False
    for i in range(0, len(capitulos), 400):
        fichas = [
            {"id": "%s:%d:%d" % (sid, s, e), "tmdb_id": int(sid), "temporada": s, "episodio": e,
             "title": datos.get("titulo") or "", "original_title": datos.get("original") or "",
             "release_date": str(datos.get("anio") or "")}
            for s, e in capitulos[i:i + 400]
        ]
        visibles, en_cola = disponibilidad.filtrar(fichas, CACHE, configuracion)
        confirmados.update((f["temporada"], f["episodio"]) for f in visibles)
        pendientes = pendientes or en_cola
    return confirmados, pendientes


def seguir_viendo(t):
    """Muestra las series en seguimiento, con filtros por estado desde la sección Series."""
    if t:
        vistos = trakt.Trakt(AJ, log=log, timeout=5).historial_episodios(CACHE) if mis_series() else {}
        novedades.refrescar(PERFIL, t, log=log, vistos_trakt=vistos)
        _CACHE.pop("novedades", None)
    xbmcplugin.setContent(HANDLE, "episodes")
    filtro = PARAMS.get("estado", "")
    ocultar = not filtro and ADDON.getSetting("ocultar_al_dia") != "false"
    nov = mis_novedades()
    if filtro == "todos":
        for estado, etiqueta in novedades.ESTADOS_VISTA.items():
            total = sum(novedades.estado_vista(nov.get(sid) or {}) == estado for sid in mis_series())
            carpeta("%s (%d)" % (etiqueta, total), url(accion="seguir", estado=estado), "DefaultTVShows.png")
    filas = []
    for sid, d in seguimiento.ordenadas(PERFIL):
        n = nov.get(sid) or {}
        estado = novedades.estado_vista(n)
        if filtro in novedades.ESTADOS_VISTA and estado != filtro:
            continue
        prioridad = {"nuevo": 0, "al_dia": 1, "terminada": 2}.get(estado, 3)
        filas.append((prioridad, -d.get("fecha", 0), sid, d, n))
    hay = False
    for _, _, sid, d, n in sorted(filas, key=lambda f: (f[0], f[1])):
        comun = {"id": sid, "titulo": d.get("titulo", ""), "original": d.get("original", ""), "anio": d.get("anio", "")}
        sig = n.get("siguiente")
        if not sig and ocultar:
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
                    if prox.get("s") and prox.get("emitido") else
                    novedades.ESTADOS_VISTA.get(novedades.estado_vista(n), "Por comprobar").lower())
            li = xbmcgui.ListItem("%s  %s" % (d["titulo"], marca_serie(sid)))
            if prox.get("s") and prox.get("emitido"):
                li.setLabel("%s · %s" % (li.getLabel(), cola))
            destino, es_carpeta = url(accion="temporadas", **comun), True
            texto = "Has visto hasta el %sx%02d.\nEstado: %s." % (d["s"], int(d["e"]), cola)
        confirmados, en_cola = fuentes_episodios(sid, d, n.get("episodios_pendientes", []))
        if confirmados:
            distintivo = "%d con fuente" % len(confirmados)
        elif en_cola:
            distintivo = "Comprobando fuentes"
        elif sig and n.get("episodios_pendientes") and ADDON.getSetting("comprobar_fuentes_episodios") == "true":
            distintivo = "Sin fuente confirmada"
        else:
            distintivo = ""
        if distintivo:
            li.setLabel("%s  %s" % (li.getLabel(), color(distintivo, VERDE if confirmados else GRIS)))
            texto = distintivo + "\n" + texto
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
        acciones = [("Ver temporadas", "Container.Update(%s)" % url(accion="temporadas", **comun)),
                    ("Quitar de seguimiento", "RunPlugin(%s)" % url(accion="dejar_seguir", id=sid))]
        if confirmados and sig and (sig["s"], sig["e"]) not in confirmados:
            s_disp, e_disp = min(confirmados)
            reproducible = url(accion="reproducir", tipo="episodio", s=s_disp, e=e_disp,
                              poster=d.get("poster", ""), fondo=d.get("fanart", ""), **comun)
            acciones.insert(0, ("Ver %dx%02d con fuente" % (s_disp, e_disp), "PlayMedia(%s)" % reproducible))
        li.addContextMenuItems(acciones)
        xbmcplugin.addDirectoryItem(HANDLE, destino, li, es_carpeta)
        hay = True
    if not hay and filtro != "todos":
        aviso("No hay series en este estado" if filtro else
              "No hay capítulos pendientes: las series se apuntan solas al ver un capítulo")
    fin_listado("episodes")


def a_medias():
    """Películas sin terminar, con su barra de progreso."""
    xbmcplugin.setContent(HANDLE, "movies")
    pelis = progreso.peliculas(PERFIL)
    candidatos = [dict(d, id=d["tmdb"], title=d["titulo"], original_title=d.get("original"),
                       release_date=str(d.get("anio") or "")) for d in pelis]
    pelis = progreso.con_caratulas(peliculas_disponibles(candidatos), api(obligatoria=False), CACHE)
    for d in pelis:
        etiqueta = "%s (%s)" % (d["titulo"], d["anio"]) if d.get("anio") else d["titulo"]
        li = xbmcgui.ListItem("%s  %s" % (etiqueta, color("%s de %s" % (progreso.hhmmss(d["pos"]), progreso.hhmmss(d["total"])), AZUL)))
        poster = tmdb_mod.TMDB.imagen(d.get("poster")) or tmdb_mod.TMDB.imagen(d.get("fanart"), "w500") or LOGO
        li.setArt({"poster": poster, "thumb": poster, "fanart": tmdb_mod.TMDB.imagen(d.get("fanart"), "w1280")})
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
        [datos for tipo, datos in fichas if tipo == "pelicula"])}
    return [ficha_pelicula(datos) if tipo == "pelicula" else ficha_serie(datos)
            for tipo, datos in fichas if tipo != "pelicula" or str(datos["id"]) in visibles]


def acciones_trakt(li, tipo, tid):
    if trakt.Trakt(AJ, log=log).encendido():
        li.addContextMenuItems([("Pendientes de Trakt", "RunPlugin(%s)" %
                                url(accion="trakt_cambiar_pendiente", tipo=tipo, id=tid))])


def trakt_cambiar_pendiente():
    tipo = PARAMS.get("tipo")
    tk = trakt.Trakt(AJ, log=log)
    if tipo not in ("movies", "shows") or not tk.encendido():
        return
    opciones = ["Añadir a pendientes de Trakt", "Quitar de pendientes de Trakt"]
    elegir = xbmcgui.Dialog().select("Pendientes de Trakt", opciones)
    if elegir < 0:
        return
    try:
        resultado = tk.cambiar_pendiente(tipo, PARAMS["id"], elegir == 0)
        if resultado.get("not_found", {}).get(tipo):
            return aviso("Trakt no encuentra este título")
    except (OSError, ValueError, trakt.TraktError):
        return aviso("No se pudo actualizar la lista de Trakt")
    aviso("Pendientes de Trakt actualizados")
    xbmc.executebuiltin("Container.Refresh")


def menu_trakt():
    carpeta("Progreso de series", url(accion="trakt_progreso"), "DefaultInProgressShows.png")
    carpeta("Películas pendientes", url(accion="trakt_pend", tipo="movies"), "DefaultMovies.png")
    carpeta("Series pendientes", url(accion="trakt_pend", tipo="shows"), "DefaultTVShows.png")
    try:
        for lid, nombre, n in trakt.Trakt(AJ, log=log).listas():
            carpeta("%s  %s" % (nombre, color("(%d)" % n, GRIS)), url(accion="trakt_lista", id=lid))
    except Exception as e:
        aviso(str(e))
    xbmcplugin.endOfDirectory(HANDLE)


def trakt_progreso_series():
    tk = trakt.Trakt(AJ, log=log)
    if not tk.encendido():
        aviso("Vincula y activa Trakt para ver el progreso de tus series")
        return fin_listado(ok=False)
    grupo = PARAMS.get("grupo")
    if not grupo:
        for clave, titulo in (("curso", "En curso"), ("dia", "Al día")):
            carpeta(titulo, url(accion="trakt_progreso", grupo=clave), "DefaultTVShows.png")
        return fin_listado()

    try:
        pagina = max(1, int(PARAMS.get("page", 1)))
        series, hay_mas = tk.progreso_series(pagina)
    except (OSError, ValueError, trakt.TraktError):
        aviso("No se pudo leer el historial de Trakt")
        return fin_listado(ok=False)
    xbmcplugin.setContent(HANDLE, "tvshows")
    mostradas = 0
    incompletas = False
    for serie, estado in series:
        if estado is None:
            incompletas = True
            continue
        emitidos, vistos = estado["aired"], estado["completed"]
        pendientes = max(0, emitidos - vistos)
        if bool(pendientes) != (grupo == "curso"):
            continue
        titulo = serie.get("title") or "Serie"
        tmdb = (serie.get("ids") or {}).get("tmdb")
        prox = estado.get("next_episode") or {}
        temporada, capitulo = prox.get("season"), prox.get("number")
        etiqueta = "%s · %d de %d vistos · %s" % (
            titulo, vistos, emitidos, "%d pendientes" % pendientes if pendientes else "Al día")
        if pendientes and temporada is not None and capitulo is not None:
            etiqueta += " · Siguiente: %dx%02d" % (temporada, capitulo)
            if prox.get("title"):
                etiqueta += " " + prox["title"]
        li = xbmcgui.ListItem(etiqueta)
        li.setArt({"icon": "DefaultTVShows.png"})
        comun = {"id": tmdb, "titulo": titulo, "anio": serie.get("year") or ""}
        if tmdb and pendientes and temporada is not None and capitulo is not None:
            destino = url(accion="reproducir", tipo="episodio", s=temporada, e=capitulo, elegir=1, **comun)
            li.setProperty("IsPlayable", "true")
            li.addContextMenuItems([("Ver temporadas", "Container.Update(%s)" % url(accion="temporadas", **comun))])
            xbmcplugin.addDirectoryItem(HANDLE, destino, li, False)
        elif tmdb:
            xbmcplugin.addDirectoryItem(HANDLE, url(accion="temporadas", **comun), li, True)
        else:
            xbmcplugin.addDirectoryItem(HANDLE, "", li, False)
        mostradas += 1
    if hay_mas:
        carpeta("Página siguiente", url(accion="trakt_progreso", grupo=grupo, page=pagina + 1))
    if incompletas:
        aviso("Trakt no devolvió el progreso de todas las series")
    elif not mostradas:
        aviso("No hay series en esta categoría en esta página")
    return fin_listado()


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
    sid = str(PARAMS["id"])
    seg = mis_series().get(sid) or {}
    vistos = trakt.Trakt(AJ, log=log, timeout=5).historial_episodios(CACHE)
    historial = seguimiento.con_historial_trakt(seg, vistos.get(sid))
    visto_dia = time.strftime("%Y-%m-%d", time.localtime(seg["fecha"])) if seg.get("fecha") else ""
    episodios = temp.get("episodes", [])
    emitidos = [(ep["season_number"], ep["episode_number"]) for ep in episodios
                if ep.get("air_date") and ep["air_date"] <= hoy
                and not seguimiento.esta_visto(historial, ep["season_number"], ep["episode_number"])]
    confirmados, _ = fuentes_episodios(PARAMS["id"], PARAMS, emitidos)
    for ep in episodios:
        emitido = ep.get("air_date") or ""
        n_s, n_e = ep["season_number"], ep["episode_number"]
        visto = seguimiento.esta_visto(historial, n_s, n_e)
        spoiler = ADDON.getSetting("series_sin_destripes") == "true" and not visto
        titulo_episodio = "Episodio %d" % n_e if spoiler else ep.get("name") or ""
        nombre = "%dx%02d. %s" % (n_s, n_e, titulo_episodio)
        if not emitido or emitido > hoy:
            nombre = color("%s (sale el %s)" % (nombre, fecha_es(emitido) or "?"), GRIS)
        elif seg and not visto and emitido > visto_dia:
            nombre = "%s  %s" % (nombre, color("● NUEVO", VERDE))
        if visto:
            nombre += "  " + color("✓ VISTO", VERDE)
        elif (n_s, n_e) in confirmados:
            nombre += "  " + color("Con fuente", VERDE)
        li = xbmcgui.ListItem(nombre)
        li.setArt({"thumb": tmdb_mod.TMDB.imagen(ep.get("still_path"), "w300") if not spoiler else "",
                   "poster": tmdb_mod.TMDB.imagen(temp.get("poster_path"))})
        tag = li.getVideoInfoTag()
        tag.setMediaType("episode")
        tag.setTitle(titulo_episodio)
        tag.setTvShowTitle(serie)
        tag.setSeason(n_s)
        tag.setEpisode(n_e)
        tag.setPlot("" if spoiler else ep.get("overview") or "")
        tag.setFirstAired(emitido)
        if ep.get("runtime"):
            tag.setDuration(int(ep["runtime"]) * 60)
        if visto:
            tag.setPlaycount(1)  # marca de visto
        prog = mi_progreso().get("e:%s:%s:%s" % (PARAMS["id"], n_s, n_e))
        if prog and not visto:
            tag.setResumePoint(float(prog["pos"]), float(prog["total"]))
            li.setLabel(li.getLabel() + " · A medias")
        li.setProperty("IsPlayable", "true")
        destino = url(accion="reproducir", tipo="episodio", id=PARAMS["id"], titulo=serie,
                      original=PARAMS.get("original", ""), anio=PARAMS.get("anio", ""), s=n_s, e=n_e,
                      poster=PARAMS.get("poster", ""), fondo=PARAMS.get("fondo", ""))
        acciones = [("Elegir fuente", "PlayMedia(%s&elegir=1)" % destino)]
        if emitido and emitido <= hoy:
            cambio = "Marcar como no visto" if visto else "Marcar como visto"
            accion = url(accion="marcar_capitulo", id=PARAMS["id"], s=n_s, e=n_e, visto=int(not visto),
                         titulo=serie, original=PARAMS.get("original", ""), anio=PARAMS.get("anio", ""),
                         poster=PARAMS.get("poster", ""), fondo=PARAMS.get("fondo", ""))
            acciones.append((cambio, "RunPlugin(%s)" % accion))
            accion_aviso_fuente(li, {"id": "%s:%d:%d" % (PARAMS["id"], n_s, n_e), "tmdb_id": int(PARAMS["id"]),
                                    "title": serie, "original_title": PARAMS.get("original") or "",
                                    "temporada": n_s, "episodio": n_e})
        li.addContextMenuItems(acciones)
        xbmcplugin.addDirectoryItem(HANDLE, destino, li, False)
    fin_listado("episodes")


def marcar_capitulo():
    meta = {"tipo": "episodio", "tmdb": PARAMS["id"], "s": int(PARAMS["s"]), "e": int(PARAMS["e"]),
            "titulo": PARAMS.get("titulo"), "original": PARAMS.get("original"), "anio": PARAMS.get("anio"),
            "poster": PARAMS.get("poster"), "fanart": PARAMS.get("fondo")}
    visto = PARAMS["visto"] == "1"
    seguimiento.marcar_visto(PERFIL, meta, visto=visto)
    tk = trakt.Trakt(AJ, log=log)
    if tk.encendido():
        try:
            resultado = tk.marcar_visto(meta, visto)
            if any(resultado.get("not_found", {}).values()):
                aviso("Guardado en Palantix. Trakt no encuentra ese capítulo.")
            else:
                try:
                    os.unlink(os.path.join(CACHE, trakt.CACHE_VISTOS))
                except OSError:
                    pass
        except (OSError, ValueError, trakt.TraktError):
            aviso("Guardado en Palantix. Falló la sincronización con Trakt.")
    xbmc.executebuiltin("Container.Refresh")


def historial_vistos():
    tipo = PARAMS.get("tipo")
    if tipo not in historial.TIPOS:
        for clave, titulo in historial.TIPOS.items():
            carpeta(titulo, url(accion="historial_vistos", tipo=clave),
                    "DefaultMovies.png" if clave == "pelicula" else "DefaultTVShows.png")
        return fin_listado()

    serie = tipo == "serie"
    try:
        if serie:
            historial.importar_series(PERFIL, mis_series(), mis_novedades())
        vistos = historial.leer(PERFIL, tipo)
    except (OSError, sqlite3.Error):
        aviso("No se pudo leer el historial de vistos")
        return fin_listado(ok=False)
    contenido = "tvshows" if serie else "movies"
    xbmcplugin.setContent(HANDLE, contenido)
    for ficha in vistos:
        titulo, nota = ficha["titulo"], ficha["nota"]
        anio = ficha["anio"]
        nombre = "%s (%s)" % (titulo, anio) if anio else titulo
        puntuacion = "%s %d/5" % ("★" * nota, nota) if nota else "Sin valorar"
        li = xbmcgui.ListItem("%s · %s" % (nombre, puntuacion))
        li.setArt(_arte({"poster_path": ficha["poster"], "backdrop_path": ficha["fanart"]}))
        tag = li.getVideoInfoTag()
        tag.setTitle(nombre + " · " + puntuacion)
        tag.setMediaType("tvshow" if serie else "movie")
        tag.setPlaycount(1)
        if ficha["fecha"]:
            tag.setPlot("Visto el %s" % time.strftime("%d-%m-%Y", time.localtime(ficha["fecha"])))
        if nota:
            tag.setRating(float(2 * nota), 0, "palantix", True)
        accion_historial(li, tipo, ficha["tmdb"], titulo, ficha["original"], anio,
                         ficha["poster"], ficha["fanart"])
        if not serie:
            li.setProperty("IsPlayable", "true")
        destino = url(accion="temporadas" if serie else "reproducir", id=ficha["tmdb"], titulo=titulo,
                      original=ficha["original"], anio=anio, poster=ficha["poster"], fondo=ficha["fanart"])
        xbmcplugin.addDirectoryItem(HANDLE, destino, li, isFolder=serie)
    if not vistos:
        aviso("Aún no hay títulos en este historial")
    fin_listado()
    if vistos and xbmc.getSkinDir() == "skin.estuary":
        xbmc.executebuiltin("Container.SetViewMode(50)")


def valorar_visto():
    meta = {"tipo": PARAMS.get("tipo"), "tmdb": PARAMS.get("id"), "titulo": PARAMS.get("titulo"),
            "original": PARAMS.get("original"), "anio": PARAMS.get("anio"), "poster": PARAMS.get("poster"),
            "fanart": PARAMS.get("fondo")}
    if meta["tipo"] not in historial.TIPOS or not str(meta["tmdb"]).isdigit():
        return
    nota = historial.preguntar(meta["titulo"])
    nuevo = PARAMS.get("nuevo") == "1"
    if nota is None and not nuevo:
        return
    try:
        historial.registrar(PERFIL, meta, fecha=None if nuevo else 0, nota=nota)
    except (OSError, sqlite3.Error, ValueError):
        return aviso("No se pudo guardar el título en el historial")
    aviso("Valoración guardada" if nota is not None else "Título añadido al historial")
    if not nuevo:
        xbmc.executebuiltin("Container.Refresh")


def favoritas():
    listar({"results": leer_favoritas(), "page": 1, "total_pages": 1}, "favoritas")


def fav_cambiar(poner):
    favs = [f for f in leer_favoritas() if str(f.get("id")) != PARAMS["id"]]
    if poner:
        favs.insert(0, json.loads(PARAMS["datos"]))
    guardar_favoritas(favs)
    aviso("Añadida a Favoritas" if poner else "Quitada de Favoritas")
    xbmc.executebuiltin("Container.Refresh")


def catalogo_cine_libre():
    items = cine_libre.peliculas()
    grupo = PARAMS.get("g")
    if not grupo:
        for nombre in dict.fromkeys(it["grupo"] for it in items):
            carpeta(nombre, url(accion="cine_libre", g=nombre), "DefaultMovies.png")
        return fin_listado()
    fichas = [ficha_lista(it) for it in items if it["grupo"] == grupo]
    xbmcplugin.setContent(HANDLE, "movies")
    xbmcplugin.addDirectoryItems(HANDLE, fichas, len(fichas))
    fin_listado("movies")


def entrada_deporte(titulo, enlace, poster=""):
    li = xbmcgui.ListItem(titulo)
    li.setArt({"thumb": poster or LOGO, "fanart": FONDO})
    li.setProperty("IsPlayable", "true")
    xbmcplugin.addDirectoryItem(HANDLE, destino_canal(enlace), li)


def destino_canal(enlace):
    """Abre Horus directamente y evita resolver un plugin desde otro plugin."""
    horus = deportes.ruta_canal_ekhorus(enlace) or deportes.ruta_horus(enlace)
    if horus and complemento_ace_stream():
        return horus
    return url(accion="deportes_play", u=enlace)


def menu_deportes():
    carpeta("Hoy", url(accion="deportes_hoy"))
    carpeta("Eventos en directo", url(accion="deportes_eventos", modo="directo"))
    carpeta("Próximos eventos", url(accion="deportes_eventos", modo="proximos"))
    carpeta("Detener reproducción", url(accion="deportes_detener"))
    carpeta("Canales en directo", url(accion="deportes_canales"), "DefaultTVShows.png")
    carpeta("Guía TV", url(accion="deportes_epg"), "DefaultTVShows.png")
    carpeta("Cuadrícula de Palantix", url(accion="deportes_guia_propia"), "DefaultTVShows.png")
    if xbmc.getCondVisibility("PVR.HasTVChannels | System.AddonIsEnabled(pvr.iptvsimple)"):
        carpeta("Cuadrícula de canales de Kodi", url(accion="deportes_cuadricula"), "DefaultTVShows.png")
    reproductor = complemento_ace_stream()
    if reproductor and reproductor.getAddonInfo("name").casefold() == "ekhorus":
        carpeta("Canales de EKHorus", deportes.ruta_catalogo_ekhorus(), "DefaultTVShows.png")
    carpeta("Mis fuentes", url(accion="deportes_fuentes"), "DefaultPlaylist.png")
    return fin_listado()


def guia_cuadricula_kodi():
    if xbmc.getCondVisibility("PVR.HasTVChannels"):
        return abrir_ventana_kodi("TVGuide")

    fin_listado(ok=False)
    xbmcgui.Dialog().ok("Cuadrícula de canales de Kodi",
                        "Kodi todavía no tiene canales de TV cargados. Comprueba que tu cliente PVR "
                        "tenga canales en la sección TV de Kodi. En el menú de Palantix también puedes abrir "
                        "Cuadrícula de Palantix, que usa la guía propia del complemento.")


def canales_deportes():
    for titulo, enlace in deportes.CANALES:
        if enlace:
            entrada_deporte(titulo, enlace)
    return fin_listado()


def listas_canales_tv():
    items = []
    reproductor = complemento_ace_stream()
    if reproductor and reproductor.getAddonInfo("name").casefold() == "ekhorus":
        ruta = xbmcvfs.translatePath("special://profile/addon_data/script.module.horus/tv/ekhorus.m3u")
        try:
            items.extend(listas.parsear(listas.descargar(ruta), canales=True))
        except (OSError, ValueError, TypeError, AttributeError):
            log("La lista exportada de EKHorus no está disponible")
    for fuente in mislistas.leer(perfil_deportes()):
        if deportes.ace_id(fuente["origen"]):
            items.append({"titulo": fuente["nombre"], "url": fuente["origen"], "grupo": "Mis canales", "poster": ""})
        elif deportes.es_web(fuente["origen"]):
            try:
                cargados = listas.cargar(fuente["origen"], CACHE, min(300, ttl_listas()), canales=True)
                items.extend(dict(item, grupo=fuente["nombre"]) if item["grupo"] == "Sin grupo" else item
                             for item in cargados)
            except (OSError, ValueError, TypeError, AttributeError):
                log("Una lista de TV configurada no está disponible")
    return [item for item in items if not item.get("inicio")]


def datos_guia_deportes(hora):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        guia = pool.submit(epg.cargar, CACHE, hora)
        canales_tv = listas_canales_tv()
        try:
            datos = guia.result()
        except (OSError, EOFError, ValueError, epg.ElementTree.ParseError):
            datos = {"nombres": {}, "programas": {}}
    canales, _ = tv.preparar(canales_tv, datos)
    return canales, datos["programas"]


def tv_internacional():
    datos = epg.leer_cache(CACHE) or {"nombres": {}}
    _, grupos = tv.preparar(listas_canales_tv(), datos)
    grupo = PARAMS.get("grupo")
    if grupo is None:
        for nombre in sorted(grupos, key=str.casefold):
            carpeta("%s (%d)" % (nombre, len(grupos[nombre])), url(accion="tv_internacional", grupo=nombre),
                    "DefaultTVShows.png")
        if not grupos:
            carpeta("Mis fuentes de TV", url(accion="deportes_fuentes"), "DefaultPlaylist.png")
            aviso("Añade una lista de canales internacionales en Mis fuentes de TV")
    else:
        for item in sorted(grupos.get(grupo, []), key=lambda item: item["titulo"].casefold()):
            entrada_deporte(item["titulo"], item["url"], item["poster"])
    return fin_listado()


def guia_deportes():
    hora = time.time()
    canales, programas = datos_guia_deportes(hora)
    for cid, (nombre, enlace) in canales.items():
        actual, siguiente = epg.ahora_y_despues(programas.get(cid, []), hora)
        partes = [nombre]
        for etiqueta, programa in (("Ahora", actual), ("Después", siguiente)):
            if programa:
                inicio = datetime.fromtimestamp(programa[0]).strftime("%H:%M")
                partes.append("%s %s: %s" % (etiqueta, inicio, programa[2]))
        if not actual and not siguiente:
            partes.append("Sin programación disponible")
        if not enlace:
            partes.append("Sin señal directa")
            xbmcplugin.addDirectoryItem(HANDLE, "", xbmcgui.ListItem(" · ".join(partes)))
        else:
            entrada_deporte(" · ".join(partes), enlace)
    return fin_listado()


def guia_cuadricula_palantix():
    hora = time.time()
    canales, programas = datos_guia_deportes(hora)
    if HANDLE >= 0:
        fin_listado(ok=False)
    opciones = cuadricula_tv.mostrar(ADDON, canales, programas, hora,
                                    ADDON.getSetting("deportes_sin_resultados") != "false", seleccionar_programa)
    if opciones:
        xbmc.executebuiltin("ActivateWindow(Videos,%s,return)" % url(accion="deportes"))


def seleccionar_programa(canal, enlace, inicio, fin, titulo):
    if not titulo:
        if enlace:
            xbmc.executebuiltin("PlayMedia(%s)" % destino_canal(enlace))
            return True
        xbmcgui.Dialog().ok(canal, "Sin señal configurada")
        return False
    horario = "%s–%s" % (datetime.fromtimestamp(inicio).strftime("%H:%M"),
                         datetime.fromtimestamp(fin).strftime("%H:%M"))
    detalle = "%s · %s · %s" % (canal, horario, titulo)
    ahora = time.time()
    if inicio > ahora:
        if xbmcgui.Dialog().yesno(detalle, "¿Quieres un recordatorio cuando empiece?"):
            programar_recordatorio(datetime.fromtimestamp(inicio).astimezone())
    elif enlace and inicio <= ahora < fin:
        if xbmcgui.Dialog().yesno(detalle, "¿Abrir el canal en directo?"):
            xbmc.executebuiltin("PlayMedia(%s)" % destino_canal(enlace))
            return True
    else:
        xbmcgui.Dialog().ok(detalle, "Emisión pasada" if fin <= ahora else "Sin señal configurada")
    return False


def perfil_deportes():
    return os.path.join(PERFIL, "deportes")


def fuentes_deportes():
    carpeta("Añadir lista M3U o JSON", url(accion="deportes_anadir", tipo="lista"), "DefaultAddSource.png")
    carpeta("Añadir enlace Ace Stream", url(accion="deportes_anadir", tipo="ace"), "DefaultAddSource.png")
    reproductor = complemento_ace_stream()
    nombre = reproductor.getAddonInfo("name") if reproductor else "Ace Stream"
    carpeta("Configurar " + nombre, url(accion="deportes_horus"), "DefaultAddonService.png")
    for fuente in mislistas.leer(perfil_deportes()):
        origen = fuente["origen"]
        li = xbmcgui.ListItem(fuente["nombre"])
        li.addContextMenuItems([("Quitar fuente", "RunPlugin(%s)" % url(accion="deportes_quitar", u=origen))])
        if deportes.ace_id(origen):
            li.setProperty("IsPlayable", "true")
            xbmcplugin.addDirectoryItem(HANDLE, destino_canal(origen), li)
        else:
            xbmcplugin.addDirectoryItem(HANDLE, url(accion="deportes_lista", u=origen), li, isFolder=True)
    return fin_listado()


def anadir_fuente_deportes():
    es_ace = PARAMS.get("tipo") == "ace"
    dialogo = xbmcgui.Dialog()
    origen = (dialogo.input("Enlace o código Ace Stream" if es_ace else "URL de la lista M3U o JSON") or "").strip()
    if not origen:
        return
    if es_ace:
        cid = deportes.ace_id(origen)
        if not cid:
            return aviso("Introduce un enlace Ace Stream o un código de 40 caracteres")
        origen = "acestream://" + cid
    elif not deportes.es_web(origen):
        return aviso("Introduce una dirección http o https")
    sugerido = "Ace Stream" if es_ace else mislistas.nombre_por_defecto(origen)
    nombre = dialogo.input("Nombre de la fuente", sugerido) or sugerido
    if not mislistas.anadir(perfil_deportes(), nombre, origen):
        return aviso("Esa fuente ya está añadida")
    xbmc.executebuiltin("Container.Refresh")


def quitar_fuente_deportes():
    for i, fuente in enumerate(mislistas.leer(perfil_deportes())):
        if fuente["origen"] == PARAMS.get("u"):
            if xbmcgui.Dialog().yesno("Deportes", "¿Quitar «%s»?" % fuente["nombre"]):
                mislistas.quitar(perfil_deportes(), i)
                xbmc.executebuiltin("Container.Refresh")
            return


def listar_deportes(hoy=False, modo=""):
    fuentes = [f for f in mislistas.leer(perfil_deportes()) if deportes.es_web(f["origen"])]
    if not (hoy or modo):
        fuentes = [f for f in fuentes if f["origen"] == PARAMS.get("u")]
    eventos = []
    vistos = set()
    ahora = datetime.now().astimezone()
    fecha = ahora.date()
    for fuente in fuentes:
        try:
            items = listas.cargar(fuente["origen"], CACHE, min(300, ttl_listas()), eventos=True)
        except (OSError, ValueError, TypeError, AttributeError):
            aviso("No se pudo leer la fuente «%s»" % fuente["nombre"])
            continue
        for item in items:
            enlace = item["url"]
            inicio = deportes.inicio_evento(item["inicio"])
            if enlace and not (deportes.ace_id(enlace) or deportes.es_web(enlace)):
                enlace = ""
            if not enlace and not inicio:
                continue
            item["url"] = enlace
            fin = deportes.inicio_evento(item["fin"])
            if hoy and (inicio is None or inicio.date() != fecha):
                continue
            if modo == "directo" and not (inicio and fin and inicio <= ahora < fin):
                continue
            if modo == "proximos" and not (inicio and inicio > ahora):
                continue
            clave = (item["titulo"], deportes.ace_id(enlace) or enlace, inicio)
            if clave not in vistos:
                vistos.add(clave)
                eventos.append((inicio, item))
    for inicio, item in sorted(eventos, key=lambda evento: evento[0].timestamp() if evento[0] else float("inf")):
        ocultar = ADDON.getSetting("deportes_sin_resultados") != "false"
        titulo = "Evento deportivo" if ocultar and item["resultado_en_titulo"] else item["titulo"]
        if inicio:
            formato = "%H:%M" if hoy else "%d/%m %H:%M"
            titulo = "%s · %s" % (inicio.strftime(formato), titulo)
        if item["grupo"] != "Sin grupo":
            titulo += " · " + item["grupo"]
        if item["canal"]:
            titulo += " · " + item["canal"]
        if not item["url"]:
            titulo += " · Sin señal configurada"
        if inicio and inicio > ahora:
            carpeta(titulo, url(accion="deportes_recordatorio", inicio=inicio.isoformat()))
        elif item["url"]:
            entrada_deporte(titulo, item["url"], item["poster"])
        else:
            xbmcplugin.addDirectoryItem(HANDLE, "", xbmcgui.ListItem(titulo), False)
    if not eventos:
        aviso("No hay eventos para este horario" if hoy or modo else "La lista no contiene enlaces compatibles")
    return fin_listado()


def recordatorio_deporte():
    inicio = deportes.inicio_evento(PARAMS.get("inicio"))
    if not inicio:
        return fin_listado()
    segundos = int((inicio - datetime.now().astimezone()).total_seconds())
    if segundos <= 0:
        aviso("El evento ya ha comenzado")
    elif xbmcgui.Dialog().yesno("Deportes", "¿Quieres que Kodi te avise cuando empiece el evento?"):
        programar_recordatorio(inicio)
    return fin_listado()


def programar_recordatorio(inicio):
    segundos = max(1, int((inicio - datetime.now().astimezone()).total_seconds()))
    minutos, resto = divmod(segundos, 60)
    xbmc.executebuiltin("AlarmClock(PalantixDeporte%d,Notification(Palantix,Empieza tu evento deportivo,6000),%d:%02d,silent)" %
                        (inicio.timestamp(), minutos, resto))
    aviso("Recordatorio programado mientras Kodi esté abierto")


def detener_deportes():
    xbmc.executebuiltin("PlayerControl(Stop)")
    return fin_listado()


def complemento_ace_stream(avisar=False):
    if xbmc.getCondVisibility("System.AddonIsEnabled(%s)" % deportes.HORUS):
        try:
            return xbmcaddon.Addon(deportes.HORUS)
        except RuntimeError:
            pass
    if avisar:
        xbmcgui.Dialog().ok("Ace Stream", "Instala y activa Horus o EKHorus en Kodi y configura el motor Ace Stream "
                            "para tu dispositivo. Después puedes gestionar tus enlaces en TV → Opciones de TV → Mis fuentes.")
    return None


def configurar_horus():
    reproductor = complemento_ace_stream(avisar=True)
    if reproductor:
        reproductor.openSettings()


def reproducir_deporte():
    enlace = PARAMS.get("u", "")
    horus = deportes.ruta_canal_ekhorus(enlace) or deportes.ruta_horus(enlace)
    if horus:
        ruta = horus if complemento_ace_stream(avisar=True) else ""
    else:
        ruta = enlace if deportes.es_web(enlace) else ""
    xbmcplugin.setResolvedUrl(HANDLE, bool(ruta), xbmcgui.ListItem(path=ruta))


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
IDIOMAS_PRIORIDAD = fuentes_catalogo.IDIOMAS_PRIORIDAD
ORDENES_FUENTES = ("Idioma primero", "Calidad primero")


def configurar_serie():
    dialogo = xbmcgui.Dialog()
    audio = dialogo.select("Audio de la serie", ["Preferencia general", "Castellano", "Latino", "Versión original"])
    if audio < 0:
        return
    subs = dialogo.select("Subtítulos de la serie", ["Preferencia general", "Desactivados", "Español", "Inglés"])
    if subs < 0:
        return
    try:
        ajustes_serie.guardar(PERFIL, PARAMS["id"], ajustes_serie.AUDIOS[audio], ajustes_serie.SUBTITULOS[subs])
        aviso("Preferencias de la serie guardadas")
    except (OSError, sqlite3.Error):
        aviso("No se pudieron guardar las preferencias de la serie")


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
    return fuentes_catalogo.preferencias(ADDON.getSetting)


def consulta_fuentes(t, fallo=lambda proveedor: None):
    origenes = origenes_listas() if ADDON.getSetting("prov_listas") != "false" else []
    return fuentes_catalogo.consulta(t, ADDON.getSetting, origenes, CACHE, log, fallo)


def peliculas_disponibles(peliculas):
    if not peliculas or ADDON.getSetting("solo_peliculas_con_fuentes") != "true":
        return peliculas

    _, proveedores = consulta_fuentes(None)
    visibles, pendientes = disponibilidad.filtrar(peliculas, CACHE, (proveedores, preferencias()))
    if not visibles:
        if pendientes:
            aviso("Comprobando fuentes en segundo plano. Vuelve a abrir esta lista en un momento.")
        else:
            aviso("No se encontraron fuentes para las películas de esta página")
    return visibles


def comprobar_manifiestos():
    lineas = []
    for n in range(1, 4):
        origen = ADDON.getSetting("stremio_%d" % n).strip()
        estado = "Sin configurar"
        if origen:
            try:
                _, datos = Stremio(origen, n, cache=CACHE).leer_manifiesto()
                recursos = datos["resources"]
                admite = any(r == "stream" or (isinstance(r, dict) and r.get("name") == "stream")
                             for r in recursos)
                estado = "Manifiesto accesible" if admite else "Manifiesto sin recurso de reproducción"
            except (OSError, ValueError, TypeError, sqlite3.Error) as error:
                estado = motivo_error(error)
        lineas.append("Fuente %d · %s" % (n, estado))
    xbmcgui.Dialog().ok("Fuentes de Stremio", "\n".join(lineas))


def estado_indice():
    _, proveedores = consulta_fuentes(None)
    pref = preferencias()
    lineas = []
    for titulo, config in (("Películas", (proveedores, pref)), ("Capítulos", (proveedores, pref, "episodios"))):
        confirmados, cola, ultima = disponibilidad.resumen(CACHE, config)
        fecha = time.strftime("%d/%m/%Y %H:%M", time.localtime(ultima)) if ultima else "sin comprobaciones"
        lineas.append("%s · %d con fuente · %d por comprobar\nÚltima revisión: %s" %
                      (titulo, confirmados, cola, fecha))
    xbmcgui.Dialog().ok("Estado de la comprobación de fuentes", "\n\n".join(lineas))


def abrir_ventana_kodi(ventana):
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    xbmc.executebuiltin("ActivateWindow(%s)" % ventana)


def informe_palantix():
    tk, ad = servicio_por_id("trakt"), servicio_por_id("ad")
    lineas = ["Palantix " + ADDON.getAddonInfo("version"),
              "Catálogo TMDB: " + ("configurado" if clave_tmdb() else "sin configurar"),
              "Trakt: " + ("vinculado" if tk.vinculado() else "sin vincular"),
              "AllDebrid: " + ("vinculado" if ad.vinculado() else "sin vincular"),
              "Stremio: " + ("activo" if ADDON.getSetting("prov_stremio") == "true" else "desactivado"),
              "EKHorus/Horus: " + ("activo" if complemento_ace_stream() else "desactivado o ausente")]
    if ADDON.getSetting("prov_stremio") == "true":
        for n in range(1, 4):
            origen = ADDON.getSetting("stremio_%d" % n).strip()
            if origen:
                try:
                    Stremio(origen, n, cache=CACHE).leer_manifiesto()
                    estado = "manifiesto accesible"
                except (OSError, ValueError, TypeError, sqlite3.Error) as error:
                    estado = motivo_error(error)
                lineas.append("Fuente %d · %s" % (n, estado))
    ultimo = xbmcgui.Window(10000).getProperty("palantix.ultimo_error")
    if ultimo in ("Error de Kodi al continuar el vídeo", "Error de Kodi al iniciar el vídeo"):
        lineas.append("Último error de reproducción: " + ultimo)
    texto = "\n".join(lineas)
    dialogo = xbmcgui.Dialog()
    dialogo.textviewer("Informe de Palantix", texto)
    if dialogo.yesno("Informe de Palantix", "¿Quieres guardar el informe para compartirlo?"):
        destino = dialogo.browseSingle(3, "Carpeta para el informe de Palantix", "files")
        if destino:
            try:
                ruta = os.path.join(xbmcvfs.translatePath(destino), "palantix-informe-%s.txt" % time.strftime("%Y%m%d-%H%M%S"))
                with open(ruta, "x", encoding="utf-8") as f:
                    f.write(texto)
                aviso("Informe guardado")
            except OSError:
                aviso("No se pudo guardar el informe")


def asistente_configuracion():
    addon = xbmcaddon.Addon()
    tk, ad = servicio_por_id("trakt"), servicio_por_id("ad")
    def estado(servicio):
        if not servicio.vinculado():
            return "Sin vincular"
        return "Vinculado" if servicio.encendido() else "Desactivado"

    opciones = [
        ("TMDB · " + ("Clave guardada" if clave_tmdb() else "Sin configurar"), comprobar_tmdb),
        ("Trakt · " + estado(tk), lambda: comprobar_cuenta_asistente("trakt")),
        ("AllDebrid · " + estado(ad), lambda: comprobar_cuenta_asistente("ad")),
        ("Stremio · " + ("Activo" if addon.getSetting("prov_stremio") == "true" else "Desactivado"),
         comprobar_manifiestos),
        ("Estado de la comprobación de fuentes", estado_indice),
        ("Probar vídeo directo · Sintel (Blender)", probar_video_asistente),
        ("Copiar preferencias a otro Kodi", copiar_preferencias),
        ("Ordenar prioridad de idiomas", configurar_prioridad_idiomas),
        ("Generar informe sin claves ni URLs", informe_palantix),
    ]
    seleccion = xbmcgui.Dialog().select("Comprobar mi configuración", [nombre for nombre, _ in opciones])
    if seleccion >= 0:
        opciones[seleccion][1]()


def comprobar_cuenta_asistente(sid):
    servicio = servicio_por_id(sid)
    if not servicio.vinculado():
        return vincular(sid)
    try:
        servicio.cuenta()
    except Exception:
        return xbmcgui.Dialog().ok(servicio.nombre, "No se pudo comprobar la cuenta. Revisa la conexión o vuelve a vincular.")
    estado = "Servicio activo." if servicio.encendido() else "Activa el servicio en Ajustes para usarlo."
    xbmcgui.Dialog().ok(servicio.nombre, "La cuenta responde. " + estado)


def probar_video_asistente():
    video = "https://download.blender.org/durian/movies/Sintel.2010.1080p.mkv"
    xbmc.Player().play(video, xbmcgui.ListItem("Sintel · Prueba de reproducción"))


def preferencias_desde_movil():
    import tempfile
    from resources.lib import preferencias_movil

    class Ventana(xbmcgui.WindowDialog):
        cerrada = False

        def onAction(self, accion):
            if accion.getId() in (9, 10, 92):
                self.cerrada = True
                self.close()

    dialogo = xbmcgui.Dialog()
    try:
        ip = xbmc.getInfoLabel("Network.IPAddress")
        sesion, enlace = preferencias_movil.servidor(ip, preferencias_copia.exportar(ADDON.getSetting))
    except (OSError, ValueError):
        return dialogo.ok("Palantix", "Conecta Kodi y el móvil a la misma red local.")
    ventana = Ventana()
    with sesion, tempfile.TemporaryDirectory() as temporal:
        controles = [xbmcgui.ControlLabel(110, 65, 1050, 50, "Abre en el móvil durante 90 segundos", font="font27"),
                     xbmcgui.ControlLabel(110, 120, 1050, 60, enlace, font="font13")]
        try:
            import pyqrcode
            imagen = os.path.join(temporal, "preferencias.png")
            pyqrcode.create(enlace).png(imagen, scale=7)
            controles.append(xbmcgui.ControlImage(110, 195, 360, 360, imagen))
        except (ImportError, OSError):
            pass
        ventana.addControls(controles)
        ventana.show()
        try:
            limite = time.monotonic() + 90
            monitor = xbmc.Monitor()
            while not ventana.cerrada and sesion.datos is None and time.monotonic() < limite and not monitor.abortRequested():
                sesion.handle_request()
        finally:
            ventana.close()
    if sesion.datos:
        aplicar_preferencias(dialogo, sesion.datos)


def copiar_preferencias():
    dialogo = xbmcgui.Dialog()
    accion = dialogo.select("Preferencias de Palantix", ["Exportar preferencias", "Importar preferencias", "Conectar móvil en la red local"])
    if accion == 2:
        return preferencias_desde_movil()
    if accion not in (0, 1):
        return
    if accion == 0:
        destino = dialogo.browseSingle(3, "Carpeta para guardar las preferencias", "files")
        if not destino:
            return
        nombre = "palantix-preferencias-%s.json" % time.strftime("%Y%m%d-%H%M%S")
        try:
            with open(os.path.join(xbmcvfs.translatePath(destino), nombre), "x", encoding="utf-8") as f:
                f.write(preferencias_copia.exportar(ADDON.getSetting))
        except OSError:
            return dialogo.ok("Palantix", "No se pudo guardar el archivo. Elige una carpeta local con permiso de escritura.")
        return dialogo.ok("Palantix", "Preferencias guardadas en " + nombre)

    origen = dialogo.browseSingle(1, "Elige un archivo de preferencias", "files", ".json")
    if not origen:
        return
    try:
        with open(xbmcvfs.translatePath(origen), "rb") as f:
            datos = preferencias_copia.importar(f.read(preferencias_copia.MAX_BYTES + 1).decode("utf-8"))
    except (OSError, ValueError):
        return dialogo.ok("Palantix", "No se pudo leer un archivo válido de preferencias.")
    aplicar_preferencias(dialogo, datos)


def aplicar_preferencias(dialogo, datos):
    if dialogo.yesno("Palantix", "¿Aplicar las preferencias de idioma, calidad y menús?"):
        anteriores = {clave: ADDON.getSetting(clave) for clave in datos}
        try:
            for clave, valor in datos.items():
                ADDON.setSetting(clave, valor)
        except (RuntimeError, ValueError):
            for clave, valor in anteriores.items():
                ADDON.setSetting(clave, valor)
            return dialogo.ok("Palantix", "No se pudo aplicar la copia de preferencias.")
        dialogo.ok("Palantix", "Preferencias importadas. Vuelve a abrir Palantix para ver los cambios.")


def no_reproducir():
    xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())


def elegir_fuentes(ordenadas, titulo, automatico):
    """Reutiliza la búsqueda al descartar un enlace que no se puede resolver."""
    restantes = list(ordenadas)
    while restantes:
        seleccion = 0
        if not automatico:
            opciones = []
            for fuente, analisis in restantes:
                resumen = etiquetas.resumen_fuente(fuente, analisis)
                extras = " ".join(analisis["extras"])
                detalle = " · ".join(dict.fromkeys(filter(None, (fuente.proveedor, extras, fuente.etiqueta))))
                opciones.append(xbmcgui.ListItem(label=resumen, label2=detalle))
            seleccion = xbmcgui.Dialog().select(titulo, opciones, useDetails=True)
            if seleccion < 0 or seleccion >= len(restantes):
                return
        fuente, analisis = restantes.pop(seleccion)
        yield fuente, analisis, not restantes


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
    if PARAMS.get("reintentar"):
        offset = PARAMS.get("desde", "0")
        desde = min(int(offset), 86400) if offset.isascii() and offset.isdecimal() and len(offset) <= 5 else 0
    elif previo and PARAMS.get("continuar"):
        desde = previo["pos"]
    elif previo and not PARAMS.get("desde_cero"):
        n = xbmcgui.Dialog().contextmenu(["Reanudar desde %s" % progreso.hhmmss(previo["pos"]), "Desde el principio"])
        if n < 0:
            return no_reproducir()
        desde = previo["pos"] if n == 0 else 0
    barra = xbmcgui.DialogProgress()
    barra.create("Palantix", "Buscando fuentes para «%s»..." % nombre)
    fallos = []
    try:
        buscar, proveedores = consulta_fuentes(api(obligatoria=False), fallos.append)
        fuentes = buscar(peli)
    finally:
        barra.close()

    pref = preferencias()
    if peli.tmdb_id:
        disponible = bool(etiquetas.ordenar(fuentes, **pref))
        if disponible or (not fallos and (not proveedores[2] or peli.imdb_id)):
            ident = "%d:%d:%d" % (peli.tmdb_id, peli.temporada, peli.episodio) if episodio else peli.tmdb_id
            config = (proveedores, pref, "episodios") if episodio else (proveedores, pref)
            try:
                disponibilidad.registrar(CACHE, config, ident, disponible)
            except (OSError, sqlite3.Error):
                log("No se pudo guardar la comprobación de fuentes")
    subs_serie = ""
    if episodio:
        try:
            audio, subs_serie = ajustes_serie.leer(PERFIL, peli.tmdb_id)
            if audio:
                pref["idioma"] = audio
                pref["prioridad_idiomas"] = (audio,)
        except (OSError, sqlite3.Error):
            log("No se pudieron recuperar las preferencias de la serie")
    excluidas = PARAMS.get("reintentar", "").split(",")[:12]
    ordenadas = [(f, a) for f, a in etiquetas.ordenar(fuentes, **pref)
                 if sha256(f.url.encode()).hexdigest()[:16] not in excluidas]
    if not ordenadas:
        if fallos:
            aviso("Búsqueda incompleta: " + ", ".join(sorted(set(fallos))))
        else:
            aviso("No hay fuentes para «%s»%s" % (nombre, " en tu idioma" if fuentes else ""))
        return no_reproducir()

    automatico = ADDON.getSetting("autoplay") == "true" and not PARAMS.get("elegir")
    titulo_selector = "Elige fuente · " + ORDENES_FUENTES[pref["calidad_primero"]]
    if fallos:
        aviso("Búsqueda incompleta: " + ", ".join(sorted(set(fallos))))
    for f, a, ultima in elegir_fuentes(ordenadas, titulo_selector, automatico):
        def elegir(videos):
            if f.archivo:
                coincidencias = [n for n, v in enumerate(videos)
                                 if v[0].replace("\\", "/").rsplit("/", 1)[-1] == f.archivo]
                if len(coincidencias) == 1:
                    return coincidencias[0]
            return _elegir_fichero(videos)

        ruta = resolver(f.url, avisar=ultima or not automatico, elegir=elegir, privada=f.privada)
        if not ruta:
            if not f.privada:
                log("Fuente descartada: %s" % f.etiqueta)
            continue
        if f.cabeceras:  # convención de Kodi para mandar cabeceras HTTP
            ruta += "|" + urlencode(f.cabeceras)
        if automatico and len(ordenadas) > 1:
            aviso("%s %s" % (etiquetas.texto_etiquetas(a), f.proveedor))
        if not f.privada:
            log("Reproduciendo %s" % f.url)
        prioridad_audio = pref["prioridad_idiomas"] or (pref["idioma"],)
        li = xbmcgui.ListItem(path=ruta)
        if desde:
            li.setProperty("StartOffset", str(int(desde)))
        sub = poner_subtitulos(peli, a, pref, subs_serie)
        if sub:
            li.setSubtitles([sub])
        intentos = [h for h in excluidas if len(h) == 16] + [sha256(f.url.encode()).hexdigest()[:16]]
        reintento = ""
        if len(ordenadas) > 1 and len(intentos) <= 12:
            reintento = url(accion="reproducir", tipo=peli.tipo, id=peli.tmdb_id, s=peli.temporada,
                            e=peli.episodio, titulo=peli.titulo, original=peli.titulo_original,
                            anio=peli.anio, elegir=1, desde=int(desde), reintentar=",".join(intentos),
                            poster=PARAMS.get("poster", ""), fondo=PARAMS.get("fondo", ""))
        avisar_al_servicio(peli, prioridad_audio, reintento)
        return xbmcplugin.setResolvedUrl(HANDLE, True, li)
    no_reproducir()


def poner_subtitulos(peli, analisis, pref, preferencia_serie=""):
    """Descarga el mejor subtítulo en tu idioma si el audio de la fuente no lo es (o siempre, según Ajustes)."""
    clave = ADDON.getSetting("os_apikey").strip()
    modo = (0 if preferencia_serie == "off" else 2) if preferencia_serie else ajuste_int("subs_modo", 1)
    idiomas = preferencia_serie if preferencia_serie in ("es", "en") else ADDON.getSetting("subs_idiomas") or "es"
    if not clave or not subtitulos.hace_falta(modo, analisis["idiomas"], pref["idioma"]):
        return None
    cliente = subtitulos.OpenSubtitles(clave, ADDON.getSetting("os_usuario"), ADDON.getSetting("os_clave"), log=log)
    try:
        lista = cliente.buscar(peli.tmdb_id, idiomas,
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
        aviso("Subtítulos añadidos")
        return ruta
    except subtitulos.SubError as e:
        aviso(str(e))
    except Exception as e:
        log("Subtítulos: %s" % e)
    return None


def avisar_al_servicio(peli, prioridad_audio=(), reintento=""):
    """Deja en la ventana principal qué va a sonar y cuál es el siguiente capítulo (lo lee service.py)."""
    ventana = xbmcgui.Window(10000)
    meta = {"tipo": peli.tipo, "tmdb": peli.tmdb_id, "s": peli.temporada, "e": peli.episodio,
            "titulo": peli.titulo, "original": peli.titulo_original, "anio": peli.anio,
            "poster": PARAMS.get("poster", ""), "fanart": PARAMS.get("fondo", ""),
            "prioridad_audio": prioridad_audio, "reintento": reintento, "inicio_solicitado": time.time()}
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
    "cine_libre": catalogo_cine_libre,
    "tv": guia_cuadricula_palantix,
    "tv_internacional": tv_internacional,
    "deportes": menu_deportes,
    "deportes_canales": canales_deportes,
    "deportes_epg": guia_deportes,
    "deportes_guia_propia": guia_cuadricula_palantix,
    "deportes_fuentes": fuentes_deportes,
    "deportes_anadir": anadir_fuente_deportes,
    "deportes_quitar": quitar_fuente_deportes,
    "deportes_horus": configurar_horus,
    "deportes_cuadricula": guia_cuadricula_kodi,
    "perfiles_kodi": lambda: abrir_ventana_kodi("profiles"),
    "deportes_hoy": lambda: listar_deportes(hoy=True),
    "deportes_eventos": lambda: listar_deportes(modo=PARAMS.get("modo")),
    "deportes_recordatorio": recordatorio_deporte,
    "deportes_detener": detener_deportes,
    "deportes_lista": listar_deportes,
    "deportes_play": reproducir_deporte,
    "anios": lambda: anios(PARAMS["destino"]),
    "dejar_seguir": dejar_seguir,
    "marcar_capitulo": marcar_capitulo,
    "historial_vistos": historial_vistos,
    "valorar_visto": valorar_visto,
    "a_medias": a_medias,
    "trakt": menu_trakt,
    "ajustes_serie": configurar_serie,
    "hoy_para_ti": hoy_para_ti,
    "perfiles_visto": visto_en_perfil,
    "lista_avisos_plataforma": lista_avisos_plataforma,
    "quitar_aviso_plataforma": quitar_aviso_plataforma,
    "aviso_fuente": guardar_aviso_fuente,
    "lista_avisos_fuentes": lista_avisos_fuentes,
    "quitar_aviso_fuente": quitar_aviso_fuente,
    "explorar_filtros": explorar_filtros,
    "favoritas_disponibles": favoritas_disponibles,
    "oferta_streaming": oferta_streaming,
    "trakt_progreso": trakt_progreso_series,
    "trakt_cambiar_pendiente": trakt_cambiar_pendiente,
    "quitar_medias": quitar_medias,
    "trailer": trailer,
    "ajustes": ADDON.openSettings,
    "asistente_configuracion": asistente_configuracion,
    "estado_indice": estado_indice,
    "copiar_preferencias": copiar_preferencias,
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
    if accion in ("tendencias", "populares", "en_cines", "mejor_valoradas", "novedades_streaming"):
        listar(vp(getattr(t, accion), page), accion)
    elif accion in ("s_tendencias", "s_populares", "s_mejor_valoradas", "s_capitulos_recientes"):
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
    elif accion == "elegir_juntos":
        elegir_juntos(t)
    elif accion == "explorar_generos":
        explorar_generos(t)
    elif accion == "explorar":
        explorar_catalogo(t, page)
    elif accion == "explorar_ficha":
        explorar_ficha(t)
    elif accion == "aviso_plataforma":
        configurar_aviso_plataforma(t)
    elif accion == "perfiles_elegir":
        configurar_perfil_elegir(t)
    elif accion == "donde_ver":
        donde_ver(t)
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
                     filtrar_peliculas=peliculas_disponibles)
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
