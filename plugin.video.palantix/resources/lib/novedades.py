"""Novedades de las series en seguimiento: capítulos pendientes y capítulos NUEVOS.

- pendientes: capítulos ya emitidos que quedan por ver.
- nuevo: ha salido algún capítulo DESPUÉS de la última vez que viste la serie.
Se guarda en novedades.json (caché de 6 h) para que los menús abran al instante;
el servicio lo refresca solo y avisa cuando aparece un capítulo nuevo.
"""
import json
import os
import time

from . import seguimiento

TTL = 6 * 3600
ESTADOS_VISTA = {"nuevo": "Nuevo", "al_dia": "Al día", "terminada": "Terminada"}


def estado_vista(datos):
    if datos.get("pendientes"):
        return "nuevo"
    if not (datos.get("ultimo") or {}).get("e"):
        return ""
    return "al_dia" if datos.get("en_emision") else "terminada"


def _ruta(perfil):
    return os.path.join(perfil, "novedades.json")


def leer(perfil):
    try:
        with open(_ruta(perfil), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _guardar(perfil, datos):
    os.makedirs(perfil, exist_ok=True)
    with open(_ruta(perfil), "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)


def estado(t, sid, s, e, fecha_visto, historial=None):
    """Calcula los capítulos emitidos que quedan pendientes, incluidos los saltados."""
    serie = t.serie(sid)
    ultimo = serie.get("last_episode_to_air") or {}
    prox = serie.get("next_episode_to_air") or {}
    ult = (int(ultimo.get("season_number") or 0), int(ultimo.get("episode_number") or 0))
    caps = {x["season_number"]: int(x.get("episode_count") or 0) for x in serie.get("seasons", []) if x["season_number"] > 0}
    historial = historial or {"s": s, "e": e}
    restantes = []
    for temp in range(1, ult[0] + 1):
        hasta = ult[1] if temp == ult[0] else caps.get(temp, 0)
        restantes.extend((temp, ep) for ep in range(1, hasta + 1) if not seguimiento.esta_visto(historial, temp, ep))

    siguiente = None
    if restantes:
        temp, ep = restantes[0]
        try:
            episodios = t.temporada(sid, temp).get("episodes", [])
        except Exception:
            episodios = []
        ficha = next((x for x in episodios if x["episode_number"] == ep), {})
        siguiente = {"s": temp, "e": ep, "nombre": ficha.get("name") or "",
                     "still": ficha.get("still_path") or "", "emitido": ficha.get("air_date") or "",
                     "sinopsis": ficha.get("overview") or ""}

    pendientes = len(restantes)
    visto_dia = time.strftime("%Y-%m-%d", time.localtime(fecha_visto or 0))
    return {
        "pendientes": pendientes,
        "episodios_pendientes": restantes,
        "nuevo": bool(pendientes and (ultimo.get("air_date") or "") > visto_dia),
        "ultimo": {"s": ult[0], "e": ult[1], "emitido": ultimo.get("air_date") or ""},
        "proximo": {"s": prox.get("season_number"), "e": prox.get("episode_number"), "emitido": prox.get("air_date")}
        if prox else None,
        "siguiente": siguiente,
        "en_emision": serie.get("in_production", False) or bool(prox),
        "comprobado": time.time(),
    }


def refrescar(perfil, t, forzar=False, log=print, vistos_trakt=None):
    """Recalcula las series en seguimiento caducadas. Devuelve [(titulo, ultimo)] de las que tienen capítulo NUEVO
    que antes no estaba (para avisar)."""
    antes = leer(perfil)
    ahora = dict(antes)
    recien = []
    for sid, d in seguimiento.ordenadas(perfil):
        previo = antes.get(sid)
        vistos = (vistos_trakt or {}).get(sid, [])
        revision = [d.get("s"), d.get("e"), d.get("legado"), d.get("vistos"), d.get("no_vistos"), d.get("fecha"), vistos]
        if not forzar and previo and time.time() - previo.get("comprobado", 0) < TTL \
                and previo.get("revision") == revision:
            continue
        try:
            historial = seguimiento.con_historial_trakt(d, vistos)
            est = estado(t, int(sid), int(d["s"]), int(d["e"]), d.get("fecha"), historial)
        except Exception as ex:
            log("[Palantix] novedades de %s: %s" % (d.get("titulo"), ex))
            continue
        est["revision"] = revision
        ahora[sid] = est
        if previo and est["ultimo"] != previo.get("ultimo") and est["pendientes"]:
            recien.append((d.get("titulo", ""), est["ultimo"]))
    for sid in list(ahora):  # series que ya no se siguen
        if sid not in dict(seguimiento.ordenadas(perfil)):
            ahora.pop(sid)
    _guardar(perfil, ahora)
    return recien


def resumen(perfil):
    """(series con capítulo nuevo, series con pendientes) leyendo solo la caché (instantáneo)."""
    datos = leer(perfil)
    return (sum(1 for x in datos.values() if x.get("nuevo")),
            sum(1 for x in datos.values() if x.get("pendientes")))
