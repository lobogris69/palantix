"""Novedades de las series en seguimiento: capítulos pendientes y capítulos NUEVOS.

- pendientes: capítulos ya emitidos que van después del último que viste.
- nuevo: ha salido algún capítulo DESPUÉS de la última vez que viste la serie.
Se guarda en novedades.json (caché de 6 h) para que los menús abran al instante;
el servicio lo refresca solo y avisa cuando aparece un capítulo nuevo.
"""
import json
import os
import time

from . import seguimiento

TTL = 6 * 3600


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


def _antes(a, b):
    return (a[0], a[1]) < (b[0], b[1])


def estado(t, sid, s, e, fecha_visto):
    """Calcula el estado de una serie para quien ha visto hasta SxE (en la fecha `fecha_visto`, epoch)."""
    serie = t.serie(sid)
    ultimo = serie.get("last_episode_to_air") or {}
    prox = serie.get("next_episode_to_air") or {}
    ult = (int(ultimo.get("season_number") or 0), int(ultimo.get("episode_number") or 0))
    caps = {x["season_number"]: int(x.get("episode_count") or 0) for x in serie.get("seasons", []) if x["season_number"] > 0}

    pendientes = 0
    if ult[0] and _antes((s, e), ult):
        for temp in range(max(s, 1), ult[0] + 1):
            hasta = ult[1] if temp == ult[0] else caps.get(temp, 0)
            desde = e if temp == s else 0
            pendientes += max(0, hasta - desde)

    siguiente = None
    if pendientes:
        for temp, desde in ((s, e), (s + 1, 0)):
            try:
                eps = t.temporada(sid, temp).get("episodes", [])
            except Exception:
                eps = []
            cand = [x for x in sorted(eps, key=lambda x: x["episode_number"]) if x["episode_number"] > desde]
            if cand:
                x = cand[0]
                siguiente = {"s": temp, "e": x["episode_number"], "nombre": x.get("name") or "",
                             "still": x.get("still_path") or "", "emitido": x.get("air_date") or "",
                             "sinopsis": x.get("overview") or ""}
                break

    visto_dia = time.strftime("%Y-%m-%d", time.localtime(fecha_visto or 0))
    return {
        "pendientes": pendientes,
        "nuevo": bool(pendientes and (ultimo.get("air_date") or "") > visto_dia),
        "ultimo": {"s": ult[0], "e": ult[1], "emitido": ultimo.get("air_date") or ""},
        "proximo": {"s": prox.get("season_number"), "e": prox.get("episode_number"), "emitido": prox.get("air_date")}
        if prox else None,
        "siguiente": siguiente,
        "en_emision": serie.get("in_production", False) or bool(prox),
        "comprobado": time.time(),
    }


def refrescar(perfil, t, forzar=False, log=print):
    """Recalcula las series en seguimiento caducadas. Devuelve [(titulo, ultimo)] de las que tienen capítulo NUEVO
    que antes no estaba (para avisar)."""
    antes = leer(perfil)
    ahora = dict(antes)
    recien = []
    for sid, d in seguimiento.ordenadas(perfil):
        previo = antes.get(sid)
        if not forzar and previo and time.time() - previo.get("comprobado", 0) < TTL \
                and previo.get("visto") == [d.get("s"), d.get("e")]:
            continue
        try:
            est = estado(t, int(sid), int(d["s"]), int(d["e"]), d.get("fecha"))
        except Exception as ex:
            log("[Palantix] novedades de %s: %s" % (d.get("titulo"), ex))
            continue
        est["visto"] = [d.get("s"), d.get("e")]
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
