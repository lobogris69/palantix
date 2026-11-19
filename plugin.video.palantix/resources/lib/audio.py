"""Identifica pistas de audio con los metadatos que devuelve Kodi."""
import re
import unicodedata

_LATINO = re.compile(r"\b(?:latino(?:america(?:no)?)?|latin american|latam|castellano latino)\b")
_CASTELLANO = re.compile(r"\b(?:castellano|castilian|espanol de espana|spanish (?:spain|european)|european spanish)\b")
_ESPANOL = re.compile(r"\b(?:espanol|spanish)\b")


def idioma(pista):
    codigo = pista.get("language", "").lower().replace("_", "-")
    nombre = unicodedata.normalize("NFKD", pista.get("name", "").lower())
    nombre = nombre.encode("ascii", "ignore").decode()
    if codigo in {"es-419", "es-mx"} or _LATINO.search(nombre):
        return "LAT"
    if codigo == "es-es" or _CASTELLANO.search(nombre):
        return "CAST"
    if codigo in {"es", "spa", "esp"} or codigo.startswith("es-") or _ESPANOL.search(nombre):
        return "ES"
    return ""


def pista_preferida(pistas, prioridad, actual):
    """Usa pistas explícitas antes que una pista española sin región identificada."""
    if len(pistas) < 2 or not prioridad or prioridad[0] not in {"LAT", "CAST"}:
        return None

    for preferido in [p for p in prioridad if p in {"LAT", "CAST"}] + ["ES"]:
        indices = [p["index"] for p in pistas if idioma(p) == preferido]
        if indices:
            return actual if actual in indices else indices[0]
    return None
