"""Peticiones HTTP mínimas con la librería estándar (sin dependencias externas)."""
import json
import urllib.request
from urllib.parse import urlencode

AGENTE = "Palantix/0.2"


def get_json(url, params=None, timeout=15):
    if params:
        url = url + ("&" if "?" in url else "?") + urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
