"""Pantalla de inicio estilo plataforma (cartel grande + filas de carátulas + menú lateral).

`datos_filas()` es lógica pura (se prueba sin Kodi); `abrir()` crea la ventana con palantix-inicio.xml.
Cada elemento lleva en propiedades qué hacer al pulsarlo: tipo «reproducir» (PlayMedia) o «carpeta» (abrir).
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

from . import novedades, progreso, seguimiento
from .tmdb import TMDB
from .providers.cine_libre import TITULO as TITULO_CINE_LIBRE

FILAS = [
    (101, "Continuar viendo"),
    (102, "Nuevos capítulos de tus series"),
    (103, "Tendencias en películas"),
    (104, "Series del momento"),
    (105, "Estrenos en cines"),
    (106, "Las mejor valoradas"),
    (107, "Mi lista"),
    (108, "Novedades en streaming"),
    (111, "Capítulos recientes"),
]
TODAS = list(range(101, 112))  # ids de las filas del XML (101-102 anchas, 103-111 carátulas)

# Pestañas: (fila, título, (qué pedir a TMDB, argumento))
PESTANAS = {
    "peliculas": [(103, "Tendencias en películas", ("lista", "tendencias")), (104, "Populares", ("lista", "populares")),
                  (105, "Estrenos en cines", ("lista", "en_cines")), (106, "Las mejor valoradas", ("lista", "mejor_valoradas")),
                  (107, "Acción", ("genero", 28)), (108, "Comedia", ("genero", 35)), (109, "Terror", ("genero", 27)),
                  (110, "Ciencia ficción", ("genero", 878))],
    "series": [(103, "Series del momento", ("lista", "s_tendencias")), (104, "Series populares", ("lista", "s_populares")),
               (105, "Las mejor valoradas", ("lista", "s_mejor_valoradas")), (106, "Drama", ("s_genero", 18)),
               (107, "Comedia", ("s_genero", 35)), (108, "Crimen", ("s_genero", 80)), (109, "Animación", ("s_genero", 16)),
               (110, "Documentales", ("s_genero", 99)),
               (111, "Capítulos recientes", ("lista", "s_capitulos_recientes"))],
}
NOMBRE_PESTANA = {"inicio": "", "peliculas": "Películas", "series": "Series"}
CACHE_SEG = 3600


def _img(ruta, tam="w500"):
    return TMDB.imagen(ruta, tam) if ruta else ""


def _anio(fecha):
    return (fecha or "")[:4]


def _info(*partes):
    return "   ·   ".join(p for p in partes if p)


def _nota(v):
    try:
        return "★ %.1f" % float(v) if float(v) > 0 else ""
    except (TypeError, ValueError):
        return ""


def elemento_pelicula(m, url):
    return {"label": m.get("title") or m.get("original_title") or "?", "plot": m.get("overview", ""),
            "poster": _img(m.get("poster_path")), "fanart": _img(m.get("backdrop_path"), "w1280"),
            "thumb": _img(m.get("backdrop_path"), "w780"),
            "info": _info(_anio(m.get("release_date")), _nota(m.get("vote_average")), "Película"),
            "tipo": "reproducir", "url": url(accion="reproducir", id=m["id"], titulo=m.get("title", ""),
                                             original=m.get("original_title", ""), anio=_anio(m.get("release_date")))}


def elemento_serie(s, url):
    return {"label": s.get("name") or s.get("original_name") or "?", "plot": s.get("overview", ""),
            "poster": _img(s.get("poster_path")), "fanart": _img(s.get("backdrop_path"), "w1280"),
            "thumb": _img(s.get("backdrop_path"), "w780"),
            "info": _info(_anio(s.get("first_air_date")), _nota(s.get("vote_average")), "Serie"),
            "tipo": "carpeta", "url": url(accion="temporadas", id=s["id"], titulo=s.get("name", ""),
                                          original=s.get("original_name", ""), anio=_anio(s.get("first_air_date")))}


def _tmdb_cache(perfil, t):
    """Listados de TMDB para el inicio, en paralelo y guardados 1 hora (abre al instante)."""
    ruta = os.path.join(perfil, "inicio_cache.json")
    region = t.region
    try:
        with open(ruta, encoding="utf-8") as f:
            c = json.load(f)
        if (time.time() - c.get("fecha", 0) < CACHE_SEG and c.get("idioma") == t.idioma
                and c.get("region") == region and "capitulos_recientes" in c["datos"]):
            return c["datos"]
    except (OSError, ValueError, KeyError):
        pass
    tareas = {"tendencias": t.tendencias, "series": t.s_tendencias, "cines": t.en_cines,
              "valoradas": t.mejor_valoradas, "streaming": t.novedades_streaming,
              "capitulos_recientes": t.s_capitulos_recientes}
    with ThreadPoolExecutor(max_workers=len(tareas)) as pool:
        futuros = {k: pool.submit(f, 1) for k, f in tareas.items()}
    datos = {}
    for k, fut in futuros.items():
        try:
            datos[k] = fut.result().get("results", [])[:20]
        except Exception:
            datos[k] = []
    if any(datos.values()):
        os.makedirs(perfil, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"fecha": time.time(), "idioma": t.idioma, "region": region, "datos": datos}, f)
    return datos


def _pedir(t, que):
    tipo, arg = que
    if tipo == "lista":
        return getattr(t, arg)(1)
    if tipo == "genero":
        return t.por_genero(arg, 1)
    return t.s_por_genero(arg, 1)


def datos_pestana(perfil, t, url, pestana, filtrar_peliculas=lambda pelis: pelis):
    """{fila: elementos} de la pestaña Películas o Series (en paralelo y guardado 1 hora)."""
    filas = PESTANAS[pestana]
    ruta = os.path.join(perfil, "inicio_%s.json" % pestana)
    crudo = None
    try:
        with open(ruta, encoding="utf-8") as f:
            c = json.load(f)
        if time.time() - c.get("fecha", 0) < CACHE_SEG and c.get("idioma") == t.idioma:
            cache = {int(k): v for k, v in c["datos"].items()}
            if all(fid in cache for fid, _, _ in filas):
                crudo = cache
    except (OSError, ValueError, KeyError):
        pass
    if crudo is None:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futuros = {fid: pool.submit(_pedir, t, que) for fid, _, que in filas}
        crudo = {}
        for fid, fut in futuros.items():
            try:
                crudo[fid] = fut.result().get("results", [])[:20]
            except Exception:
                crudo[fid] = []
        if any(crudo.values()):
            os.makedirs(perfil, exist_ok=True)
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump({"fecha": time.time(), "idioma": t.idioma, "datos": crudo}, f)
    if pestana == "peliculas":
        visibles = {str(m["id"]) for m in filtrar_peliculas([m for fila in crudo.values() for m in fila])}
        crudo = {fid: [m for m in fila if str(m["id"]) in visibles] for fid, fila in crudo.items()}
    hacer = elemento_pelicula if pestana == "peliculas" else elemento_serie
    return {fid: [hacer(x, url) for x in crudo.get(fid, [])] for fid, _, _ in filas}


def titulos(pestana):
    if pestana == "inicio":
        return dict(FILAS)
    return {fid: titulo for fid, titulo, _ in PESTANAS[pestana]}


def datos_filas(perfil, t, url, favoritas=(), filtrar_peliculas=lambda pelis: pelis):
    """{id_fila: [elementos]} listos para pintar."""
    filas = {fid: [] for fid, _ in FILAS}
    nov = novedades.leer(perfil)

    # 101 Continuar viendo: películas a medias + siguiente capítulo de las series empezadas
    a_medias = progreso.peliculas(perfil)[:10]
    tm = _tmdb_cache(perfil, t) if t else {}
    pelis = [m for grupo in ("tendencias", "cines", "valoradas", "streaming") for m in tm.get(grupo, [])]
    pelis.extend(favoritas)
    pelis.extend(dict(id=d["tmdb"], title=d["titulo"], original_title=d.get("original"),
                      release_date=str(d.get("anio") or "")) for d in a_medias)
    visibles = {str(m["id"]) for m in filtrar_peliculas(pelis)}
    for d in (d for d in a_medias if str(d["tmdb"]) in visibles):
        quedan = int((d["total"] - d["pos"]) // 60)
        filas[101].append({
            "label": d["titulo"], "label2": "%s · quedan %d min" % (d["titulo"], quedan),
            "poster": _img(d.get("poster")), "fanart": _img(d.get("fanart"), "w1280"), "thumb": _img(d.get("fanart"), "w780"),
            "plot": "Te quedaste en el %s." % progreso.hhmmss(d["pos"]),
            "info": _info(str(d.get("anio") or ""), "Película", "%d %%" % (100 * d["pos"] // max(1, d["total"]))),
            "resume": (d["pos"], d["total"]), "tipo": "reproducir",
            "url": url(accion="reproducir", id=d["tmdb"], titulo=d["titulo"], original=d.get("original", ""),
                       anio=d.get("anio", ""), poster=d.get("poster", ""), fondo=d.get("fanart", ""))})
    for sid, d in seguimiento.ordenadas(perfil):
        n = nov.get(sid) or {}
        sig = n.get("siguiente")
        if not sig:
            continue
        e = {"label": d["titulo"], "label2": "%s · %dx%02d" % (d["titulo"], sig["s"], sig["e"]),
             "poster": _img(d.get("poster")), "fanart": _img(d.get("fanart"), "w1280"),
             "thumb": _img(sig.get("still"), "w780") or _img(d.get("fanart"), "w780"),
             "plot": "[B]%dx%02d · %s[/B][CR]%s" % (sig["s"], sig["e"], sig["nombre"], sig.get("sinopsis", "")),
             "info": _info("Serie", "%d capítulo%s pendiente%s" % (n["pendientes"], "" if n["pendientes"] == 1 else "s",
                                                                 "" if n["pendientes"] == 1 else "s")),
             "destacado": "● NUEVO CAPÍTULO" if n.get("nuevo") else "",
             "nuevo": "1" if n.get("nuevo") else "", "tipo": "reproducir",
             "url": url(accion="reproducir", tipo="episodio", id=sid, titulo=d["titulo"], original=d.get("original", ""),
                        anio=d.get("anio", ""), s=sig["s"], e=sig["e"], poster=d.get("poster", ""), fondo=d.get("fanart", ""))}
        filas[102 if n.get("nuevo") else 101].append(e)

    # 103-106 catálogo de TMDB
    if t:
        filas[103] = [elemento_pelicula(m, url) for m in tm.get("tendencias", []) if str(m["id"]) in visibles]
        filas[104] = [elemento_serie(s, url) for s in tm.get("series", [])]
        filas[105] = [elemento_pelicula(m, url) for m in tm.get("cines", []) if str(m["id"]) in visibles]
        filas[106] = [elemento_pelicula(m, url) for m in tm.get("valoradas", []) if str(m["id"]) in visibles]

    # 107 Mi lista (favoritas)
    filas[107] = [elemento_pelicula(m, url) for m in favoritas if str(m["id"]) in visibles]
    filas[108] = [elemento_pelicula(m, url) for m in tm.get("streaming", []) if str(m["id"]) in visibles]
    filas[111] = [elemento_serie(serie, url) for serie in tm.get("capitulos_recientes", [])]
    return filas


def menu(url, con_trakt=False):
    m = [("Inicio", "", "pestana", "inicio"),
         ("Buscar", "DefaultAddonsSearch.png", "carpeta", url(accion="buscar")),
         ("Películas", "DefaultMovies.png", "pestana", "peliculas"),
         ("Series", "DefaultTVShows.png", "pestana", "series"),
         ("Mis series", "DefaultInProgressShows.png", "carpeta", url(accion="seguir")),
         ("Mi lista", "DefaultFavourites.png", "carpeta", url(accion="favoritas")),
         (TITULO_CINE_LIBRE, "DefaultMovies.png", "carpeta", url(accion="cine_libre")),
         ("Mis listas", "DefaultPlaylist.png", "carpeta", url(accion="listas"))]
    if con_trakt:
        m.append(("Trakt", "DefaultAddonService.png", "carpeta", url(accion="trakt")))
    m += [("Ajustes", "DefaultAddonService.png", "ajustes", ""),
          ("Actualizar", "DefaultAddonsUpdates.png", "carpeta", url(accion="actualizar")),
          ("Menú clásico", "DefaultFolder.png", "carpeta", url(accion="clasico")),
          ("Salir", "DefaultFolderBack.png", "salir", "")]
    return m


def abrir(addon, perfil, t, url, favoritas=(), con_trakt=False, log=print,
          filtrar_peliculas=lambda pelis: pelis):
    import xbmc
    import xbmcgui

    logo = addon.getAddonInfo("icon")

    def li(e):
        item = xbmcgui.ListItem(e["label"], e.get("label2", ""))
        item.setArt({"poster": e.get("poster", ""), "fanart": e.get("fanart", ""), "thumb": e.get("thumb", ""),
                     "icon": e.get("icon", "")})
        tag = item.getVideoInfoTag()
        tag.setPlot(e.get("plot", ""))
        if e.get("resume"):
            tag.setResumePoint(float(e["resume"][0]), float(e["resume"][1]))
        for k in ("info", "destacado", "nuevo", "tipo", "url"):
            item.setProperty(k, e.get(k, ""))
        return item

    class Inicio(xbmcgui.WindowXML):
        def onInit(self):
            self.setProperty("logo", logo)
            self.setProperty("version", addon.getAddonInfo("version"))
            self.setProperty("fondo_palantix", addon.getAddonInfo("fanart"))
            if getattr(self, "_listo", False):
                return
            self._listo = True
            for fid, titulo in FILAS:
                self.setProperty("fila%d" % fid, titulo)
            m = self.getControl(200)
            for nombre, icono, tipo, destino in menu(url, con_trakt):
                it = xbmcgui.ListItem(nombre)
                it.setArt({"icon": icono or logo})
                it.setProperty("tipo", tipo)
                it.setProperty("url", destino)
                m.addItem(it)
            self.cargar("inicio")

        def cargar(self, pestana):
            """Rellena las filas con la pestaña pedida (Inicio, Películas o Series) sin salir de la pantalla."""
            self.pestana = pestana
            self.setProperty("pestana", NOMBRE_PESTANA[pestana])
            for fid in TODAS:
                self.getControl(fid).reset()
                self.clearProperty("fila%d" % fid)
            self.setProperty("estado", "Cargando...")
            try:
                if pestana == "inicio":
                    filas = datos_filas(perfil, t, url, favoritas, filtrar_peliculas)
                elif t:
                    filas = datos_pestana(perfil, t, url, pestana, filtrar_peliculas)
                else:
                    filas = {}
            except Exception as e:
                log("Pestaña %s: %s" % (pestana, e))
                filas = {}
            self.clearProperty("estado")
            primera = None
            for fid, titulo in sorted(titulos(pestana).items()):
                elementos = filas.get(fid, [])
                if elementos:
                    self.setProperty("fila%d" % fid, titulo)
                    self.getControl(fid).addItems([li(e) for e in elementos])
                    primera = primera or fid
            if primera:
                self.setFocusId(primera)
            else:
                self.setProperty("estado", "No hay títulos para mostrar" if t else
                                 "Pon tu clave de TMDB en Ajustes para ver el catálogo")
                self.setFocusId(200)

        def onAction(self, accion):
            # Atrás: desde Películas o Series vuelve al Inicio; desde el Inicio, cierra Palantix
            if accion.getId() in (10, 92):
                if getattr(self, "pestana", "inicio") != "inicio":
                    return self.cargar("inicio")
                return self.close()

        def onClick(self, control_id):
            item = self.getControl(control_id).getSelectedItem()
            if not item:
                return
            tipo, destino = item.getProperty("tipo"), item.getProperty("url")
            if tipo == "pestana":
                self.cargar(destino)
            elif tipo == "salir":  # cerrar Palantix y volver a la pantalla principal de Kodi
                self.close()
                xbmc.executebuiltin("ActivateWindow(Home)")
            elif tipo == "ajustes":
                addon.openSettings()
            elif tipo == "reproducir" or "accion=actualizar" in destino:
                xbmc.executebuiltin("PlayMedia(%s)" % destino if tipo == "reproducir" else "RunPlugin(%s)" % destino)
            elif destino:
                xbmc.executebuiltin("ActivateWindow(Videos,%s,return)" % destino)

    ventana = Inicio("palantix-inicio.xml", addon.getAddonInfo("path"), "default", "1080i")
    ventana.doModal()
    del ventana
