"""Contrato que cumple cualquier proveedor de vídeo.

Para añadir una fuente nueva:
  1. Crea un fichero en esta carpeta con una clase que herede de Proveedor.
  2. Implementa buscar(peli) devolviendo una lista de Fuente.
  3. Añádela a PROVEEDORES en __init__.py y, si quieres, un interruptor
     en resources/settings.xml con id="prov_<id>".
"""
from dataclasses import dataclass, field


@dataclass
class Peli:
    """Lo que se quiere ver: una película o un capítulo (tipo="episodio").
    En los capítulos, titulo/titulo_original/tmdb_id son los de la SERIE."""
    titulo: str                 # título en el idioma del catálogo
    titulo_original: str = ""   # título original (útil para buscar)
    anio: int = 0
    tmdb_id: int = 0
    imdb_id: str = ""
    tipo: str = "pelicula"      # "pelicula" | "episodio"
    temporada: int = 0
    episodio: int = 0


@dataclass
class Fuente:
    etiqueta: str               # lo que verá el usuario en el selector
    url: str                    # URL directa reproducible por Kodi (o de alojamiento/magnet si hay Debrid)
    calidad: str = ""           # "1080p", "SD"...
    proveedor: str = ""
    idioma: str = ""            # si la fuente lo sabe seguro: "CAST", "LAT", "VOSE"...
    cabeceras: dict = field(default_factory=dict)  # se añaden a la URL con |Cabecera=valor


class Proveedor:
    id = "base"
    nombre = "Base"

    def buscar(self, peli):
        """Devuelve una lista de Fuente. Nunca debe lanzar excepción hacia fuera."""
        raise NotImplementedError
