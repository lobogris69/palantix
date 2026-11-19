"""Colección de vídeos con licencia comprobada, incluida en el complemento."""
from pathlib import Path

from .. import listas
from .lista_url import ListaURL

CATALOGO = Path(__file__).resolve().parents[2] / "cine_libre.json"
TITULO = "Cine libre y documentales"


def peliculas():
    return listas.cargar(str(CATALOGO))


class CineLibre(ListaURL):
    id = "cine_libre"
    nombre = TITULO

    def __init__(self):
        super().__init__([str(CATALOGO)])
