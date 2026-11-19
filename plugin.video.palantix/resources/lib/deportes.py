"""Fuentes deportivas y validación de enlaces al motor Ace Stream."""
import re
from datetime import datetime
from urllib.parse import urlencode, urlsplit

HORUS = "script.module.horus"
_CID = re.compile(r"(?:acestream://)?([0-9a-f]{40})", re.I)

CANALES = (
    ("Teledeporte", "https://rtvelivestream.rtve.es/rtvesec/tdp/tdp_main.m3u8"),
    ("Esport3", "https://directes-tv-es.3catdirectes.cat/live-origin/esport3-hls/master.m3u8"),
    ("Real Madrid TV", "https://rmtv.akamaized.net/hls/live/2043153/rmtv-es-web/master.m3u8"),
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


def inicio_evento(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        return datetime.fromisoformat(valor.strip().replace("Z", "+00:00")).astimezone()
    except (ValueError, OverflowError, OSError):
        return None
