"""Clasificación y emparejamiento de los canales configurados con la guía."""
import re
from collections import defaultdict

from . import deportes, epg

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


def preparar(items, guia):
    """Devuelve la guía española y los demás canales por grupo, sin consultar la red."""
    indice = epg.indice_nombres(guia)
    for alias, clave in ALIASES_ES.items():
        if alias in indice:
            indice.setdefault(clave, indice[alias])
    canales, internos = {}, defaultdict(list)
    for titulo, enlace in deportes.CANALES:
        id_guia = indice.get(clave_canal(titulo)) or epg.IDS_PALANTIX.get(titulo, titulo)
        canales[id_guia] = (titulo, enlace)

    nombres = {clave_canal(titulo): cid for cid, (titulo, _) in canales.items()}
    vistos = set()
    for item in items:
        titulo, enlace = item["titulo"], item["url"]
        if not (deportes.es_web(enlace) or deportes.ace_id(enlace) or deportes.ruta_canal_ekhorus(enlace)):
            continue
        id_guia = item.get("tvg_id", "")
        if id_guia not in guia["nombres"]:
            id_guia = next((cid for dato in (id_guia, item.get("tvg_nombre", ""), titulo)
                            if (cid := (indice.get(epg.nombre_canal(dato)) or indice.get(clave_canal(dato))))), "")
        if es_espanol(item, id_guia):
            cid = id_guia or nombres.get(clave_canal(titulo)) or "canal:" + clave_canal(titulo)
            if cid not in vistos:
                canales[cid] = (canales.get(cid, (titulo, enlace))[0], enlace)
                vistos.add(cid)
        else:
            grupo = item["grupo"] or "Sin grupo"
            clave = (grupo, enlace)
            if clave not in vistos:
                internos[grupo].append(item)
                vistos.add(clave)
    return canales, dict(internos)
