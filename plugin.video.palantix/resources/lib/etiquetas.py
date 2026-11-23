"""Lee idioma y calidad del nombre de una fuente y ordena las fuentes según las preferencias del usuario.

Etiquetas de idioma: CAST (castellano), LAT (latino), VOSE (versión original subtitulada),
VO (versión original), DUAL / MULTI (varias pistas de audio).
"""
import re
from urllib.parse import unquote

_LAT = re.compile(r"latino|\blatin\b|\blat\b|latam|hispanoamerica", re.I)
_CAST = re.compile(r"castellano|\bcast\b|\besp\b|\bspa\b|espa[ñn]ol|spanish|\(es\)|\[es\]", re.I)
_CAST_EXPLICITO = re.compile(r"castellano|\bcast\b|\bes[-_]es\b", re.I)
_VOSE = re.compile(r"\bvose\b|\bvos\b|subtitulad|\bsubs?[ ._-]?esp", re.I)
_DUAL = re.compile(r"\bdual\b", re.I)
_MULTI = re.compile(r"\bmulti\b", re.I)
_VO = re.compile(r"\bvo\b|\benglish\b|\beng\b", re.I)
_NOMBRES_IDIOMA = {"LAT": "Latino", "CAST": "Castellano", "VOSE": "VOSE",
                   "VO": "Versión original", "DUAL": "Audio dual", "MULTI": "Multiaudio"}
_TAMANO = re.compile(r"(?<!\w)([0-9]+(?:[.,][0-9]+)?)\s*(GiB|MiB|TiB|GB|MB|TB)\b", re.I)
_UNIDADES = {"gib": "GiB", "mib": "MiB", "tib": "TiB"}

_CALIDAD = [
    ("4K", re.compile(r"2160p|\b4k\b|\buhd\b", re.I)),
    ("1080p", re.compile(r"1080[pi]?\b|\bfhd\b", re.I)),
    ("720p", re.compile(r"720p?\b|\bhd\b", re.I)),
    ("SD", re.compile(r"480p|576p|\bsd\b|dvdrip|xvid|\bdivx\b", re.I)),
]
_RANGO = {"4K": 4, "1080p": 3, "720p": 2, "SD": 1, "": 2}  # sin dato: lo tratamos como 720p
_EXTRAS = [
    ("DV", re.compile(r"dolby[ ._-]?vision|\bdv\b|\bdovi\b", re.I)),
    ("HDR", re.compile(r"\bhdr(10)?\+?\b", re.I)),
    ("REMUX", re.compile(r"remux", re.I)),
    ("HEVC", re.compile(r"x265|hevc|h\.?265", re.I)),
    ("CAM", re.compile(r"\bcam(rip)?\b|\bhdcam\b|\bts\b|telesync|\btc\b|telecine", re.I)),
]


def analizar(*textos):
    """Devuelve {'idiomas': [...], 'calidad': '1080p', 'extras': [...]} a partir de los textos dados."""
    t = " ".join(unquote(x or "") for x in textos)
    t = re.sub(r"[._]", " ", t)
    idiomas = []
    if _LAT.search(t):
        idiomas.append("LAT")
    # «Spanish»/«Español» sin más suele ser castellano; si ya pone latino, no lo duplicamos
    castellano = _CAST_EXPLICITO.search(t)
    if castellano or (_CAST.search(_LAT.sub(" ", t)) and not idiomas):
        idiomas.append("CAST")
    for etiqueta, rx in (("VOSE", _VOSE), ("DUAL", _DUAL), ("MULTI", _MULTI), ("VO", _VO)):
        if rx.search(t):
            idiomas.append(etiqueta)
    calidad = next((c for c, rx in _CALIDAD if rx.search(t)), "")
    extras = [e for e, rx in _EXTRAS if rx.search(t)]
    return {"idiomas": idiomas, "calidad": calidad, "extras": extras}


def _nota_idioma(idiomas, preferido):
    if not preferido:
        return 2
    if preferido in idiomas:
        return 3
    if preferido in ("CAST", "LAT") and ({"DUAL", "MULTI"} & set(idiomas)):
        return 2  # probablemente trae la pista en español
    if not idiomas:
        return 1  # no se sabe
    return 0      # otro idioma


def ordenar(fuentes, idioma="", calidad_max="4K", solo_idioma=False,
            prioridad_idiomas=(), calidad_primero=False):
    """Devuelve [(fuente, analisis)] de mejor a peor. Las CAM van siempre al final."""
    tope = _RANGO.get(calidad_max, 4)
    salida = []
    for f in fuentes:
        a = analizar(getattr(f, "idioma", ""), f.etiqueta, f.calidad, f.url.rsplit("/", 1)[-1])
        nota_idioma = _nota_idioma(a["idiomas"], idioma)
        if solo_idioma and idioma and nota_idioma == 0:
            continue
        if prioridad_idiomas:
            nota_idioma = max(
                (len(prioridad_idiomas) + 2 - n for n, codigo in enumerate(prioridad_idiomas)
                 if codigo in a["idiomas"]),
                default=2 if nota_idioma == 2 else int(bool(a["idiomas"])),
            )
        rango = _RANGO.get(a["calidad"], 0 if calidad_primero else 2)
        calidad = (rango <= tope, rango)
        prioridades = (*calidad, nota_idioma) if calidad_primero else (nota_idioma, *calidad)
        clave = ("CAM" not in a["extras"], *prioridades,
                 "HDR" in a["extras"] or "DV" in a["extras"])
        salida.append((clave, f, a))
    salida.sort(key=lambda x: x[0], reverse=True)
    return [(f, a) for _, f, a in salida]


def texto_etiquetas(a):
    partes = ["[%s]" % i for i in a["idiomas"]]
    if a["calidad"]:
        partes.append("[%s]" % a["calidad"])
    partes += ["[%s]" % e for e in a["extras"] if e != "HEVC"]
    return " ".join(partes)


def resumen_fuente(fuente, analisis):
    """Datos breves para la primera línea del selector de Kodi."""
    texto = unquote(" ".join((fuente.idioma, fuente.etiqueta, fuente.url.rsplit("/", 1)[-1])))
    idiomas = ["Español" if i == "CAST" and not _CAST_EXPLICITO.search(texto) else _NOMBRES_IDIOMA[i]
               for i in analisis["idiomas"]]
    tamano = _TAMANO.search(fuente.etiqueta)
    peso = "%s %s" % (tamano[1], _UNIDADES.get(tamano[2].lower(), tamano[2].upper())) if tamano else ""
    audio = " / ".join(idiomas) or "Idioma sin indicar"
    return " · ".join(filter(None, (audio, analisis["calidad"], formato_video(fuente.url, fuente.etiqueta), peso)))


def formato_video(url, etiqueta):
    """Contenedor anunciado por el proveedor o visible en la ruta."""
    patron = r"(?:\.|\b)(mkv|mp4|webm|m3u8|mpd|avi|mov|m4v)(?=\b)"
    encontrado = re.search(patron, etiqueta + " " + unquote(url.split("?", 1)[0]), re.I)
    return encontrado[1].upper() if encontrado else ""
