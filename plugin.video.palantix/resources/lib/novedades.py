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
VERSION = 2
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


def estado(t, sid, s, e, fecha_visto, historial=None, *, serie=None, detalle=True, anterior=None):
    """Calcula los capítulos emitidos que quedan pendientes, incluidos los saltados."""
    serie = t.serie(sid) if serie is None else serie
    ultimo = serie.get("last_episode_to_air") or {}
    prox = serie.get("next_episode_to_air") or {}
    ult = (int(ultimo.get("season_number") or 0), int(ultimo.get("episode_number") or 0))
    caps = {x["season_number"]: int(x.get("episode_count") or 0) for x in serie.get("seasons", []) if x["season_number"] > 0}
    historial = historial or {"s": s, "e": e}
    restantes = []
    ultimo_visto = (0, 0)
    for temp in range(1, ult[0] + 1):
        hasta = ult[1] if temp == ult[0] else caps.get(temp, 0)
        for ep in range(1, hasta + 1):
            if seguimiento.esta_visto(historial, temp, ep):
                ultimo_visto = (temp, ep)
            else:
                restantes.append((temp, ep))

    siguiente = None
    if restantes and detalle:
        temp, ep = next((p for p in restantes if p > ultimo_visto), restantes[0])
        if anterior and (anterior["s"], anterior["e"]) == (temp, ep) and anterior.get("nombre"):
            siguiente = dict(anterior)
        else:
            try:
                episodios = t.temporada(sid, temp).get("episodes", []) if t else []
            except (OSError, ValueError):
                episodios = []
            ficha = next((x for x in episodios if x["episode_number"] == ep), {})
            siguiente = {"s": temp, "e": ep, "nombre": ficha.get("name") or "",
                         "still": ficha.get("still_path") or "", "emitido": ficha.get("air_date") or "",
                         "sinopsis": ficha.get("overview") or ""}
        siguiente["pendiente_anterior"] = (temp, ep) < ultimo_visto

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


def revision_local(datos):
    return [datos.get(k) for k in ("s", "e", "legado", "vistos", "no_vistos", "fecha")]


def progreso_desactualizado(perfil):
    seguidas = seguimiento.leer(perfil)
    estados = leer(perfil)
    return estados.keys() != seguidas.keys() or any(
        estados[sid].get("version") != VERSION or estados[sid].get("revision", [])[:6] != revision_local(d)
        for sid, d in seguidas.items())


def refrescar(perfil, t, forzar=False, log=print, vistos_trakt=None):
    """Recalcula las series en seguimiento caducadas. Devuelve [(titulo, ultimo)] de las que tienen capítulo NUEVO
    que antes no estaba (para avisar)."""
    antes = leer(perfil)
    ahora = dict(antes)
    recien = []
    seguidas = seguimiento.ordenadas(perfil)
    for sid, d in seguidas:
        previo = antes.get(sid)
        vistos = (vistos_trakt or {}).get(sid, [])
        revision = revision_local(d) + [vistos]
        vigente = not forzar and previo and time.time() - previo.get("comprobado", 0) < TTL
        if vigente and previo.get("version") == VERSION and previo.get("revision") == revision:
            continue
        serie = previo.get("catalogo") if vigente else None
        try:
            historial = seguimiento.con_historial_trakt(d, vistos)
            if serie is None:
                ficha = t.serie(int(sid))
                serie = {k: ficha.get(k) for k in ("last_episode_to_air", "next_episode_to_air", "in_production")}
                serie["seasons"] = [{k: x.get(k) for k in ("season_number", "episode_count")}
                                    for x in ficha.get("seasons", [])]
            est = estado(t, int(sid), int(d["s"]), int(d["e"]), d.get("fecha"), historial, serie=serie,
                         anterior=previo.get("siguiente") if vigente else None)
        except Exception as ex:
            log("[Palantix] novedades de %s: %s" % (d.get("titulo"), ex))
            continue
        est.update(catalogo=serie, revision=revision, version=VERSION)
        if vigente and previo.get("catalogo") is serie:
            est["comprobado"] = previo["comprobado"]
        ahora[sid] = est
        if previo and est["ultimo"] != previo.get("ultimo") and est["pendientes"]:
            recien.append((d.get("titulo", ""), est["ultimo"]))
    ids = {sid for sid, _ in seguidas}
    for sid in ahora.keys() - ids:
        ahora.pop(sid)
    if ahora != antes:
        _guardar(perfil, ahora)
    return recien


def resumen(perfil):
    """(series con capítulo nuevo, series con pendientes) leyendo solo la caché (instantáneo)."""
    datos = leer(perfil)
    return (sum(1 for x in datos.values() if x.get("nuevo")),
            sum(1 for x in datos.values() if x.get("pendientes")))
