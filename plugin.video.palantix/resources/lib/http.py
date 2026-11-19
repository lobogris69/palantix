"""Peticiones HTTP mínimas con la librería estándar (sin dependencias externas)."""
import json
import urllib.request
from urllib.parse import urlencode

AGENTE = "Palantix/0.3"


class _RedireccionHTTPS(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise ValueError("El complemento debe usar HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def get_json(url, params=None, timeout=15, cabeceras=None, https_only=False):
    if params:
        url = url + ("&" if "?" in url else "?") + urlencode(params)
    c = {"User-Agent": AGENTE, "Accept": "application/json"}
    c.update(cabeceras or {})
    req = urllib.request.Request(url, headers=c)
    abrir = urllib.request.build_opener(_RedireccionHTTPS()).open if https_only else urllib.request.urlopen
    with abrir(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
