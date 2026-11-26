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

guion[:] = [(201, {}), (200, {})]
tk.marcar_visto({"tipo": "episodio", "tmdb": 1399, "s": 2, "e": 5}, False)
comprobar("trakt: quitar visto sincroniza serie, temporada y episodio",
          vistas_t[-1] == ("POST", "/sync/history/remove",
                          {"shows": [{"ids": {"tmdb": 1399},
                                      "seasons": [{"number": 2, "episodes": [{"number": 5}]}]}]}))
tk.cambiar_pendiente("shows", 1399, True)
comprobar("trakt: añadir una serie a pendientes usa su id de TMDB",
          vistas_t[-1] == ("POST", "/sync/watchlist", {"shows": [{"ids": {"tmdb": 1399}}]}))

# gancho: scrobble al empezar y parar, y nota al terminar
aj2 = Aj(trakt_client_id="C", trakt_client_secret="S", trakt_token="T", trakt_activo="true", trakt_valorar="2", valorar_al_terminar="false")
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
llamadas.clear()
aj2.set("trakt_activo", "false")
g.al_empezar(meta, None)
g.al_parar(meta, None, True)
comprobar("trakt desactivado no envía reproducciones", not llamadas)
aj2.set("trakt_activo", "true")
g.al_empezar(meta, None)
g.al_parar(meta, None, True)
comprobar("trakt recién activado funciona sin reiniciar el servicio", llamadas == [("start", 0), ("stop", 100)])
notas.clear()
aj2.set("valorar_al_terminar", "true")
g.al_parar(meta, None, True)
g.al_parar(dict(meta, tipo="episodio", s=1, e=8, valoracion_titulo=True), None, True)
comprobar("Trakt conserva el scrobble sin duplicar la pregunta local de valoración",
          notas == [] and llamadas[-2:] == [("stop", 100), ("stop", 100)])
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

# ---------------------------------------------------------------- pantalla de inicio (filas)
from resources.lib import inicio, progreso as pg, seguimiento as sg, novedades as nv  # noqa: E402
from urllib.parse import urlencode  # noqa: E402

PERF = tempfile.mkdtemp(prefix="palantix_inicio_")
url = lambda **kw: "plugin://plugin.video.palantix/?" + urlencode(kw)


class TFalso:
    idioma = "es-ES"
    region = "ES"
    llamadas = 0

    def _r(self, n):
        TFalso.llamadas += 1
        return {"results": [{"id": n + i, "title": "Peli %d" % (n + i), "name": "Serie %d" % (n + i),
                             "release_date": "2025-05-01", "first_air_date": "2024-01-01", "vote_average": 7.8,
                             "poster_path": "/p%d.jpg" % i, "backdrop_path": "/f%d.jpg" % i, "overview": "Sinopsis"}
                            for i in range(25)]}

    def detalle(self, sid): return {"poster_path": "/reparada.jpg"}
    def tendencias(self, p): return self._r(1000)
    def s_tendencias(self, p): return self._r(2000)
    def s_capitulos_recientes(self, p): return self._r(8000)
    def en_cines(self, p): return self._r(3000)
    def mejor_valoradas(self, p): return self._r(4000)
    def novedades_streaming(self, p): return self._r(7000)


pg.apuntar(PERF, {"tipo": "pelicula", "tmdb": 653, "titulo": "Nosferatu", "anio": 1922, "fanart": "/n.jpg"}, 1200, 5640)
sg.marcar_visto(PERF, {"tipo": "episodio", "tmdb": 100, "s": 1, "e": 1, "titulo": "Ficción", "poster": "/s.jpg"})
sg.marcar_visto(PERF, {"tipo": "episodio", "tmdb": 200, "s": 2, "e": 3, "titulo": "Otra"})
nv._guardar(PERF, {"100": {"pendientes": 2, "nuevo": True, "siguiente": {"s": 1, "e": 2, "nombre": "Dos", "still": "/st.jpg"}},
                   "200": {"pendientes": 1, "nuevo": False, "siguiente": {"s": 2, "e": 4, "nombre": "Cuatro"}}})
filas = inicio.datos_filas(PERF, TFalso(), url, favoritas=[{"id": 9, "title": "Favorita", "release_date": "2000-01-01"}])
comprobar("inicio: recupera una carátula faltante en una película guardada antes del cambio",
          filas[101][0]["poster"].endswith("/reparada.jpg") and filas[101][0]["thumb"].endswith("/n.jpg"))
comprobar("inicio: «Continuar viendo» con la peli a medias y la serie sin novedad",
          [e["label"] for e in filas[101]] == ["Nosferatu", "Otra"] and filas[101][0]["resume"] == (1200, 5640))
comprobar("inicio: «Nuevos capítulos» con la serie que tiene NUEVO", [e["label"] for e in filas[102]] == ["Ficción"]
          and filas[102][0]["nuevo"] == "1" and "e=2" in filas[102][0]["url"])
comprobar("inicio: filas del catálogo con 20 carátulas cada una", all(len(filas[f]) == 20 for f in (103, 104, 106)) and 105 not in filas)
comprobar("inicio: película = reproducir, serie = abrir temporadas",
          filas[103][0]["tipo"] == "reproducir" and "accion=reproducir" in filas[103][0]["url"]
          and filas[104][0]["tipo"] == "carpeta" and "accion=temporadas" in filas[104][0]["url"])
comprobar("inicio: línea de información «2025 · ★ 7.8 · Película»", filas[103][0]["info"] == "2025   ·   ★ 7.8   ·   Película")
comprobar("inicio: Mi lista con las favoritas", [e["label"] for e in filas[107]] == ["Favorita"])
comprobar("inicio: novedades en streaming pasan por el filtro de fuentes",
          [e["label"] for e in inicio.datos_filas(
              PERF, TFalso(), url, filtrar_peliculas=lambda pelis: [p for p in pelis if p["id"] == 7001]
          )[108]] == ["Peli 7001"])
antes = TFalso.llamadas
inicio.datos_filas(PERF, TFalso(), url)
comprobar("inicio: la segunda vez abre al instante (catálogo en caché, sin pedir a TMDB)", TFalso.llamadas == antes)
filas = inicio.datos_filas(tempfile.mkdtemp(), None, url)
comprobar("inicio: sin clave de TMDB no se rompe (filas vacías)", all(v == [] for v in filas.values()))
comprobar("inicio: menú lateral con Buscar, Películas, Series... y Menú clásico",
          [m[0] for m in inicio.menu(url)] == ["Inicio", "Hoy para ti", "Buscar", "Películas", "Series", "Mis series", "Historial de vistos", "Mi lista",
                                                "Cine libre y documentales", "TV", "TV internacional", "Radio", "Mis listas", "Ajustes", "Actualizar", "Menú clásico", "Salir"])

# ---------------------------------------------------------------- pestañas Películas y Series
class TPestanas(TFalso):
    def populares(self, p): return self._r(5000)
    def por_genero(self, g, p): return self._r(6000 + g)
    def s_populares(self, p): return self._r(7000)
    def s_mejor_valoradas(self, p): return self._r(8000)
    def s_por_genero(self, g, p): return self._r(9000 + g)


PP = tempfile.mkdtemp(prefix="palantix_pestanas_")
pel = inicio.datos_pestana(PP, TPestanas(), url, "peliculas")
comprobar("pestaña Películas: 7 filas y ninguna de cine", sorted(pel) == [103, 104, 106, 107, 108, 109, 110]
          and all(len(v) == 20 for v in pel.values()))
comprobar("pestaña Películas: la fila Terror pide el género 27 y reproduce", pel[109][0]["label"] == "Peli %d" % (6000 + 27)
          and pel[109][0]["tipo"] == "reproducir")
ser = inicio.datos_pestana(PP, TPestanas(), url, "series")
comprobar("pestaña Series: las series abren sus temporadas", ser[106][0]["label"] == "Serie %d" % (9000 + 18)
          and ser[106][0]["tipo"] == "carpeta" and "accion=temporadas" in ser[106][0]["url"])
comprobar("pestaña Series: capítulos recientes abre la serie",
          ser[111][0]["label"] == "Serie 8000" and "accion=temporadas" in ser[111][0]["url"])
for sid, titulo in ((8001, "Completa"), (8002, "Al corriente"), (8003, "Con pendientes")):
    sg.marcar_visto(PP, {"tmdb": sid, "tipo": "episodio", "s": 1, "e": 1, "titulo": titulo})
nv._guardar(PP, {"8001": {"ultimo": {"e": 1}, "en_emision": False},
                 "8002": {"ultimo": {"e": 1}, "en_emision": True},
                 "8003": {"pendientes": 1}})
ser = inicio.datos_pestana(PP, TPestanas(), url, "series")
comprobar("pestaña Series: seguimiento visible y ordenado por estado",
          inicio.titulos("series")[101] == "Series en seguimiento" and
          [e["destacado"] for e in ser[101]] == ["Nuevo", "Al día", "Terminada"])
antes = TFalso.llamadas
inicio.datos_pestana(PP, TPestanas(), url, "peliculas")
comprobar("pestañas: la segunda vez abren al instante (caché)", TFalso.llamadas == antes)
comprobar("pestañas: títulos de las filas", inicio.titulos("series")[110] == "Documentales" and inicio.titulos("inicio")[101] == "Continuar viendo")
comprobar("menú lateral: Películas y Series cambian de pestaña sin salir",
          [(m[0], m[2], m[3]) for m in inicio.menu(url)][3:5] == [("Películas", "pestana", "peliculas"), ("Series", "pestana", "series")])

print("\n%s" % ("TODO CORRECTO" if not fallos else "%d FALLOS" % fallos))
sys.exit(1 if fallos else 0)
