"""Clasificación y emparejamiento de los canales configurados con la guía."""
import re
from collections import defaultdict
from dataclasses import dataclass

from . import deportes, epg, listas

TDT_TV = "https://www.tdtchannels.com/lists/tv.m3u8"
TDT_RADIO = "https://www.tdtchannels.com/lists/radio.m3u8"
TDT_TTL = 4 * 3600


@dataclass
class Parrilla:
    canales: dict
    programas: dict
    logos: dict
    grupos: dict
    internacionales: dict


def canales_tdt(cache):
    salida = []
    for item in listas.cargar(TDT_TV, cache, TDT_TTL, canales=True):
        if not deportes.es_web(item["url"]):
            continue
        palabras = set(epg.normalizar(item["grupo"]).split())
        internacional = bool(palabras & {"int", "internacional", "internacionales"})
        salida.append(dict(item, pais="int" if internacional else "ES", es_tdt=True))
    return salida


def radios_tdt(cache):
    grupos, vistos = defaultdict(list), set()
    for item in listas.cargar(TDT_RADIO, cache, TDT_TTL, canales=True):
        grupo = item["grupo"].replace("_", " ")
        grupo = grupo[6:] if grupo.casefold().startswith("radio ") else grupo
        clave = item["tvg_id"].casefold() or epg.normalizar(item["titulo"])
        if clave not in vistos and deportes.es_web(item["url"]):
            grupos[grupo].append(item)
            vistos.add(clave)
    return dict(grupos)


ESPANA = {"es", "esp", "espana", "spain"}
PAISES = ESPANA | {
    "argentina", "brasil", "chile", "colombia", "ecuador", "francia", "france",
    "alemania", "germany", "italia", "italy", "mexico", "peru", "portugal",
    "reino unido", "uk", "usa", "estados unidos", "uruguay", "venezuela",
    "latinoamerica", "latam", "internacional", "international",
}
ALIASES_ES = {
    "la1": "la 1", "tve 1": "la 1", "la2": "la 2", "tve 2": "la 2",
    "antena3": "antena 3", "la sexta": "lasexta", "tele 5": "telecinco",
    "rmtv": "real madrid tv", "esport 3": "esport3", "s24h": "24h",
}
CANALES_ES = {"la 1", "la 2", "antena 3", "cuatro", "telecinco", "lasexta",
              "24h", "clan", "tdp", "teledeporte", "esport3", "real madrid tv", "top barca"}


def clave_canal(titulo):
    clave = epg.nombre_canal(titulo)
    return ALIASES_ES.get(clave, clave)


def es_espanol(item, cid):
    pais = epg.normalizar(item.get("pais", ""))
    if pais:
        return bool(ESPANA.intersection(pais.split()))
    grupos = [epg.normalizar(g) for g in re.split(r"[;|,]", item["grupo"])]
    regiones = {p for p in PAISES if any(g == p or g.startswith(p + " ") for g in grupos)}
    if regiones:
        return bool(regiones & ESPANA)
    identificador = item.get("tvg_id", "").casefold()
    if identificador.endswith(".es"):
        return True
    if re.search(r"\.[a-z]{2}$", identificador):
        return False
    return bool(cid or clave_canal(item["titulo"]) in CANALES_ES)


def preparar(items, guia, guia_tdt=None):
    """Devuelve la guía española y los demás canales por grupo, sin consultar la red."""
    indice = epg.indice_nombres(guia)
    for alias, clave in ALIASES_ES.items():
        if alias in indice:
            indice.setdefault(clave, indice[alias])
    canales, internos, logos, grupos = {}, defaultdict(list), {}, {}
    programas = dict(guia.get("programas", {}))
    programas_tdt = (guia_tdt or {}).get("programas", {})
    for titulo, enlace in deportes.CANALES:
        id_guia = indice.get(clave_canal(titulo)) or epg.IDS_PALANTIX.get(titulo, titulo)
        canales[id_guia] = (titulo, enlace)

    nombres = {clave_canal(titulo): cid for cid, (titulo, _) in canales.items()}
    vistos, ids_tdt = set(), {}
    for item in items:
        titulo, enlace = item["titulo"], item["url"]
        if not (deportes.es_web(enlace) or deportes.ace_id(enlace) or deportes.ruta_canal_ekhorus(enlace)):
            continue
        id_guia = item.get("tvg_id", "")
        if id_guia not in guia["nombres"]:
            id_guia = next((cid for dato in (id_guia, item.get("tvg_nombre", ""), titulo)
                            if (cid := (indice.get(epg.nombre_canal(dato)) or indice.get(clave_canal(dato))))), "")
        if es_espanol(item, id_guia):
            clave = clave_canal(titulo)
            tvg_id = item.get("tvg_id", "") if item.get("es_tdt") else ""
            cid = ids_tdt.get(tvg_id) or id_guia or nombres.get(clave) or "canal:" + (clave or titulo.casefold())
            if tvg_id:
                ids_tdt[tvg_id] = cid
                if programas_tdt.get(tvg_id):
                    programas[cid] = programas_tdt[tvg_id]
            if item.get("es_tdt"):
                grupos[cid] = item["grupo"]
            if cid not in vistos:
                canales[cid] = (canales.get(cid, (titulo, enlace))[0], enlace)
                nombres.setdefault(clave, cid)
                vistos.add(cid)
            if item.get("poster"):
                logos.setdefault(cid, item["poster"])
        else:
            grupo = item["grupo"] or "Sin grupo"
            clave = (grupo, (item.get("tvg_id") or clave_canal(titulo)) if item.get("es_tdt") else enlace)
            if clave not in vistos:
                internos[grupo].append(item)
                vistos.add(clave)
    return Parrilla(canales, programas, logos, grupos, dict(internos))
