"""Adapta los directorios de Palantix a las filas de la pantalla visual."""
import re
from urllib.parse import parse_qsl, urlsplit

TITULOS = {
    "m_peliculas": "Películas", "m_series": "Series", "favoritas": "Mis favoritas",
    "listas": "Mis listas", "cine_libre": "Cine libre y documentales", "tv_internacional": "TV internacional",
    "radio_tdt": "Radio", "deportes": "Opciones de TV", "deportes_canales": "Canales en directo",
    "deportes_epg": "Guía TV", "deportes_fuentes": "Mis fuentes de TV", "deportes_hoy": "Deportes hoy",
    "deportes_eventos": "Eventos deportivos", "deportes_lista": "Canales y eventos",
    "anios": "Por año", "a_medias": "Continuar viendo", "trakt": "Trakt", "trakt_progreso": "Progreso de series",
    "hoy_para_ti": "Hoy para ti", "lista_avisos_plataforma": "Avisos de plataformas",
    "lista_avisos_fuentes": "Avisos de fuentes", "favoritas_disponibles": "Favoritas con fuente",
    "historial_vistos": "Historial de vistos", "tendencias": "Tendencias", "populares": "Populares",
    "en_cines": "En cines", "mejor_valoradas": "Mejor valoradas", "novedades_streaming": "Novedades en streaming",
    "s_tendencias": "Series del momento", "s_populares": "Series populares", "s_mejor_valoradas": "Mejor valoradas",
    "s_capitulos_recientes": "Capítulos recientes", "anio": "Películas", "s_anio": "Series",
    "sagas": "Sagas", "sagas_buscar": "Buscar saga", "saga": "Saga", "elegir_juntos": "Elegir juntos",
    "explorar_generos": "Explorar géneros", "explorar": "Géneros", "explorar_ficha": "Ficha",
    "donde_ver": "Dónde ver", "seguir": "Series en seguimiento", "trakt_pend": "Pendientes de Trakt",
    "trakt_lista": "Lista de Trakt", "generos": "Géneros", "s_generos": "Géneros de series",
    "genero": "Películas", "s_genero": "Series", "buscar": "Buscar películas", "s_buscar": "Buscar series",
    "temporadas": "Temporadas", "capitulos": "Capítulos",
}
DIALOGOS = {
    "tv", "deportes_guia_propia", "deportes_cuadricula", "tv_importar_ekhorus", "deportes_horus",
    "deportes_anadir", "deportes_recordatorio", "deportes_detener", "perfiles_kodi", "actualizar",
    "valorar_visto", "ajustes_serie", "perfiles_visto", "perfiles_elegir", "aviso_plataforma", "oferta_streaming",
    "lista_nueva", "lista_ayuda", "asistente_configuracion", "copiar_preferencias", "orden_idiomas",
    "ajustes", "vincular", "cuenta", "estado_indice", "tmdb_clave", "aviso_fuente", "trailer",
}
_MUTACIONES = {
    "marcar_capitulo", "valorar_visto", "fav_poner", "fav_quitar", "lista_nueva", "lista_quitar", "lista_renombrar",
    "lista_recargar",
    "quitar_medias", "dejar_seguir", "trakt_cambiar_pendiente", "deportes_anadir", "deportes_quitar",
    "quitar_aviso_fuente", "quitar_aviso_plataforma",
}
_ETIQUETAS = re.compile(r"\[/?(?:COLOR(?: [^\]]+)?|B|I)\]", re.I)


def parametros(destino):
    try:
        partes = urlsplit(destino)
    except ValueError:
        return {}
    return dict(parse_qsl(partes.query)) if (partes.scheme, partes.netloc) == ("plugin", "plugin.video.palantix") else {}


def titulo_de(param, etiqueta):
    titulo = param.get("titulo")
    if param["accion"] == "capitulos":
        temporada = param.get("s", "0")
        temporada = "Especiales" if temporada == "0" else "Temporada " + temporada
        return " · ".join(filter(None, (titulo, temporada)))
    if param["accion"] == "temporadas" and titulo:
        return titulo
    limpio = _ETIQUETAS.sub("", etiqueta)
    if limpio and not limpio.startswith(("Página siguiente", "Página anterior")):
        return limpio
    return param.get("genero") or param.get("q") or TITULOS[param["accion"]]


def es_mutacion(destino):
    return parametros(destino).get("accion") in _MUTACIONES


class Elemento:
    def __init__(self, item):
        self.item = item
        self.contexto = []

    def __getattr__(self, nombre):
        return getattr(self.item, nombre)

    def addContextMenuItems(self, opciones):
        self.contexto.extend(opciones)


class GUI:
    def __init__(self, kodi):
        self.kodi = kodi

    def __getattr__(self, nombre):
        return getattr(self.kodi, nombre)

    def ListItem(self, *args, **kwargs):
        return Elemento(self.kodi.ListItem(*args, **kwargs))


class Directorio:
    def __init__(self, kodi):
        self.kodi = kodi
        self.items = []
        self.contenido = ""
        self.correcto = True

    def __getattr__(self, nombre):
        return getattr(self.kodi, nombre)

    def setContent(self, handle, contenido):
        self.contenido = contenido

    def addDirectoryItem(self, handle, url, listitem, isFolder=False, totalItems=0):
        self.items.append((url, listitem, isFolder))
        return True

    def addDirectoryItems(self, handle, items, totalItems=0):
        self.items.extend(items)
        return True

    def addSortMethod(self, *args, **kwargs):
        pass

    def endOfDirectory(self, handle, succeeded=True, **kwargs):
        self.correcto = succeeded


def tarjeta(destino, elemento, carpeta, logo, episodios):
    etiqueta = _ETIQUETAS.sub("", elemento.getLabel()).strip()
    tag = elemento.getVideoInfoTag()
    poster = elemento.getArt("poster")
    fanart = elemento.getArt("fanart")
    icon = elemento.getArt("icon")
    thumb = elemento.getArt("thumb") or fanart or poster or icon or logo
    duracion = tag.getDuration()
    pos, total = tag.getResumeTime(), tag.getResumeTimeTotal()
    visto = bool(tag.getPlayCount()) and episodios
    accion = parametros(destino).get("accion")
    tipo = ("reproducir" if elemento.getProperty("IsPlayable") == "true" else
            "dialogo" if accion in DIALOGOS else "carpeta" if carpeta else "")
    marca = "Visto" if visto else "A medias" if pos else "Con fuente" if "Con fuente" in etiqueta else ""
    return {"label": etiqueta, "label2": etiqueta, "plot": tag.getPlot(),
            "poster": poster or thumb, "thumb": thumb, "fanart": fanart,
            "info": " · ".join(filter(None, ("%d min" % round(duracion / 60) if duracion else "", marca))),
            "destacado": marca, "seguida": marca, "tipo": tipo, "url": destino,
            "resume": (pos, total) if pos and total else None, "contexto": elemento.contexto}


def filas(directorio, logo):
    contenido = directorio.contenido
    episodios = contenido == "episodes"
    tarjetas = [tarjeta(destino, elemento, carpeta, logo, episodios)
                for destino, elemento, carpeta in directorio.items]
    if not tarjetas:
        return {}, {}
    if contenido in ("movies", "tvshows", "seasons"):
        acciones, obras = [], []
        for t in tarjetas:
            param = parametros(t["url"])
            es_filtro = param.get("accion") == "explorar_filtros" or t["label"] == "Quitar filtros"
            lista = acciones if param.get("page") or es_filtro else obras
            lista.append(t)
        resultado = {103 + i: obras[i * 10:(i + 1) * 10 if i < 8 else len(obras)]
                     for i in range(min(9, (len(obras) + 9) // 10))}
        nombres = {i: ("Temporadas" if contenido == "seasons" else "Títulos") if i == 103 else "Más títulos"
                   for i in resultado}
        if acciones:
            resultado[100], nombres[100] = acciones, "Navegación"
        return resultado, nombres
    if episodios:
        return {101: tarjetas[:10], 102: tarjetas[10:]}, {101: "Capítulos", 102: "Más capítulos"}
    return {101: tarjetas}, {101: "Opciones"}
