"""Conector EXPERIMENTAL con AllDebrid (API v4/v4.1, https://docs.alldebrid.com/).

Convierte enlaces de alojamientos de ficheros (y magnets que ya estén listos en AllDebrid)
en enlaces directos reproducibles, usando la cuenta del propio usuario.
Solo librería estándar: se puede probar fuera de Kodi.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlparse

from .http import AGENTE

API = "https://api.alldebrid.com"
VIDEO = (".mkv", ".mp4", ".avi", ".m4v", ".mov", ".webm", ".ts", ".m2ts", ".wmv", ".mpg", ".mpeg")

MENSAJES = {  # traducción de los códigos de error más habituales
    "AUTH_MISSING_APIKEY": "Falta la clave de AllDebrid",
    "AUTH_BAD_APIKEY": "La clave de AllDebrid no es válida",
    "AUTH_BLOCKED": "AllDebrid pide confirmar este acceso desde tu correo",
    "AUTH_USER_BANNED": "Cuenta de AllDebrid bloqueada",
    "LINK_DOWN": "El enlace ya no existe en el alojamiento",
    "LINK_PASS_PROTECTED": "El enlace tiene contraseña",
    "LINK_HOST_NOT_SUPPORTED": "AllDebrid no admite ese alojamiento",
    "LINK_TEMPORARY_UNAVAILABLE": "El alojamiento no responde ahora mismo",
    "MUST_BE_PREMIUM": "Hace falta cuenta premium de AllDebrid",
    "FREE_TRIAL_LIMIT_REACHED": "Se acabó la prueba gratuita de AllDebrid",
    "MAGNET_MUST_BE_PREMIUM": "Los magnets requieren cuenta premium",
    "MAGNET_INVALID_URI": "Magnet no válido",
    "MAGNET_TOO_MANY_ACTIVE": "Demasiados magnets activos en tu cuenta",
    "PIN_EXPIRED": "El PIN ha caducado, vuelve a intentarlo",
}


class AllDebridError(Exception):
    def __init__(self, codigo, mensaje=""):
        self.codigo = codigo
        super().__init__(MENSAJES.get(codigo, mensaje or codigo))


class NoListo(Exception):
    """El magnet no está descargado aún en AllDebrid (no hay reproducción instantánea)."""


class AllDebrid:
    def __init__(self, apikey="", log=print, espera=time.sleep):
        self.apikey = (apikey or "").strip()
        self.log = log
        self.espera = espera  # inyectable para pruebas

    # ------------------------------------------------------------ transporte
    def _req(self, ruta, params=None, metodo="POST", auth=True):
        cabeceras = {"User-Agent": AGENTE, "Accept": "application/json"}
        if auth:
            if not self.apikey:
                raise AllDebridError("AUTH_MISSING_APIKEY")
            cabeceras["Authorization"] = "Bearer " + self.apikey
        cuerpo = urlencode(params or {}, doseq=True)
        url = API + ruta
        if metodo == "GET":
            url += ("?" + cuerpo) if cuerpo else ""
            datos = None
        else:
            datos = cuerpo.encode()
            cabeceras["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=datos, headers=cabeceras, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                resp = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:  # la API también devuelve JSON con 4xx
            try:
                resp = json.loads(e.read().decode("utf-8"))
            except ValueError:
                raise AllDebridError("HTTP_%d" % e.code, "AllDebrid respondió %d" % e.code)
        if resp.get("status") != "success":
            err = resp.get("error") or {}
            raise AllDebridError(err.get("code", "DESCONOCIDO"), err.get("message", ""))
        return resp.get("data") or {}

    # ------------------------------------------------------------ cuenta
    def pin_get(self):
        """Devuelve {'pin', 'check', 'user_url', 'expires_in'}."""
        return self._req("/v4.1/pin/get", metodo="GET", auth=False)

    def pin_check(self, pin, check):
        """Devuelve la apikey si ya está activado, o None si aún no."""
        d = self._req("/v4/pin/check", {"pin": pin, "check": check}, auth=False)
        if d.get("activated") and d.get("apikey"):
            self.apikey = d["apikey"]
            return d["apikey"]
        return None

    def usuario(self):
        return self._req("/v4/user", metodo="GET").get("user", {})

    # ------------------------------------------------------------ alojamientos
    def dominios(self, cache_dir=None, ttl=86400):
        """Dominios que AllDebrid sabe desbloquear (lista pública, en caché 24 h)."""
        cache = os.path.join(cache_dir, "alldebrid_hosts.json") if cache_dir else None
        if cache and os.path.exists(cache) and time.time() - os.path.getmtime(cache) < ttl:
            with open(cache, encoding="utf-8") as f:
                return set(json.load(f))
        d = self._req("/v4/hosts/domains", metodo="GET", auth=False)
        doms = set(d.get("hosts", [])) | set(d.get("streams", [])) | set(d.get("redirectors", []))
        if cache:
            os.makedirs(cache_dir, exist_ok=True)
            with open(cache, "w", encoding="utf-8") as f:
                json.dump(sorted(doms), f)
        return doms

    @staticmethod
    def necesita(url, dominios):
        """¿Hay que pasar esta URL por AllDebrid?"""
        if url.startswith("magnet:"):
            return True
        host = (urlparse(url).hostname or "").lower()
        partes = host.split(".")
        return any(".".join(partes[i:]) in dominios for i in range(len(partes) - 1))

    # ------------------------------------------------------------ desbloqueo
    def desbloquear(self, enlace, password="", cancelado=lambda: False, max_espera=120):
        """Enlace de alojamiento -> enlace directo. Gestiona la generación diferida."""
        params = {"link": enlace}
        if password:
            params["password"] = password
        d = self._req("/v4/link/unlock", params)
        if d.get("link"):
            return d["link"], d.get("filename", "")
        if not d.get("delayed"):
            raise AllDebridError("SIN_ENLACE", "AllDebrid no devolvió enlace")
        inicio = time.time()
        while time.time() - inicio < max_espera:
            if cancelado():
                raise AllDebridError("CANCELADO", "Cancelado")
            self.espera(5)  # la API pide no consultar más de una vez cada 5 s
            r = self._req("/v4/link/delayed", {"id": d["delayed"]})
            if r.get("status") == 2 and r.get("link"):
                return r["link"], d.get("filename", "")
            if r.get("status") == 3:
                raise AllDebridError("DELAYED_ERROR", "AllDebrid no pudo generar el enlace")
        raise AllDebridError("TIEMPO", "AllDebrid tardó demasiado")

    def magnet(self, uri):
        """Magnet -> lista de (nombre, tamaño, enlace) de vídeos, si ya está listo en AllDebrid."""
        subido = self._req("/v4/magnet/upload", {"magnets[]": [uri]}).get("magnets", [{}])[0]
        if subido.get("error"):
            e = subido["error"]
            raise AllDebridError(e.get("code", "MAGNET"), e.get("message", ""))
        if not subido.get("ready"):
            raise NoListo("El magnet se está descargando en AllDebrid; prueba más tarde")
        res = self._req("/v4/magnet/files", {"id[]": [subido["id"]]}).get("magnets", [{}])[0]
        if res.get("error"):
            e = res["error"]
            raise AllDebridError(e.get("code", "MAGNET"), e.get("message", ""))
        videos = [f for f in _aplanar(res.get("files", [])) if f[0].lower().endswith(VIDEO)]
        videos = [v for v in videos if not re.search(r"\bsample\b", v[0], re.I)] or videos
        return sorted(videos, key=lambda v: -v[1])


def _aplanar(nodos, ruta=""):
    """El árbol de ficheros de AllDebrid usa n=nombre, s=tamaño, l=enlace, e=hijos."""
    for n in nodos:
        nombre = (ruta + "/" if ruta else "") + n.get("n", "")
        if "e" in n:
            yield from _aplanar(n["e"], nombre)
        elif n.get("l"):
            yield nombre, int(n.get("s") or 0), n["l"]
