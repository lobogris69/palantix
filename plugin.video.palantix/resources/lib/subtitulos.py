"""Subtítulos automáticos con la API REST de OpenSubtitles (api.opensubtitles.com/api/v1).

Necesita una clave de API gratuita (opensubtitles.com > Mi cuenta > API consumers).
Usuario y contraseña son opcionales: sin ellos hay pocas descargas al día; con ellos, más.
Solo librería estándar: se puede probar fuera de Kodi.
"""
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlencode

API = "https://api.opensubtitles.com/api/v1"
AGENTE = "Palantix v0.3"


class SubError(Exception):
    pass


class OpenSubtitles:
    def __init__(self, api_key, usuario="", clave="", log=print):
        self.key, self.usuario, self.clave, self.log = (api_key or "").strip(), usuario, clave, log
        self.token, self.base = None, API

    def _pedir(self, metodo, ruta, params=None, cuerpo=None):
        if not self.key:
            raise SubError("Falta la clave de OpenSubtitles")
        url = self.base + ruta + (("?" + urlencode(params)) if params else "")
        cab = {"Api-Key": self.key, "User-Agent": AGENTE, "Accept": "application/json"}
        datos = None
        if cuerpo is not None:
            datos = json.dumps(cuerpo).encode()
            cab["Content-Type"] = "application/json"
        if self.token:
            cab["Authorization"] = "Bearer " + self.token
        req = urllib.request.Request(url, data=datos, headers=cab, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8")).get("message", "")
            except ValueError:
                msg = ""
            if e.code == 406 or "quota" in msg.lower() or "remaining" in msg.lower():
                raise SubError("Se acabaron las descargas de subtítulos de hoy")
            if e.code in (401, 403):
                raise SubError("OpenSubtitles rechaza la clave o el usuario")
            raise SubError("OpenSubtitles: %s" % (msg or e.code))

    def entrar(self):
        if self.token or not (self.usuario and self.clave):
            return
        r = self._pedir("POST", "/login", cuerpo={"username": self.usuario, "password": self.clave})
        self.token = r.get("token")
        if r.get("base_url"):  # las cuentas VIP usan otro servidor
            self.base = "https://%s/api/v1" % r["base_url"].replace("https://", "").rstrip("/")

    def buscar(self, tmdb_id, idiomas="es", temporada=0, episodio=0):
        """Lista de subtítulos, los mejores primero: [{file_id, idioma, nombre, descargas}]"""
        if temporada and episodio:
            params = {"parent_tmdb_id": tmdb_id, "season_number": temporada, "episode_number": episodio}
        else:
            params = {"tmdb_id": tmdb_id}
        params["languages"] = idiomas
        r = self._pedir("GET", "/subtitles", params)
        salida = []
        for d in r.get("data", []):
            a = d.get("attributes", {})
            for f in a.get("files", []):
                salida.append({"file_id": f.get("file_id"), "idioma": a.get("language", ""),
                               "nombre": a.get("release") or f.get("file_name") or "",
                               "descargas": int(a.get("download_count") or 0),
                               "ia": bool(a.get("ai_translated") or a.get("machine_translated"))})
        # traducciones automáticas al final; luego por popularidad
        return sorted(salida, key=lambda s: (s["ia"], -s["descargas"]))

    def descargar(self, file_id, carpeta, nombre="sub"):
        self.entrar()
        r = self._pedir("POST", "/download", cuerpo={"file_id": file_id})
        enlace = r.get("link")
        if not enlace:
            raise SubError("OpenSubtitles no dio enlace de descarga")
        os.makedirs(carpeta, exist_ok=True)
        limpio = re.sub(r"[^\w.-]+", "_", nombre)[:60] or "sub"
        ruta = os.path.join(carpeta, "%s.%s.srt" % (limpio, file_id))
        req = urllib.request.Request(enlace, headers={"User-Agent": AGENTE})
        with urllib.request.urlopen(req, timeout=30) as resp, open(ruta, "wb") as f:
            f.write(resp.read())
        self.log("[Palantix] subtítulo descargado (%s restantes hoy)" % r.get("remaining", "?"))
        return ruta


def hace_falta(modo, idiomas_fuente, idioma_pref):
    """¿Buscar subtítulos? modo: 0 nunca, 1 si el audio no es el preferido, 2 siempre."""
    if modo == 2:
        return True
    if modo == 0:
        return False
    if idioma_pref in ("CAST", "LAT"):
        return not ({"CAST", "LAT", "DUAL", "MULTI"} & set(idiomas_fuente))
    return "VOSE" not in idiomas_fuente  # con preferencia VO/VOSE: subtítulos si no los trae ya
