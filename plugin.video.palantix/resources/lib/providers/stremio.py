"""Fuentes de un complemento Stremio configurado por el usuario."""
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from .. import http
from .base import Fuente, Proveedor

_FORMATO = re.compile(r"\.(mkv|mp4|webm|avi|mov|m4v|ts|m3u8|mpd|wmv)\b", re.I)


def _url_http(url, protocolos):
    if not isinstance(url, str) or any(c.isspace() or c in "|\\" for c in url):
        return None
    try:
        partes = urlsplit(url)
        if (partes.scheme in protocolos and partes.hostname
                and partes.username is None and not partes.fragment):
            return partes
    except ValueError:
        pass
    return None


def _texto(valor):
    if isinstance(valor, str):
        return " ".join(valor.replace("[", "(").replace("]", ")").split())[:240]
    return ""


class PausaPelis(OSError):
    def __init__(self, segundos, del_proveedor=False):
        minutos = max(1, int((segundos + 59) // 60))
        motivo = "bloqueo comunicado por Pelis" if del_proveedor else "límite de consultas de Palantix"
        super().__init__("%s, vuelve a probar en %d min" % (motivo, minutos))


def motivo_error(error):
    """Texto para la interfaz sin mostrar la URL privada del complemento."""
    if isinstance(error, PausaPelis):
        return str(error)
    if isinstance(error, HTTPError):
        motivos = {401: "configuración rechazada", 403: "acceso denegado",
                   404: "ruta no disponible", 429: "demasiadas peticiones"}
        return "HTTP %d%s" % (error.code, " · " + motivos[error.code] if error.code in motivos else "")
    if isinstance(error, TimeoutError) or (isinstance(error, URLError) and isinstance(error.reason, TimeoutError)):
        return "tiempo de espera agotado"
    if isinstance(error, sqlite3.Error):
        return "no se pudo consultar el límite local"
    if isinstance(error, ValueError):
        return "configuración o respuesta inválida"
    return "error de conexión o de respuesta"


class Stremio(Proveedor):
    id = "stremio"

    def __init__(self, manifiesto, numero, log=print, fallo=lambda proveedor: None, cache=None, segundo_plano=False):
        self.manifiesto = manifiesto
        self.nombre = "Stremio %d" % numero
        self.log = log
        self.fallo = fallo
        self.cache = Path(cache) if cache else None
        self.limite_pelis = 35 if segundo_plano else 50
        self._manifiesto = None
        self._bloqueo_manifiesto = Lock()

    def _pedir(self, url):
        host = urlsplit(url).hostname or ""
        if self.cache is None or not (host == "pelis-addon.com" or host.endswith(".pelis-addon.com")):
            return http.get_json(url, timeout=8, https_only=True)

        ahora = time.time()
        self.cache.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(self.cache / "stremio-pelis.sqlite"))) as db:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS peticiones (fecha REAL)")
                db.execute("CREATE TABLE IF NOT EXISTS bloqueos (hasta REAL)")
                db.execute("DELETE FROM peticiones WHERE fecha <= ?", (ahora - 600,))
                db.execute("DELETE FROM bloqueos WHERE hasta <= ?", (ahora,))
                hasta = db.execute("SELECT max(hasta) FROM bloqueos").fetchone()[0]
                if hasta is not None:
                    raise PausaPelis(hasta - ahora, del_proveedor=True)
                cantidad, primera = db.execute("SELECT count(*), min(fecha) FROM peticiones").fetchone()
                if cantidad >= self.limite_pelis:
                    raise PausaPelis(primera + 600 - ahora)
                db.execute("INSERT INTO peticiones VALUES (?)", (ahora,))
            try:
                return http.get_json(url, timeout=8, https_only=True)
            except HTTPError as error:
                if error.code == 429:
                    retry = (error.headers or {}).get("Retry-After", "")
                    try:
                        espera = int(retry) if retry.isdigit() else (
                            parsedate_to_datetime(retry).astimezone(timezone.utc) -
                            datetime.now(timezone.utc)).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        espera = 86400
                    with db:
                        db.execute("INSERT INTO bloqueos VALUES (?)", (time.time() + max(600, espera),))
                raise

    def buscar(self, peli):
        if not re.fullmatch(r"tt[0-9]+", peli.imdb_id):
            return []
        tipo, video = "movie", peli.imdb_id
        if peli.tipo == "episodio":
            tipo = "series"
            video += ":%d:%d" % (peli.temporada, peli.episodio)
        try:
            return self._buscar(tipo, video)
        except (OSError, ValueError, TypeError, sqlite3.Error) as error:
            aviso = "%s (%s)" % (self.nombre, motivo_error(error))
            self.fallo(aviso)
            self.log("[Palantix] " + aviso)
            return []

    def leer_manifiesto(self):
        partes = _url_http(self.manifiesto, ("https",))
        if not partes or not partes.path.endswith("/manifest.json"):
            raise ValueError("URL de manifiesto inválida")
        with self._bloqueo_manifiesto:
            if self._manifiesto is None:
                manifiesto = self._pedir(self.manifiesto)
                if not isinstance(manifiesto, dict) or not isinstance(manifiesto.get("resources"), list):
                    raise ValueError("Manifiesto inválido")
                self._manifiesto = manifiesto
            return partes, self._manifiesto

    def _buscar(self, tipo, video):
        partes, manifiesto = self.leer_manifiesto()
        if not self._admite(manifiesto, tipo, video):
            return []
        ruta = partes.path[:-len("manifest.json")] + "stream/%s/%s.json" % (tipo, quote(video, safe=":"))
        respuesta = self._pedir(urlunsplit(partes._replace(path=ruta)))
        if not isinstance(respuesta, dict) or not isinstance(respuesta.get("streams"), list):
            raise ValueError("Respuesta de streams inválida")
        nombre = _texto(manifiesto.get("name")) or self.nombre
        fuentes = []
        for item in respuesta["streams"]:
            fuente = self._fuente(item, nombre)
            if fuente is not None:
                fuentes.append(fuente)
        return fuentes

    @staticmethod
    def _admite(manifiesto, tipo, video):
        recursos = manifiesto.get("resources")
        if not isinstance(recursos, list):
            return False
        for recurso in recursos:
            if recurso == "stream":
                recurso = {}
            elif not isinstance(recurso, dict) or recurso.get("name") != "stream":
                continue
            tipos = recurso.get("types", manifiesto.get("types", []))
            prefijos = recurso.get("idPrefixes", manifiesto.get("idPrefixes", []))
            if (isinstance(tipos, list) and tipo in tipos and isinstance(prefijos, list)
                    and (not prefijos or any(isinstance(p, str) and video.startswith(p) for p in prefijos))):
                return True
        return False

    @staticmethod
    def _fuente(item, proveedor):
        if not isinstance(item, dict):
            return None
        hints = item.get("behaviorHints")
        if not isinstance(hints, dict):
            hints = {}
        if hints.get("proxyHeaders"):
            return None
        archivo = _texto(hints.get("filename"))
        url = item.get("url")
        partes = _url_http(url, ("https", "http"))
        if not partes:
            hash_bt = item.get("infoHash")
            if not isinstance(hash_bt, str) or not re.fullmatch(r"[a-fA-F0-9]{40}", hash_bt):
                return None
            url = "magnet:?xt=urn:btih:" + hash_bt.lower()
        nombre = _texto(item.get("name"))
        descripcion = _texto(item.get("description") or item.get("title"))
        texto = " · ".join(dict.fromkeys(t for t in (nombre, descripcion, archivo) if t))
        formato = (_FORMATO.search(archivo)
                   or _FORMATO.search(unquote(partes.path) if partes else "")
                   or _FORMATO.search(texto))
        if formato:
            texto = " · ".join(filter(None, (texto, formato[1].upper())))
        return Fuente(texto or "Fuente de vídeo", url, proveedor=proveedor,
                      archivo=archivo if partes is None else "", privada=True)
