"""Pruebas de subtítulos (OpenSubtitles), Trakt y saltar intro.

python tools/prueba_extras.py
"""
import io
import json
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugin.video.palantix"))
from resources.lib import intro, subtitulos, trakt  # noqa: E402

fallos = 0


def comprobar(nombre, cond):
    global fallos
    print(("OK    " if cond else "FALLO ") + nombre)
    fallos += 0 if cond else 1


class Aj(dict):
    def get(self, k, d=""):
        return dict.get(self, k, d)

    def set(self, k, v):
        self[k] = v


TMP = tempfile.mkdtemp(prefix="palantix_extras_")

# ---------------------------------------------------------------- subtítulos
os_ = subtitulos.OpenSubtitles("K", log=lambda m: None)
vistas = []


def falso(metodo, ruta, params=None, cuerpo=None):
    vistas.append((metodo, ruta, params, cuerpo))
    if ruta == "/subtitles":
        return {"data": [
            {"attributes": {"language": "es", "download_count": 50, "release": "Peli.1080p", "files": [{"file_id": 1}]}},
            {"attributes": {"language": "es", "download_count": 900, "release": "Peli.WEB", "ai_translated": True, "files": [{"file_id": 2}]}},
            {"attributes": {"language": "es", "download_count": 300, "release": "Peli.BluRay", "files": [{"file_id": 3}]}}]}
    if ruta == "/download":
        return {"link": "https://os/descarga.srt", "remaining": 4}
    raise AssertionError(ruta)


os_._pedir = falso
lista = os_.buscar(653)
comprobar("subs: los más descargados primero y las traducciones automáticas al final", [s["file_id"] for s in lista] == [3, 1, 2])
os_.buscar(100, temporada=1, episodio=2)
comprobar("subs: en capítulos busca por la serie + temporada + capítulo",
          vistas[-1][2] == {"parent_tmdb_id": 100, "season_number": 1, "episode_number": 2, "languages": "es"})

import urllib.request  # noqa: E402
real_urlopen = urllib.request.urlopen
urllib.request.urlopen = lambda req, timeout=0: io.BytesIO(b"1\n00:00:01,000 --> 00:00:02,000\nHola\n")
urllib.request.urlopen.__enter__ = None
class _R(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass
urllib.request.urlopen = lambda req, timeout=0: _R(b"1\n00:00:01,000 --> 00:00:02,000\nHola\n")
ruta = os_.descargar(3, os.path.join(TMP, "subs"), "Nosferatu (1922)")
urllib.request.urlopen = real_urlopen
comprobar("subs: descarga el .srt al perfil", os.path.exists(ruta) and ruta.endswith(".3.srt") and "Hola" in open(ruta, encoding="utf-8").read())
comprobar("subs: audio latino con preferencia castellano -> NO hacen falta (es español)",
          not subtitulos.hace_falta(1, ["LAT"], "CAST"))
comprobar("subs: audio en inglés -> sí", subtitulos.hace_falta(1, ["VO"], "CAST"))
comprobar("subs: audio desconocido -> sí (mejor tenerlos)", subtitulos.hace_falta(1, [], "CAST"))
comprobar("subs: modo Nunca / Siempre", not subtitulos.hace_falta(0, ["VO"], "CAST") and subtitulos.hace_falta(2, ["CAST"], "CAST"))
try:
    subtitulos.OpenSubtitles("clave-falsa").buscar(653)
    comprobar("subs real: clave falsa rechazada", False)
except subtitulos.SubError as e:
    comprobar("subs real: clave falsa rechazada (%s)" % e, True)

# ---------------------------------------------------------------- Trakt
aj = Aj(trakt_client_id="C", trakt_client_secret="S")
tk = trakt.Trakt(aj, log=lambda m: None)
guion = []
vistas_t = []


def t_falso(metodo, ruta, cuerpo=None, auth=True, reintento=True):
    vistas_t.append((metodo, ruta, cuerpo))
    return guion.pop(0)


tk._pedir = t_falso
guion[:] = [(400, {})]
comprobar("trakt: vinculación pendiente -> sigue esperando", tk.comprobar_pin({"device_code": "D"}) is False)
guion[:] = [(200, {"access_token": "T", "refresh_token": "R", "expires_in": 7776000, "created_at": 1700000000})]
comprobar("trakt: vinculación completa guarda la sesión y lo enciende", tk.comprobar_pin({"device_code": "D"})
          and aj["trakt_token"] == "T" and aj["trakt_activo"] == "true")
guion[:] = [(410, {})]
try:
    tk.comprobar_pin({"device_code": "D"})
except trakt.TraktError as e:
    comprobar("trakt: código caducado avisa (%s)" % e, "caducado" in str(e))
guion[:] = [(201, {})]
tk.scrobble("stop", {"tipo": "episodio", "tmdb": 1399, "s": 2, "e": 5}, 93.456)
comprobar("trakt: scrobble de capítulo con serie + temporada + número",
          vistas_t[-1] == ("POST", "/scrobble/stop", {"show": {"ids": {"tmdb": 1399}}, "episode": {"season": 2, "number": 5}, "progress": 93.46}))
guion[:] = [(409, {})]
tk.scrobble("stop", {"tipo": "pelicula", "tmdb": 653}, 100)
comprobar("trakt: 409 (ya apuntado) no es error", True)
guion[:] = [(201, {})]
tk.valorar({"tipo": "pelicula", "tmdb": 653}, 8)
comprobar("trakt: valoración de película", vistas_t[-1][2] == {"movies": [{"ids": {"tmdb": 653}, "rating": 8}]})
guion[:] = [(200, [{"movie": {"title": "A", "year": 2001, "ids": {"tmdb": 1}}}, {"movie": {"title": "B", "ids": {}}}])]
comprobar("trakt: pendientes (ignora los que no tienen id de TMDB)", tk.pendientes("movies") == [(1, "A", 2001)])
guion[:] = [(200, [{"type": "movie", "movie": {"title": "A", "year": 2001, "ids": {"tmdb": 1}}},
                   {"type": "show", "show": {"title": "S", "year": 2010, "ids": {"tmdb": 2}}},
                   {"type": "person", "person": {}}])]
comprobar("trakt: elementos de una lista personal", tk.lista(5) == [("pelicula", 1, "A", 2001), ("serie", 2, "S", 2010)])

# gancho: scrobble al empezar y parar, y nota al terminar
aj2 = Aj(trakt_client_id="C", trakt_client_secret="S", trakt_token="T", trakt_activo="true", trakt_valorar="2")
notas = []
g = trakt.TraktGancho(aj2, preguntar=lambda meta: 9, log=lambda m: None)
llamadas = []
g.t.scrobble = lambda accion, meta, pct: llamadas.append((accion, round(pct)))
g.t.valorar = lambda meta, nota: notas.append(nota)
meta = {"tipo": "pelicula", "tmdb": 653, "titulo": "Nosferatu"}
g.al_empezar(meta, None)
g.al_avanzar(meta, None, 4500, 5000)
g.al_parar(meta, None, False)
comprobar("trakt gancho: start y stop al 90 %", llamadas == [("start", 0), ("stop", 90)])
comprobar("trakt gancho: al pasar del 80 % pregunta la nota y la guarda", notas == [9])
llamadas.clear()
notas.clear()
g.al_empezar(meta, None)
g.al_avanzar(meta, None, 1000, 5000)
g.al_parar(meta, None, False)
comprobar("trakt gancho: al 20 % no pregunta nota", llamadas == [("start", 0), ("stop", 20)] and notas == [])
comprobar("trakt: «a veces» pregunta 1 de cada 3", trakt.toca_preguntar(1, lambda: 0.1) and not trakt.toca_preguntar(1, lambda: 0.9))

try:
    trakt.Trakt(Aj(trakt_client_id="falso", trakt_client_secret="x")).iniciar_pin()
    comprobar("trakt real: Client ID falso rechazado", False)
except trakt.TraktError as e:
    comprobar("trakt real: Client ID falso rechazado (%s)" % e, True)

# ---------------------------------------------------------------- saltar intro
m = {"tipo": "episodio", "tmdb": 100, "s": 1, "e": 1}
d = intro.Detector(TMP, m)
t, pos = 1000.0, 0
for _ in range(60):
    pos += 1; t += 1; d.paso(pos, "", t)
for _ in range(3):
    pos += 31; t += 1; d.paso(pos, "", t)
for _ in range(10):
    pos += 1; t += 1; d.paso(pos, "", t)
comprobar("intro: aprende 3 saltos seguidos como una sola intro (60 -> 153)", intro.leer(TMP).get("100") == {"inicio": 60, "fin": 153, "veces": 1})
d2 = intro.Detector(TMP, dict(m, e=2))
ev, t = None, 5000.0
for p in range(70):
    t += 1
    ev = d2.paso(p, "", t) or ev
comprobar("intro: en el capítulo siguiente ofrece el botón hasta el 153", ev == ("ofrecer", 153))
d3 = intro.Detector(TMP, dict(m, tmdb=200))
d3.paso(100, "", 9000.0)
d3.paso(110, "", 9010.0)  # 10 s de vídeo en 10 s reales (el botón estaba en pantalla): no es salto
for i in range(6):
    d3.paso(111 + i, "", 9011.0 + i)
comprobar("intro: el tiempo con el botón en pantalla no se confunde con un salto", "200" not in intro.leer(TMP))
d4 = intro.Detector(TMP, dict(m, tmdb=300))
for i in range(30):
    d4.paso(600 + i * 40, "", 100.0 + i)  # adelantar a los 10 min: no es la intro
comprobar("intro: saltos pasados los 8 primeros minutos no se aprenden", "300" not in intro.leer(TMP))
comprobar("intro: capítulo «Opening» del vídeo", intro.Detector(TMP, dict(m, tmdb=400)).paso(5, "Opening", 1.0) == ("capitulo", None))
comprobar("intro: no salta en películas", intro.Detector(TMP, {"tipo": "pelicula", "tmdb": 1}).sid is None)
intro.aprender(TMP, 100, 64, 157)
comprobar("intro: un segundo salto parecido afina la media", intro.leer(TMP)["100"] == {"inicio": 62.0, "fin": 155.0, "veces": 2})

print("\n%s" % ("TODO CORRECTO" if not fallos else "%d FALLOS" % fallos))
sys.exit(1 if fallos else 0)
