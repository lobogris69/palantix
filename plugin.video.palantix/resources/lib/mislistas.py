"""Mis listas: las direcciones de listas (JSON o M3U) que añade el usuario, con nombre y sin límite.

mislistas.json en el perfil: [{"nombre": "...", "origen": "https://... o ruta"}]
Las tres casillas antiguas de Ajustes (lista_1..3) se pasan aquí solas la primera vez.
"""
import json
import os
from urllib.parse import urlparse

AYUDA = (
    "[B]¿Qué dirección puedo poner?[/B]\n"
    "La dirección de un FICHERO DE LISTA (como los de los reproductores IPTV), en uno de estos dos formatos:\n\n"
    "[B]M3U[/B] (el más habitual):\n"
    "#EXTM3U\n"
    "#EXTINF:-1 tvg-logo=\"https://.../caratula.jpg\" group-title=\"Terror\",Nosferatu (1922)\n"
    "https://.../nosferatu.mp4\n\n"
    "[B]JSON[/B]:\n"
    "{\"nombre\": \"Mi lista\", \"peliculas\": [{\"titulo\": \"Nosferatu\", \"anio\": 1922, \"url\": \"https://...\"}]}\n\n"
    "Para series: «Mi serie S01E02» en el título, o «serie», «temporada» y «episodio» en JSON.\n"
    "Los enlaces pueden ser directos, de alojamientos o magnets (estos dos, con tu AllDebrid).\n\n"
    "[B]Lo que NO sirve:[/B] la dirección de una página web normal. Tiene que ser el fichero de la lista."
)


def _ruta(perfil):
    return os.path.join(perfil, "mislistas.json")


def leer(perfil):
    try:
        with open(_ruta(perfil), encoding="utf-8") as f:
            datos = json.load(f)
        return [d for d in datos if d.get("origen")]
    except (OSError, ValueError):
        return []


def guardar(perfil, listas):
    os.makedirs(perfil, exist_ok=True)
    with open(_ruta(perfil), "w", encoding="utf-8") as f:
        json.dump(listas, f, ensure_ascii=False, indent=1)


def nombre_por_defecto(origen):
    p = urlparse(origen)
    if p.scheme in ("http", "https"):
        base = os.path.basename(p.path) or p.netloc
        return "%s · %s" % (os.path.splitext(base)[0] or p.netloc, p.netloc)
    return os.path.splitext(os.path.basename(origen))[0] or origen


def migrar(perfil, antiguas):
    """Pasa las direcciones de las casillas antiguas de Ajustes. Devuelve cuántas se añadieron."""
    listas = leer(perfil)
    ya = {l["origen"] for l in listas}
    nuevas = [o.strip() for o in antiguas if o and o.strip() and o.strip() not in ya]
    for o in nuevas:
        listas.append({"nombre": nombre_por_defecto(o), "origen": o})
    if nuevas:
        guardar(perfil, listas)
    return len(nuevas)


def anadir(perfil, nombre, origen):
    listas = leer(perfil)
    if any(l["origen"] == origen for l in listas):
        return False
    listas.append({"nombre": nombre or nombre_por_defecto(origen), "origen": origen})
    guardar(perfil, listas)
    return True


def quitar(perfil, indice):
    listas = leer(perfil)
    if 0 <= indice < len(listas):
        listas.pop(indice)
        guardar(perfil, listas)


def renombrar(perfil, indice, nombre):
    listas = leer(perfil)
    if 0 <= indice < len(listas) and nombre:
        listas[indice]["nombre"] = nombre
        guardar(perfil, listas)
