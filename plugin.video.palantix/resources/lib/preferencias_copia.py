"""Formato portátil de preferencias de Palantix."""
import json
import re

BOOLEANAS = (
    "inicio_plataforma", "solo_peliculas_con_fuentes", "recordar_busquedas", "mostrar_etiquetas",
    "solo_idioma", "autoplay", "intro_activo", "siguiente_activo", "aviso_novedades",
    "ocultar_al_dia", "comprobar_fuentes_episodios", "auto_actualizar",
)
MAX_INDICE = {
    "idioma_cat": 6, "vista_listados": 3, "orden_listas": 3, "paginas": 2,
    "color_etiquetas": 6, "idioma_pref": 4, "orden_fuentes": 1, "calidad_max": 2, "subs_modo": 2,
}
LIMITES = {"umbral_visto": (50, 95), "siguiente_seg": (10, 120)}
CLAVES = (*BOOLEANAS, *MAX_INDICE, *LIMITES, "prioridad_idiomas", "subs_idiomas")
MAX_BYTES = 8192


def _valida(clave, valor):
    if not isinstance(valor, str):
        return False
    if clave in BOOLEANAS:
        return valor in ("true", "false")
    if clave in MAX_INDICE or clave in LIMITES:
        minimo, maximo = LIMITES[clave] if clave in LIMITES else (0, MAX_INDICE[clave])
        return bool(re.fullmatch(r"[0-9]{1,3}", valor)) and minimo <= int(valor) <= maximo
    if clave == "prioridad_idiomas":
        codigos = valor.split(",")
        return not valor or (len(codigos) == len(set(codigos))
                             and set(codigos) <= {"CAST", "LAT", "VOSE", "VO"})
    return bool(re.fullmatch(r"[a-z]{2,3}(?:-[a-zA-Z]{2,4})?(?:\s*,\s*[a-z]{2,3}(?:-[a-zA-Z]{2,4})?)*", valor))


def exportar(leer):
    ajustes = {k: leer(k) for k in CLAVES}
    return json.dumps({"formato": 1, "preferencias": {k: v for k, v in ajustes.items() if _valida(k, v)}},
                      ensure_ascii=False, indent=2)


def importar(texto):
    if len(texto.encode("utf-8")) > MAX_BYTES:
        raise ValueError("El archivo supera el tamaño permitido.")
    documento = json.loads(texto)
    if not isinstance(documento, dict) or documento.get("formato") != 1:
        raise ValueError("El archivo no tiene el formato de preferencias de Palantix.")
    ajustes = documento.get("preferencias")
    if not isinstance(ajustes, dict) or not ajustes:
        raise ValueError("El archivo no contiene preferencias de Palantix.")
    if any(k not in CLAVES or not _valida(k, v) for k, v in ajustes.items()):
        raise ValueError("El archivo contiene una preferencia desconocida o no válida.")
    return ajustes
