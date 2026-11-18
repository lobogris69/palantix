"""Proveedor de ejemplo: Internet Archive, colección de largometrajes de dominio público."""
import re
import unicodedata

from ..http import get_json
from .base import Fuente, Proveedor

BUSQUEDA = "https://archive.org/advancedsearch.php"
METADATOS = "https://archive.org/metadata/"
DESCARGA = "https://archive.org/download/"


def _normaliza(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


class ArchiveOrg(Proveedor):
    id = "archive_org"
    nombre = "Internet Archive"

    def buscar(self, peli):
        if peli.tipo != "pelicula":  # la colección feature_films no tiene series
            return []
        fuentes = []
        vistos = set()
        for titulo in dict.fromkeys(t for t in (peli.titulo_original, peli.titulo) if t):
            for doc in self._candidatos(titulo, peli.anio):
                if doc["identifier"] in vistos:
                    continue
                vistos.add(doc["identifier"])
                fuentes.extend(self._ficheros(doc))
        return fuentes

    def _candidatos(self, titulo, anio):
        consulta = 'title:("%s") AND mediatype:(movies) AND collection:(feature_films)' % titulo.replace('"', "")
        datos = get_json(BUSQUEDA, [
            ("q", consulta), ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "year"),
            ("rows", "15"), ("output", "json"),
        ])
        buscado = _normaliza(titulo)
        for doc in datos.get("response", {}).get("docs", []):
            # Título exacto; como mucho seguido del año («The General 1926»). «Contiene» cogía otras pelis.
            resto = _normaliza(doc.get("title", ""))
            if not (resto == buscado or (resto.startswith(buscado + " ") and resto[len(buscado):].strip().isdigit())):
                continue
            try:
                anio_doc = int(str(doc.get("year", "0"))[:4])
            except ValueError:
                anio_doc = 0
            if anio and anio_doc and abs(anio_doc - anio) > 1:
                continue
            yield doc

    def _ficheros(self, doc):
        ident = doc["identifier"]
        meta = get_json(METADATOS + ident)
        salida = []
        for f in meta.get("files", []):
            nombre = f.get("name", "")
            if not nombre.lower().endswith((".mp4", ".mkv", ".ogv")):
                continue
            ancho = f.get("width") or ""
            calidad = ("%sp" % f["height"]) if f.get("height") else (f.get("format") or "")
            salida.append(Fuente(
                etiqueta="%s · %s %s" % (doc.get("title", ident), calidad, ("(%s px)" % ancho) if ancho else ""),
                url=DESCARGA + ident + "/" + nombre.replace(" ", "%20"),
                calidad=calidad,
                proveedor=self.nombre,
            ))
        # Primero MP4 (lo reproduce cualquier tele), luego el resto
        salida.sort(key=lambda s: (not s.url.lower().endswith(".mp4"), s.etiqueta))
        return salida
