"""Proveedor que busca la película o el capítulo pulsado dentro de las listas propias del usuario."""
import re
import unicodedata

from .. import listas
from .base import Fuente, Proveedor


def _n(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


class ListaURL(Proveedor):
    id = "listas"
    nombre = "Mis listas"

    def __init__(self, origenes, cache_dir=None, ttl=3600, log=print, fallo=lambda proveedor: None):
        self.origenes = [o for o in origenes if o and o.strip()]
        self.cache_dir, self.ttl, self.log = cache_dir, ttl, log
        self.fallo = fallo

    def buscar(self, peli):
        titulos = {_n(peli.titulo), _n(peli.titulo_original)} - {""}
        fuentes = []
        for n, origen in enumerate(self.origenes, 1):
            proveedor = self.nombre if self.id != "listas" else "Lista %d" % n
            try:
                items = listas.cargar(origen, self.cache_dir, self.ttl)
            except Exception as e:
                self.fallo(proveedor)
                self.log("[Palantix] Lista %d ilegible: %s" % (n, type(e).__name__))
                continue
            for it in items:
                if not self._coincide(it, peli, titulos):
                    continue
                fuentes.append(Fuente(
                    etiqueta="%s%s%s" % (
                        it["titulo"],
                        (" %dx%02d" % (it["temporada"], it["episodio"])) if it["tipo"] == "episodio" else "",
                        (" · " + it["calidad"]) if it["calidad"] else ""),
                    url=it["url"], calidad=it["calidad"], idioma=it["idioma"], proveedor=proveedor,
                ))
        return fuentes

    @staticmethod
    def _coincide(it, peli, titulos):
        if it["tipo"] != peli.tipo:
            return False
        if peli.tipo == "episodio" and (it["temporada"], it["episodio"]) != (peli.temporada, peli.episodio):
            return False
        if peli.tmdb_id and it["tmdb_id"]:
            return it["tmdb_id"] == peli.tmdb_id
        if peli.imdb_id and it["imdb_id"]:
            return it["imdb_id"] == peli.imdb_id
        if not ({_n(it["titulo"]), _n(it["titulo_original"])} & titulos):
            return False
        if peli.tipo == "episodio":
            return True  # el año de una serie no ayuda a distinguir capítulos
        return not (peli.anio and it["anio"] and abs(peli.anio - it["anio"]) > 1)
