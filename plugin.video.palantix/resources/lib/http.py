"""Peticiones HTTP mínimas con la librería estándar (sin dependencias externas)."""
import json
import urllib.request
from urllib.parse import urlencode

AGENTE = "Palantix/0.3"


def get_json(url, params=None, timeout=15, cabeceras=None):
    if params:
        url = url + ("&" if "?" in url else "?") + urlencode(params)
    c = {"User-Agent": AGENTE, "Accept": "application/json"}
    c.update(cabeceras or {})
    req = urllib.request.Request(url, headers=c)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
