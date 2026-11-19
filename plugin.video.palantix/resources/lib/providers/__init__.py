"""Registro de proveedores. Se consultan todos en paralelo y se juntan los resultados."""
from concurrent.futures import ThreadPoolExecutor

from .archive_org import ArchiveOrg
from .base import Fuente, Peli, Proveedor  # noqa: F401  (reexportados)
from .lista_url import ListaURL  # noqa: F401

# Proveedores fijos. Los que dependen de ajustes (Mis listas) se pasan en `extra`.
PROVEEDORES = [
    ArchiveOrg(),
]


def buscar_fuentes(peli, activo=lambda prov_id: True, log=print, extra=(), fallo=lambda proveedor: None):
    """Lanza la búsqueda en todos los proveedores activos a la vez.

    `activo` decide por id si un proveedor está encendido (en Kodi lo lee de los ajustes).
    Un proveedor que falle no tumba a los demás: se registra y se sigue.
    """
    elegidos = list(extra) + [p for p in PROVEEDORES if activo(p.id)]
    if not elegidos:
        return []

    def _uno(prov):
        try:
            return prov.buscar(peli)
        except Exception as e:  # una fuente caída no debe romper la app
            fallo(prov.nombre)
            log("[Palantix] %s falló: %s" % (prov.nombre, type(e).__name__))
            return []

    with ThreadPoolExecutor(max_workers=len(elegidos)) as pool:
        resultados = pool.map(_uno, elegidos)
    return [f for lista in resultados for f in lista]
