"""Fuentes deportivas y validación de enlaces al motor Ace Stream."""
import ast
import base64
import binascii
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote, urlencode, urlsplit

HORUS = "script.module.horus"
_CID = re.compile(r"(?:acestream://)?([0-9a-f]{40})", re.I)

CANALES = (
    ("Teledeporte", "https://rtvelivestream.rtve.es/rtvesec/tdp/tdp_main_720.m3u8"),
    ("Esport3", "https://directes-tv-es.3catdirectes.cat/live-origin/esport3-hls/master.m3u8"),
    ("Real Madrid TV", ""),
    ("Top Barça", "https://amg17560-fcb-amg17560c2-samsung-es-9803.playouts.now.amagi.tv/ts-eu-w1-n2/playlist/amg17560-fcbarcelona-topbarcaspanish-samsunges/playlist.m3u8"),
)


def ace_id(enlace):
    match = _CID.fullmatch(enlace.strip())
    return match.group(1).lower() if match else ""


def es_web(enlace):
    try:
        partes = urlsplit(enlace)
        return partes.scheme in ("http", "https") and bool(partes.hostname)
    except ValueError:
        return False


def ruta_horus(enlace):
    cid = ace_id(enlace)
    if not cid:
        return ""
    return "plugin://%s?%s" % (HORUS, urlencode({"action": "play", "id": "acestream://" + cid}))


def ruta_catalogo_ekhorus():
    """EKHorus abre el catálogo clásico como directorio de Kodi."""
    consulta = base64.b64encode(b"{'action': 'catalogo', 'clasico': 1}")
    return "plugin://%s/?%s" % (HORUS, quote(consulta))


def datos_canal_ekhorus(enlace):
    """Valida los parámetros reproducibles de un canal que exportó EKHorus."""
    prefijo = "plugin://%s/?" % HORUS
    if not enlace.startswith(prefijo) or len(enlace) > 4096:
        return None
    try:
        item = ast.literal_eval(base64.b64decode(unquote(enlace[len(prefijo):]), validate=True).decode())
    except (ValueError, SyntaxError, binascii.Error, RecursionError):
        return None
    if not isinstance(item, dict) or item.get("action") != "play":
        return None
    for campo in ("infohash", "id"):
        valor = item.get(campo)
        cid = ace_id(valor) if isinstance(valor, str) else ""
        if cid:
            # Conserva la ruta interna y el motor elegido al exportar el canal.
            canal = {"action": "play", campo: cid, "origen": "tv"}
            if item.get("motor") == 1:
                canal["motor"] = 1
            return canal
    return None


def ruta_canal_ekhorus(enlace):
    canal = datos_canal_ekhorus(enlace)
    if canal is None:
        return ""
    return "plugin://%s/?%s" % (HORUS, quote(base64.b64encode(repr(canal).encode()).decode(), safe=""))


def ruta_exportar_ekhorus():
    consulta = base64.b64encode(b"{'action': 'tv_exportar'}").decode()
    return "plugin://%s/?%s" % (HORUS, quote(consulta, safe=""))


def paises_canal_ekhorus(ruta):
    """Lee el país por identificador de la caché local del complemento."""
    try:
        catalogo = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    filas = catalogo.get("canales") if isinstance(catalogo, dict) else None
    if not isinstance(filas, list):
        return {}
    paises = {}
    for fila in filas:
        if not isinstance(fila, dict) or not isinstance(fila.get("paises"), list):
            continue
        hash_canal = fila.get("infohash")
        if not isinstance(hash_canal, str) or not ace_id(hash_canal):
            continue
        codigos = [p for p in fila["paises"] if isinstance(p, str) and p]
        if codigos:
            paises[ace_id(hash_canal)] = " ".join(codigos)
    return paises


def inicio_evento(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        return datetime.fromisoformat(valor.strip().replace("Z", "+00:00")).astimezone()
    except (ValueError, OverflowError, OSError):
        return None
