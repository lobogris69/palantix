"""Fuentes de un complemento Stremio configurado por el usuario."""
import re
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


class Stremio(Proveedor):
    id = "stremio"

    def __init__(self, manifiesto, numero, log=print, fallo=lambda proveedor: None):
        self.manifiesto = manifiesto
        self.nombre = "Stremio %d" % numero
        self.log = log
        self.fallo = fallo

    def buscar(self, peli):
        if not re.fullmatch(r"tt[0-9]+", peli.imdb_id):
            return []
        tipo, video = "movie", peli.imdb_id
        if peli.tipo == "episodio":
            tipo = "series"
            video += ":%d:%d" % (peli.temporada, peli.episodio)
        try:
            return self._buscar(tipo, video)
        except (OSError, ValueError, TypeError):
            self.fallo(self.nombre)
            self.log("[Palantix] %s: no se pudo consultar el complemento" % self.nombre)
            return []

    def leer_manifiesto(self):
        partes = _url_http(self.manifiesto, ("https",))
        if not partes or not partes.path.endswith("/manifest.json"):
            raise ValueError("URL de manifiesto inválida")
        manifiesto = http.get_json(self.manifiesto, timeout=8, https_only=True)
        if not isinstance(manifiesto, dict) or not isinstance(manifiesto.get("resources"), list):
            raise ValueError("Manifiesto inválido")
        return partes, manifiesto

    def _buscar(self, tipo, video):
        partes, manifiesto = self.leer_manifiesto()
        if not self._admite(manifiesto, tipo, video):
            return []
        ruta = partes.path[:-len("manifest.json")] + "stream/%s/%s.json" % (tipo, quote(video, safe=":"))
        respuesta = http.get_json(urlunsplit(partes._replace(path=ruta)), timeout=8, https_only=True)
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
