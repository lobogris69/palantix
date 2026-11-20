"""Guía XMLTV dobleM. Las fechas se guardan como segundos UTC."""
import gzip
import json
import os
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

URL = "https://raw.githubusercontent.com/davidmuma/EPG_dobleM/master/guiatv.xml.gz"
TTL = 4 * 3600
HORIZONTE = 48 * 3600
IDS_PALANTIX = {"Esport3": "Esport3 Catalunya"}


def _fecha(texto):
    return datetime.strptime(texto, "%Y%m%d%H%M%S %z").timestamp()


def leer_xml(origen, ahora):
    """Lee en flujo y conserva programación útil para las siguientes 48 horas."""
    eventos = ElementTree.iterparse(origen, events=("start", "end"))
    _, raiz = next(eventos)
    if raiz.tag != "tv":
        raise ValueError("Se esperaba una guía XMLTV")
    nombres, programas = {}, {}
    for accion, elemento in eventos:
        if accion != "end":
            continue
        if elemento.tag == "channel":
            nombres[elemento.get("id")] = [n.text for n in elemento.findall("display-name") if n.text]
        elif elemento.tag == "programme":
            try:
                inicio = _fecha(elemento.get("start", ""))
                fin = _fecha(elemento.get("stop", ""))
            except ValueError:
                inicio = fin = 0
            titulo = (elemento.findtext("title") or "").strip()
            if titulo and inicio < fin and fin > ahora and inicio < ahora + HORIZONTE:
                programas.setdefault(elemento.get("channel"), []).append([inicio, fin, titulo])
        else:
            continue
        raiz.remove(elemento)
    if not nombres or not programas:
        raise ValueError("La guía dobleM no trae programación vigente")
    return {"nombres": nombres, "programas": {k: sorted(v) for k, v in programas.items()}}


def cargar(cache, ahora=None):
    ahora = time.time() if ahora is None else ahora
    ruta = Path(cache) / "epg-doblem.json"
    datos = None
    try:
        with ruta.open(encoding="utf-8") as f:
            datos = json.load(f)
        if ahora - ruta.stat().st_mtime < TTL:
            return datos
    except (OSError, ValueError):
        pass

    try:
        with urllib.request.urlopen(URL, timeout=10) as respuesta:
            with gzip.GzipFile(fileobj=respuesta) as xml:
                nuevos = leer_xml(xml, ahora)
    except (OSError, EOFError, ValueError, ElementTree.ParseError):
        if datos is None:
            raise
        return datos

    temporal = None
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=ruta.parent, delete=False) as f:
            temporal = f.name
            json.dump(nuevos, f, ensure_ascii=False)
        os.replace(temporal, ruta)
        temporal = None
    except OSError:
        pass
    finally:
        if temporal and os.path.exists(temporal):
            os.unlink(temporal)
    return nuevos


def normalizar(nombre):
    return " ".join(nombre.casefold().split())


def indice_nombres(datos):
    indice = {}
    for canal, nombres in datos["nombres"].items():
        for nombre in [canal] + nombres:
            indice.setdefault(normalizar(nombre), set()).add(canal)
    return {nombre: next(iter(ids)) for nombre, ids in indice.items() if len(ids) == 1}


def ahora_y_despues(programas, hora):
    actual = siguiente = None
    for programa in programas:
        inicio, fin, _ = programa
        if inicio <= hora < fin:
            actual = programa
        if inicio > hora:
            siguiente = programa
            break
    return actual, siguiente
