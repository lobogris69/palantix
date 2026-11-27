"""Pantalla de inicio estilo plataforma (cartel grande + filas de carátulas + menú lateral).

`datos_filas()` es lógica pura (se prueba sin Kodi); `abrir()` crea la ventana con palantix-inicio.xml.
Cada elemento lleva en propiedades qué hacer al pulsarlo: tipo «reproducir» (PlayMedia) o «carpeta» (abrir).
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qsl

from . import avisos_fuentes, explorar, menu_visual, novedades, progreso, seguimiento
from .tmdb import TMDB
from .explorar import GEN_DESTACADOS
from .providers.cine_libre import TITULO as TITULO_CINE_LIBRE

FILAS = [
    (101, "Continuar viendo"),
    (102, "Nuevos capítulos de tus series"),
    (103, "Tendencias en películas"),
    (104, "Series del momento"),
    (106, "Las mejor valoradas"),
    (107, "Mi lista"),
    (108, "Novedades en streaming"),
    (109, "Avisos listos para ver"),
    (111, "Capítulos recientes"),
]
FILA_ORDEN, FILA_ACCIONES = 112, 113
TODAS = [FILA_ORDEN, FILA_ACCIONES, *range(100, 112)]

# Pestañas: (fila, título, (qué pedir a TMDB, argumento))
PESTANAS = {
    "peliculas": [(103, "Tendencias en películas", ("lista", "tendencias")), (104, "Populares", ("lista", "populares")),
                  (106, "Las mejor valoradas", ("lista", "mejor_valoradas")),
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
                                             original=m.get("original_title", ""), anio=_anio(m.get("release_date")),
                                             poster=m.get("poster_path") or "", fondo=m.get("backdrop_path") or "")}


def elemento_serie(s, url, seguidas=(), nov=None):
    sid = str(s["id"])
    datos = (nov or {}).get(sid) or {}
    estado = novedades.estado_vista(datos) if sid in seguidas else ""
    marca = novedades.ESTADOS_VISTA.get(estado, "En seguimiento" if sid in seguidas else "")
    nombre = s.get("name") or s.get("original_name") or "?"
    return {"destacado": marca, "nuevo": "1" if estado == "nuevo" else "",
            "seguida": marca if estado != "nuevo" else "", "label": nombre,
            "label2": _info(nombre, marca), "plot": s.get("overview", ""),
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
    tareas = {"tendencias": t.tendencias, "series": t.s_tendencias,
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
    if pestana == "series":
        seguidas = seguimiento.leer(perfil)
        nov = novedades.leer(perfil)
        resultado = {fid: [elemento_serie(x, url, seguidas, nov) for x in crudo.get(fid, [])] for fid, _, _ in filas}
        orden = {estado: n for n, estado in enumerate(novedades.ESTADOS_VISTA)}
        recientes = sorted(seguidas.items(), key=lambda par: (
            orden.get(novedades.estado_vista(nov.get(par[0]) or {}), len(orden)), -par[1].get("fecha", 0)))
        resultado[101] = [
            elemento_serie({"id": sid, "name": d.get("titulo"), "original_name": d.get("original"),
                            "first_air_date": str(d.get("anio") or ""), "poster_path": d.get("poster"),
                            "backdrop_path": d.get("fanart")}, url, seguidas, nov)
            for sid, d in recientes
        ]
        for tarjeta in resultado[101]:
            tarjeta["thumb"] = tarjeta["thumb"] or tarjeta["poster"]
        return resultado
    hacer = elemento_pelicula
    return {fid: [hacer(x, url) for x in crudo.get(fid, [])] for fid, _, _ in filas}


def titulos(pestana):
    if pestana == "inicio":
        return dict(FILAS)
    nombres = {100: "Explorar géneros", **{fid: titulo for fid, titulo, _ in PESTANAS[pestana]}}
    if pestana == "series":
        nombres[101] = "Series en seguimiento"
    return nombres


def accesos_generos(pestana, url, logo):
    tipo = "tv" if pestana == "series" else "movie"
    opciones = [{"label": titulo, "label2": titulo, "thumb": logo, "tipo": "genero",
                 "url": url(accion="explorar", tipo=tipo, gid=gid, genero=titulo)}
                for gid, titulo in GEN_DESTACADOS[tipo]]
    opciones.append({"label": "Todos los géneros", "label2": "Todos los géneros", "thumb": logo,
                     "tipo": "carpeta", "url": url(accion="explorar_generos", tipo=tipo)})
    etiqueta = "Buscar series" if tipo == "tv" else "Buscar películas"
    opciones.insert(0, {"label": etiqueta, "label2": etiqueta, "thumb": logo, "tipo": "carpeta",
                        "url": url(accion="s_buscar" if tipo == "tv" else "buscar")})
    return opciones


def pestanas_orden(opciones, orden, tipo, destino):
    return [{"label": etiqueta, "tipo": tipo, "url": destino(clave), "activa": "1" if clave == orden else ""}
            for clave, etiqueta in opciones.items()]


def tarjetas_exploracion(resultados, tipo, url, seguidas, nov):
    tarjetas = []
    for ficha in resultados.filas:
        if tipo == "tv":
            tarjeta = elemento_serie(ficha, url, seguidas, nov)
        else:
            tarjeta = elemento_pelicula(ficha, url)
            tarjeta["info"] = _info(tarjeta["info"], resultados.estado_de(ficha["id"]))
            if str(ficha["id"]) in resultados.confirmadas:
                tarjeta["seguida"] = "Con fuente"
        tarjeta.update(tipo="carpeta", url=url(accion="explorar_ficha", tipo=tipo, id=ficha["id"]),
                       thumb=tarjeta["thumb"] or tarjeta["poster"], exploracion=True)
        tarjetas.append(tarjeta)
    return tarjetas


def datos_filas(perfil, t, url, favoritas=(), filtrar_peliculas=lambda pelis: pelis,
                ocultar_destripes=False, mostrar_catalogo=True):
    """{id_fila: [elementos]} listos para pintar."""
    filas = {fid: [] for fid, _ in FILAS}
    nov = novedades.leer(perfil)
    seguidas = seguimiento.leer(perfil)

    # 101 Continuar viendo: películas a medias + siguiente capítulo de las series empezadas
    a_medias = progreso.peliculas(perfil)[:10]
    tm = _tmdb_cache(perfil, t) if t and mostrar_catalogo else {}
    pelis = [m for grupo in ("tendencias", "valoradas", "streaming") for m in tm.get(grupo, [])]
    pelis.extend(favoritas)
    pelis.extend(dict(id=d["tmdb"], title=d["titulo"], original_title=d.get("original"),
                      release_date=str(d.get("anio") or "")) for d in a_medias)
    visibles = {str(m["id"]) for m in filtrar_peliculas(pelis)}
    a_medias = progreso.con_caratulas([d for d in a_medias if str(d["tmdb"]) in visibles], t, os.path.join(perfil, "cache"))
    for d in a_medias:
        quedan = int((d["total"] - d["pos"]) // 60)
        filas[101].append({
            "label": d["titulo"], "label2": "%s · quedan %d min" % (d["titulo"], quedan),
            "poster": _img(d.get("poster")), "fanart": _img(d.get("fanart"), "w1280"),
            "thumb": _img(d.get("fanart"), "w780") or _img(d.get("poster")),
            "plot": "Te quedaste en el %s." % progreso.hhmmss(d["pos"]),
            "info": _info(str(d.get("anio") or ""), "Película", "%d %%" % (100 * d["pos"] // max(1, d["total"]))),
            "resume": (d["pos"], d["total"]), "destacado": "A MEDIAS", "a_medias": "1", "tipo": "reproducir",
            "url": url(accion="reproducir", id=d["tmdb"], titulo=d["titulo"], original=d.get("original", ""), continuar=1,
                       anio=d.get("anio", ""), poster=d.get("poster", ""), fondo=d.get("fanart", ""))})
    for sid, d in seguimiento.ordenadas(perfil):
        n = nov.get(sid) or {}
        sig = n.get("siguiente")
        if not sig:
            continue
        anterior = " · Pendiente anterior" if sig.get("pendiente_anterior") else ""
        e = {"label": d["titulo"], "label2": "%s · %dx%02d" % (d["titulo"], sig["s"], sig["e"]),
             "poster": _img(d.get("poster")), "fanart": _img(d.get("fanart"), "w1280"),
             "thumb": _img(sig.get("still"), "w780") or _img(d.get("fanart"), "w780"),
             "plot": "[B]%dx%02d · %s[/B][CR]%s" % (sig["s"], sig["e"], sig["nombre"], sig.get("sinopsis", "")),
             "info": _info("Serie" + anterior, "%d capítulo%s pendiente%s" % (n["pendientes"], "" if n["pendientes"] == 1 else "s",
                                                                 "" if n["pendientes"] == 1 else "s")),
             "destacado": "● NUEVO CAPÍTULO" if n.get("nuevo") else "",
             "nuevo": "1" if n.get("nuevo") else "", "tipo": "reproducir",
             "url": url(accion="reproducir", tipo="episodio", id=sid, titulo=d["titulo"], original=d.get("original", ""),
                        anio=d.get("anio", ""), s=sig["s"], e=sig["e"], capitulo=sig["nombre"],
                        poster=d.get("poster", ""), fondo=d.get("fanart", ""))}
        if ocultar_destripes:
            e["thumb"] = _img(d.get("fanart"), "w780")
            e["plot"] = "%dx%02d" % (sig["s"], sig["e"])
        filas[102 if n.get("nuevo") else 101].append(e)

    # 103-106 catálogo de TMDB
    if t:
        filas[103] = [elemento_pelicula(m, url) for m in tm.get("tendencias", []) if str(m["id"]) in visibles]
        filas[104] = [elemento_serie(s, url, seguidas, nov) for s in tm.get("series", [])]
        filas[106] = [elemento_pelicula(m, url) for m in tm.get("valoradas", []) if str(m["id"]) in visibles]

    # 107 Mi lista (favoritas)
    filas[107] = [elemento_pelicula(m, url) for m in favoritas if str(m["id"]) in visibles]
    filas[108] = [elemento_pelicula(m, url) for m in tm.get("streaming", []) if str(m["id"]) in visibles]
    for ficha, confirmado in avisos_fuentes.leer(perfil):
        if not confirmado:
            continue
        extra = {"tipo": "episodio", "s": ficha["temporada"], "e": ficha["episodio"]} if "episodio" in ficha else {}
        titulo = ficha["title"]
        etiqueta = titulo + (" · %dx%02d" % (extra["s"], extra["e"]) if extra else "")
        filas[109].append({"label": etiqueta, "label2": etiqueta, "info": "Fuente confirmada", "tipo": "reproducir",
                           "url": url(accion="reproducir", id=ficha["tmdb_id"], titulo=titulo,
                                      original=ficha.get("original_title", ""), elegir=1, **extra)})
    filas[111] = [elemento_serie(serie, url, seguidas, nov) for serie in tm.get("capitulos_recientes", [])]
    return filas


def menu(url, con_trakt=False, con_radio=True):
    m = [("Inicio", "", "pestana", "inicio"),
         ("Hoy para ti", "DefaultInProgressShows.png", "carpeta", url(accion="hoy_para_ti")),
         ("Buscar", "DefaultAddonsSearch.png", "carpeta", url(accion="buscar")),
         ("Películas", "DefaultMovies.png", "pestana", "peliculas"),
         ("Series", "DefaultTVShows.png", "pestana", "series"),
         ("Mis series", "DefaultInProgressShows.png", "carpeta", url(accion="seguir", estado="todos")),
         ("Historial de vistos", "DefaultInProgressShows.png", "carpeta", url(accion="historial_vistos")),
         ("Mi lista", "DefaultFavourites.png", "carpeta", url(accion="favoritas")),
         (TITULO_CINE_LIBRE, "DefaultMovies.png", "carpeta", url(accion="cine_libre")),
         ("TV", "DefaultTVShows.png", "dialogo", url(accion="tv")),
         ("TV internacional", "DefaultTVShows.png", "carpeta", url(accion="tv_internacional")),
         ("Mis listas", "DefaultPlaylist.png", "carpeta", url(accion="listas"))]
    if con_radio:
        m.insert(-1, ("Radio", "DefaultMusicSongs.png", "carpeta", url(accion="radio_tdt")))
    if con_trakt:
        m.append(("Trakt", "DefaultAddonService.png", "carpeta", url(accion="trakt")))
    m += [("Ajustes", "DefaultAddonService.png", "ajustes", ""),
          ("Actualizar", "DefaultAddonsUpdates.png", "carpeta", url(accion="actualizar")),
          ("Menú clásico", "DefaultFolder.png", "carpeta", url(accion="clasico")),
          ("Salir", "DefaultFolderBack.png", "salir", "")]
    return m


def abrir(addon, perfil, t, url, favoritas=(), con_trakt=False, log=print,
          filtrar_peliculas=lambda pelis: pelis, cargar_exploracion=None, cargar_directorio=None,
          refrescar_seguimiento=None):
    import xbmc
    import xbmcgui

    logo = addon.getAddonInfo("icon")

    def li(e):
        item = xbmcgui.ListItem(e["label"], e.get("label2", ""))
        fanart = "" if addon.getSetting("modo_visual") == "2" else e.get("fanart", "")
        sustituto = logo if e.get("a_medias") or e.get("exploracion") else ""
        item.setArt({"poster": e.get("poster") or sustituto, "fanart": fanart,
                     "thumb": e.get("thumb") or sustituto, "icon": e.get("icon", "")})
        tag = item.getVideoInfoTag()
        tag.setPlot(e.get("plot", ""))
        if e.get("resume"):
            tag.setResumePoint(float(e["resume"][0]), float(e["resume"][1]))
        for k in ("info", "destacado", "nuevo", "seguida", "a_medias", "tipo", "url", "activa"):
            item.setProperty(k, e.get(k, ""))
        if e.get("contexto"):
            item.setProperty("contexto", json.dumps(e["contexto"]))
        return item

    class Inicio(xbmcgui.WindowXML):
        def onInit(self):
            self.setProperty("logo", logo)
            self.setProperty("modo_visual", addon.getSetting("modo_visual"))
            self.setProperty("version", addon.getAddonInfo("version"))
            self.setProperty("fondo_palantix", addon.getAddonInfo("fanart"))
            if getattr(self, "_listo", False):
                self.actualizar_progreso()
                return
            self._listo = True
            for fid, titulo in FILAS:
                self.setProperty("fila%d" % fid, titulo)
            m = self.getControl(200)
            for nombre, icono, tipo, destino in menu(url, con_trakt, addon.getSetting("tdtchannels_activo") != "false"):
                it = xbmcgui.ListItem(nombre)
                it.setArt({"icon": icono or logo})
                it.setProperty("tipo", tipo)
                it.setProperty("url", destino)
                m.addItem(it)
            self.cargar("inicio")

        def cargar(self, pestana):
            """Rellena las filas con la pestaña pedida (Inicio, Películas o Series) sin salir de la pantalla."""
            self.pestana = pestana
            self.exploracion = self.directorio = None
            self.niveles = []
            self.setProperty("pestana", NOMBRE_PESTANA[pestana])
            menu_lateral = self.getControl(200)
            for i in range(menu_lateral.size()):
                opcion = menu_lateral.getListItem(i)
                activa = opcion.getProperty("tipo") == "pestana" and opcion.getProperty("url") == pestana
                opcion.setProperty("activa", "1" if activa else "")
            self.setProperty("estado", "Cargando...")
            self.revision_seguimiento = seguimiento.revision_archivo(perfil)
            try:
                if refrescar_seguimiento and pestana in ("inicio", "series") and novedades.progreso_desactualizado(perfil):
                    refrescar_seguimiento()
                if pestana == "inicio":
                    mostrar_catalogo = addon.getSetting("inicio_mostrar_catalogo") != "false"
                    filas = datos_filas(perfil, t, url, favoritas, filtrar_peliculas,
                                        ocultar_destripes=addon.getSetting("series_sin_destripes") == "true",
                                        mostrar_catalogo=mostrar_catalogo)
                    if not mostrar_catalogo:
                        filas[111] = []
                elif t:
                    filas = datos_pestana(perfil, t, url, pestana, filtrar_peliculas)
                else:
                    filas = {}
            except Exception as e:
                log("Pestaña %s: %s" % (pestana, e))
                filas = {}
            self.clearProperty("estado")
            if pestana != "inicio" and t:
                filas[100] = accesos_generos(pestana, url, logo)
            nombres = titulos(pestana)
            if pestana == "inicio" and addon.getSetting("inicio_primero_nuevos") == "true":
                filas[101], filas[102] = filas.get(102, []), filas.get(101, [])
                nombres[101], nombres[102] = nombres[102], nombres[101]
            estado = "No hay títulos para mostrar" if t else "Pon tu clave de TMDB en Ajustes para ver el catálogo"
            self.pintar_filas(filas, nombres, estado)

        def pintar_filas(self, filas, nombres, estado="", foco=None):
            primera = None
            for fid in TODAS:
                control = self.getControl(fid)
                control.reset()
                self.clearProperty("fila%d" % fid)
                elementos = filas.get(fid, [])
                if elementos:
                    self.setProperty("fila%d" % fid, nombres[fid])
                    control.addItems([li(e) for e in elementos])
                    primera = primera or fid
            if estado and not primera:
                self.setProperty("estado", estado)
            else:
                self.clearProperty("estado")
            self.setFocusId(foco or primera or 200)

        def abrir_genero(self, parametros):
            self.acceso_genero = self.getControl(100).getSelectedPosition()
            self.exploracion = parametros
            self.pagina_genero(1)

        def pagina_genero(self, pagina):
            parametros = self.exploracion
            tipo = parametros.get("tipo", "movie")
            self.setProperty("pestana", parametros.get("genero") or "Géneros")
            estado = ""
            try:
                resultados = cargar_exploracion(parametros, pagina)
            except Exception as e:
                log("Explorar géneros: %s" % e)
                resultados = explorar.Resultados([], pagina, False, set(), set())
                estado = "No se pudo cargar este género"
            self.pagina_actual = pagina
            self.total_genero = resultados.total
            filtros = explorar.filtros(parametros)
            valores = [opciones[filtros[clave]] for clave, _, opciones in
                       explorar.campos_filtro(tipo, incluir_orden=False)]
            acciones = [("Filtros", "filtros_genero", _info(*valores))]
            if filtros != explorar.filtros({"orden": filtros["orden"]}):
                acciones.append(("Quitar filtros", "limpiar_genero", ""))
            if pagina > 1:
                acciones.append(("Página anterior", "anterior_genero", ""))
            if pagina < resultados.total:
                acciones.append(("Página siguiente", "siguiente_genero", ""))
            acciones.append(("Volver a géneros", "volver_genero", ""))
            filas = {FILA_ACCIONES: [{"label": titulo, "tipo": accion, "info": info}
                                    for titulo, accion, info in acciones],
                     FILA_ORDEN: pestanas_orden(explorar.ORDENES, filtros["orden"], "orden_genero", str)}
            nombres = {FILA_ORDEN: "Orden", FILA_ACCIONES: "Explorar"}
            tarjetas = tarjetas_exploracion(resultados, tipo, url, seguimiento.leer(perfil), novedades.leer(perfil))
            for i in range(0, len(tarjetas), 10):
                fid = 103 + i // 10
                filas[fid] = tarjetas[i:i + 10]
                nombres[fid] = ("Resultados · página %d" % pagina) if i == 0 else "Más resultados"
            if resultados.guardados:
                estado = "Mostrando los últimos resultados guardados"
            elif not tarjetas and not estado:
                estado = "No hay resultados con estos filtros"
            if estado:
                nombres[FILA_ORDEN] += " · " + estado
            self.pintar_filas(filas, nombres, foco=103 if tarjetas else FILA_ORDEN)

        def ordenar_genero(self, orden):
            if orden == explorar.filtros(self.exploracion)["orden"]:
                return
            self.exploracion["orden"] = orden
            self.pagina_genero(1)
            self.restaurar_foco((FILA_ORDEN, list(explorar.ORDENES).index(orden)))

        def elegir_genero(self, tipo):
            try:
                generos = t.s_generos() if tipo == "tv" else t.generos()
            except (OSError, ValueError):
                return xbmcgui.Dialog().ok("Géneros", "No se pudo cargar la lista de géneros")
            opciones = [{"name": "Todos los géneros", "id": ""}] + sorted(generos, key=lambda g: g["name"].casefold())
            n = xbmcgui.Dialog().select("Géneros", [g["name"] for g in opciones])
            if n >= 0:
                elegido = opciones[n]
                self.abrir_genero({"tipo": tipo, "gid": elegido["id"], "genero": elegido["name"]})

        def volver_genero(self):
            self.cargar(self.pestana)
            self.getControl(100).selectItem(self.acceso_genero)
            self.setFocusId(100)

        def cambiar_filtros_genero(self):
            filtros = explorar.elegir_filtros(self.exploracion["tipo"], self.exploracion, xbmcgui.Dialog().select,
                                             incluir_orden=False)
            if filtros is not None:
                self.exploracion.update(filtros)
                self.pagina_genero(1)

        def posicion(self):
            fid = self.getFocusId()
            if fid not in TODAS and fid != 200:
                return 200, 0
            return fid, self.getControl(fid).getSelectedPosition()

        def restaurar_foco(self, posicion):
            fid, indice = posicion
            control = self.getControl(fid)
            if control.size():
                control.selectItem(max(0, min(indice, control.size() - 1)))
                self.setFocusId(fid)

        def abrir_directorio(self, destino, etiqueta):
            if cargar_directorio is None:
                return False
            revision = seguimiento.revision_archivo(perfil)
            directorio = cargar_directorio(destino)
            if directorio is None:
                return False
            if directorio.correcto:
                self.revision_seguimiento = revision
                self.niveles.append((self.directorio, self.posicion()))
                destino = directorio.destino or destino
                datos = menu_visual.parametros(destino)
                titulo = datos.get("q") if datos.get("accion") in ("buscar", "s_buscar") else ""
                self.directorio = (destino, titulo or menu_visual.titulo_de(datos, etiqueta), directorio)
                self.pintar_directorio()
            return True

        def pintar_directorio(self):
            _, titulo, directorio = self.directorio
            filas, nombres = menu_visual.filas(directorio, logo)
            if directorio.orden:
                opciones, actual, alcance, base = directorio.orden
                parametros = menu_visual.parametros(base)
                parametros.pop("orden", None)
                filas[FILA_ORDEN] = pestanas_orden(opciones, actual, "orden_directorio",
                                                  lambda orden: url(orden=orden, **parametros))
                nombres[FILA_ORDEN] = "Orden" + (" · " + alcance if alcance else "")
                if 100 in filas:
                    filas[FILA_ACCIONES], nombres[FILA_ACCIONES] = filas.pop(100), nombres.pop(100)
                if 103 not in filas:
                    nombres[FILA_ORDEN] += " · Sin resultados"
            self.setProperty("pestana", titulo)
            self.pintar_filas(filas, nombres, "No hay elementos en este apartado", foco=103 if 103 in filas else None)

        def volver_directorio(self):
            self.directorio, posicion = self.niveles.pop()
            if self.directorio:
                destino, titulo, _ = self.directorio
                if not self.es_directorio_seguimiento() or not self.reemplazar_directorio(destino, titulo):
                    self.pintar_directorio()
            elif self.exploracion:
                self.pagina_genero(self.pagina_actual)
            else:
                self.cargar(self.pestana)
            self.restaurar_foco(posicion)

        def contexto(self):
            fid = self.getFocusId()
            if fid not in TODAS:
                return
            item = self.getControl(fid).getSelectedItem()
            opciones = json.loads(item.getProperty("contexto") or "[]") if item else []
            if not opciones:
                return
            n = xbmcgui.Dialog().select("Opciones", [etiqueta for etiqueta, _ in opciones])
            if n < 0:
                return
            etiqueta, comando = opciones[n]
            if comando.startswith("Container.Update("):
                destino = comando[len("Container.Update("):-1].partition(",")[0]
                if self.abrir_directorio(destino, etiqueta):
                    return
            if comando.startswith("RunPlugin(") and self.ejecutar_mutacion(comando[10:-1]):
                return
            xbmc.executebuiltin(comando)

        def ejecutar_mutacion(self, destino):
            if not self.directorio or not menu_visual.es_mutacion(destino):
                return False
            resultado = cargar_directorio(destino, mutacion=True)
            if resultado is None:
                return False
            if resultado.correcto:
                self.refrescar_directorio()
            return True

        def refrescar_directorio(self):
            destino, titulo, _ = self.directorio
            posicion = self.posicion()
            if self.reemplazar_directorio(destino, titulo):
                self.restaurar_foco(posicion)

        def reemplazar_directorio(self, destino, titulo):
            revision = seguimiento.revision_archivo(perfil)
            directorio = cargar_directorio(destino)
            if directorio is None or not directorio.correcto:
                return False
            self.directorio = (directorio.destino or destino, titulo, directorio)
            self.revision_seguimiento = revision
            self.pintar_directorio()
            return True

        def es_directorio_seguimiento(self):
            return bool(self.directorio and menu_visual.parametros(self.directorio[0]).get("accion")
                        in ("seguir", "capitulos", "trakt_progreso"))

        def actualizar_progreso(self):
            revision = seguimiento.revision_archivo(perfil)
            if revision == self.revision_seguimiento:
                return False
            self.revision_seguimiento = revision
            if self.es_directorio_seguimiento():
                self.refrescar_directorio()
                return True
            if not self.directorio and not self.exploracion and self.pestana in ("inicio", "series"):
                posicion = self.posicion()
                self.cargar(self.pestana)
                self.restaurar_foco(posicion)
                return True
            return False

        def filtrar_directorio(self, destino):
            datos = menu_visual.parametros(destino)
            tipo = datos.get("tipo", "movie")
            filtros = explorar.elegir_filtros(tipo, datos, xbmcgui.Dialog().select, incluir_orden=False)
            if filtros is None:
                return
            titulo = datos.get("genero") or "Todos los géneros"
            destino = url(accion="explorar", tipo=tipo, gid=datos.get("gid", ""), genero=titulo, **filtros)
            self.reemplazar_directorio(destino, titulo)

        def ordenar_directorio(self, destino):
            _, titulo, directorio = self.directorio
            orden = menu_visual.parametros(destino)["orden"]
            opciones, actual, _, _ = directorio.orden
            if orden != actual and self.reemplazar_directorio(destino, titulo):
                self.restaurar_foco((FILA_ORDEN, list(opciones).index(orden)))

        def onAction(self, accion):
            codigo = accion.getId()
            if codigo in (10, 92):
                if self.directorio:
                    return self.volver_directorio()
                if self.exploracion:
                    return self.volver_genero()
                if getattr(self, "pestana", "inicio") != "inicio":
                    return self.cargar("inicio")
                return self.close()
            if codigo == 117:
                self.actualizar_progreso()
                return self.contexto()
            if codigo in (1, 2, 3, 4):
                self.actualizar_progreso()
            if self.exploracion and not self.directorio and codigo in (5, 6):
                pagina = self.pagina_actual + (1 if codigo == 6 else -1)
                if 1 <= pagina <= self.total_genero:
                    self.pagina_genero(pagina)

        def onClick(self, control_id):
            if self.actualizar_progreso() and control_id != 200:
                return
            item = self.getControl(control_id).getSelectedItem()
            if not item:
                return
            tipo, destino = item.getProperty("tipo"), item.getProperty("url")
            if tipo == "pestana":
                self.cargar(destino)
            elif tipo in ("genero", "generos") and cargar_exploracion:
                parametros = dict(parse_qsl(destino.partition("?")[2]))
                if tipo == "genero":
                    self.abrir_genero(parametros)
                else:
                    self.elegir_genero(parametros.get("tipo", "movie"))
            elif tipo == "filtros_genero":
                self.cambiar_filtros_genero()
            elif tipo == "orden_genero":
                self.ordenar_genero(destino)
            elif tipo == "orden_directorio":
                self.ordenar_directorio(destino)
            elif tipo == "limpiar_genero":
                defaults = explorar.filtros({})
                for k, _, _ in explorar.campos_filtro(self.exploracion["tipo"], incluir_orden=False):
                    self.exploracion[k] = defaults[k]
                self.pagina_genero(1)
            elif tipo == "anterior_genero":
                self.pagina_genero(self.pagina_actual - 1)
            elif tipo == "siguiente_genero":
                self.pagina_genero(self.pagina_actual + 1)
            elif tipo == "volver_genero":
                self.volver_genero()
            elif tipo == "salir":  # cerrar Palantix y volver a la pantalla principal de Kodi
                self.close()
                xbmc.executebuiltin("ActivateWindow(Home)")
            elif tipo == "ajustes":
                addon.openSettings()
            elif tipo == "reproducir":
                xbmc.executebuiltin("PlayMedia(%s)" % destino)
            elif destino:
                accion = menu_visual.parametros(destino).get("accion")
                if self.directorio and accion == "explorar_filtros":
                    self.filtrar_directorio(destino)
                elif self.directorio and control_id == FILA_ACCIONES and menu_visual.parametros(destino).get("page"):
                    self.reemplazar_directorio(destino, self.directorio[1])
                elif self.ejecutar_mutacion(destino):
                    return
                elif tipo == "dialogo" or accion in menu_visual.DIALOGOS:
                    xbmc.executebuiltin("RunPlugin(%s)" % destino)
                elif (not cargar_directorio or accion not in menu_visual.TITULOS
                      or not self.abrir_directorio(destino, item.getLabel())):
                    xbmc.executebuiltin("ActivateWindow(Videos,%s,return)" % destino)

    ventana = Inicio("palantix-inicio.xml", addon.getAddonInfo("path"), "default", "1080i")
    ventana.doModal()
    del ventana
