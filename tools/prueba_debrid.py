"""Pruebas del centro Debrid (Real-Debrid, Premiumize y el orden entre servicios).

python tools/prueba_debrid.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugin.video.palantix"))
from resources.lib import debrid  # noqa: E402

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


class Guion:
    """Sustituye la red: lista de (trozo_de_url, código, json) que se van consumiendo en orden."""
    def __init__(self, pasos):
        self.pasos, self.vistas = list(pasos), []

    def __call__(self, url, datos=None, cabeceras=None, metodo=None):
        self.vistas.append((url, datos, (cabeceras or {}).get("Authorization")))
        trozo, cod, r = self.pasos.pop(0)
        assert trozo in url, "esperaba %s y llegó %s" % (trozo, url)
        return cod, r


real_peticion = debrid._peticion


def con_guion(pasos):
    g = Guion(pasos)
    debrid._peticion = g
    return g


sin_espera = dict(espera=lambda s: None, log=lambda m: None)
rd_aj = lambda: Aj(rd_activo="true", rd_token="T1", rd_refresh="R1", rd_client_id="C", rd_client_secret="S",
                   rd_caduca=str(time.time() + 3600))

# --- Real-Debrid ---------------------------------------------------------------
con_guion([("/unrestrict/link", 200, {"download": "https://rd/directo.mkv"})])
comprobar("RD: desbloquea un enlace", debrid.RealDebrid(rd_aj(), **sin_espera).resolver("https://1fichier.com/?x") == "https://rd/directo.mkv")

aj = rd_aj()
g = con_guion([("/unrestrict/link", 401, {"error": "bad_token", "error_code": 8}),
               ("/oauth/v2/token", 200, {"access_token": "T2", "refresh_token": "R2", "expires_in": 3600}),
               ("/unrestrict/link", 200, {"download": "https://rd/ok.mkv"})])
r = debrid.RealDebrid(aj, **sin_espera).resolver("https://1fichier.com/?x")
comprobar("RD: token caducado -> lo renueva solo y reintenta", r == "https://rd/ok.mkv" and aj["rd_token"] == "T2"
          and g.vistas[2][2] == "Bearer T2")

ficheros = [{"id": 1, "path": "/Peli/Peli.1080p.mkv", "bytes": 8e9, "selected": 1},
            {"id": 2, "path": "/Peli/sample.mkv", "bytes": 5e7, "selected": 1},
            {"id": 3, "path": "/Peli/info.nfo", "bytes": 100, "selected": 0}]
g = con_guion([("/torrents/addMagnet", 201, {"id": "TID"}),
               ("/torrents/info/TID", 200, {"status": "waiting_files_selection", "files": ficheros}),
               ("/torrents/selectFiles/TID", 204, {}),
               ("/torrents/info/TID", 200, {"status": "downloaded", "files": ficheros,
                                            "links": ["https://rd/l1", "https://rd/l2"]}),
               ("/unrestrict/link", 200, {"download": "https://rd/peli.mkv"})])
r = debrid.RealDebrid(rd_aj(), **sin_espera).resolver("magnet:?xt=urn:btih:abc")
comprobar("RD: magnet listo -> elige el vídeo grande, no el sample", r == "https://rd/peli.mkv"
          and g.vistas[2][1] == {"files": "1,2"} and g.vistas[4][1] == {"link": "https://rd/l1"})

con_guion([("/torrents/addMagnet", 201, {"id": "T"})] +
          [("/torrents/info/T", 200, {"status": "downloading", "progress": 12})] * 30)
try:
    debrid.RealDebrid(rd_aj(), **sin_espera).resolver("magnet:?xt=urn:btih:def")
    comprobar("RD: magnet no listo avisa", False)
except debrid.NoListo as e:
    comprobar("RD: magnet no listo avisa (%s)" % e, True)
except Exception as e:
    comprobar("RD: magnet no listo avisa (%r)" % e, False)

con_guion([("/unrestrict/link", 503, {"error": "traffic_exhausted", "error_code": 23})])
try:
    debrid.RealDebrid(rd_aj(), **sin_espera).resolver("https://1fichier.com/?y")
except debrid.DebridError as e:
    comprobar("RD: error traducido (%s)" % e, "Tráfico" in str(e))

aj = Aj()
con_guion([("/device/credentials", 403, {"error": "authorization_pending"})])
comprobar("RD: vinculación pendiente -> sigue esperando", debrid.RealDebrid(aj, **sin_espera).comprobar_pin({"device_code": "D"}) is False)
con_guion([("/device/credentials", 200, {"client_id": "C9", "client_secret": "S9"}),
           ("/oauth/v2/token", 200, {"access_token": "TOK", "refresh_token": "REF", "expires_in": 3600})])
comprobar("RD: vinculación completa guarda credenciales y lo enciende",
          debrid.RealDebrid(aj, **sin_espera).comprobar_pin({"device_code": "D"}) and aj["rd_token"] == "TOK"
          and aj["rd_client_secret"] == "S9" and aj["rd_activo"] == "true")

# --- Premiumize ----------------------------------------------------------------
pm = lambda: debrid.Premiumize(Aj(pm_activo="true", pm_apikey="K"), **sin_espera)
g = con_guion([("/transfer/directdl", 200, {"status": "success", "content": [
    {"path": "x/peli.mkv", "size": 7e9, "link": "https://pm/peli.mkv"},
    {"path": "x/peli.srt", "size": 1e4, "link": "https://pm/peli.srt"}]})])
comprobar("PM: directdl devuelve el vídeo", pm().resolver("https://rapidgator.net/file/x") == "https://pm/peli.mkv"
          and g.vistas[0][2] == "Bearer K")
g = con_guion([("/cache/check", 200, {"status": "success", "response": [False]}),
               ("/transfer/create", 200, {"status": "success", "id": "Z"})])
try:
    pm().resolver("magnet:?xt=urn:btih:abc")
    comprobar("PM: magnet no en caché", False)
except debrid.NoListo:
    comprobar("PM: magnet no en caché -> lo manda a descargar y avisa", g.pasos == [])
con_guion([("/transfer/directdl", 200, {"status": "error", "message": "Not premium"})])
try:
    pm().resolver("https://rapidgator.net/file/y")
except debrid.DebridError as e:
    comprobar("PM: error con su mensaje (%s)" % e, "Not premium" in str(e))

# --- TorBox -------------------------------------------------------------------
def tb_con(respuestas):
    s = debrid.TorBox(Aj(tb_activo="true", tb_apikey="K"), **sin_espera)
    vistas = []

    def falso(ruta, params=None, formulario=None):
        vistas.append((ruta, params, formulario))
        r = respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    s._api = falso
    return s, vistas


tb, v = tb_con([{"torrent_id": 7}, {"download_finished": True, "files": [
    {"id": 0, "name": "Peli/Peli.2160p.mkv", "size": 20e9}, {"id": 1, "name": "Peli/sample.mkv", "size": 1e8}]},
    "https://tb/descarga.mkv"])
comprobar("TB: magnet listo -> vídeo grande y enlace", tb.resolver("magnet:?xt=urn:btih:abc") == "https://tb/descarga.mkv"
          and v[2][1] == {"token": "K", "torrent_id": 7, "file_id": 0} and v[0][2]["magnet"].startswith("magnet:"))
tb, v = tb_con([{"torrent_id": 8}, {"download_finished": False, "progress": 0.42}])
try:
    tb.resolver("magnet:?xt=urn:btih:def")
    comprobar("TB: magnet no listo", False)
except debrid.NoListo as e:
    comprobar("TB: magnet no listo avisa (%s)" % e, "42%" in str(e))
tb, v = tb_con([{"webdownload_id": 3}, {"download_present": True, "files": [{"id": 5, "name": "x.mp4", "size": 9e8}]},
                "https://tb/web.mp4"])
comprobar("TB: enlace de alojamiento -> descarga web", tb.resolver("https://rapidgator.net/file/x") == "https://tb/web.mp4"
          and v[2][1]["web_id"] == 3 and v[2][1]["file_id"] == 5)
body, tipo = debrid._multipart({"magnet": "magnet:?x"})
comprobar("TB: formulario multipart bien formado", tipo.startswith("multipart/form-data; boundary=")
          and b'name="magnet"' in body and body.endswith(b"--\r\n"))

# --- centro: orden y salto entre servicios -------------------------------------
class Falso(debrid.Servicio):
    def __init__(self, nombre, admite, resultado):
        super().__init__(Aj(), **sin_espera)
        self.nombre, self._admite, self._res = nombre, admite, resultado

    def admite(self, url):
        return self._admite

    def resolver(self, url, elegir=None, cancelado=None):
        if isinstance(self._res, Exception):
            raise self._res
        return self._res


r = debrid.resolver("https://host/x", [Falso("A", True, debrid.DebridError("caído")), Falso("B", True, "https://b/ok")], log=lambda m: None)
comprobar("centro: si el primero falla, usa el segundo", r == "https://b/ok")
r = debrid.resolver("https://archive.org/x.mp4", [Falso("A", False, "nunca")])
comprobar("centro: enlace directo normal pasa tal cual", r == "https://archive.org/x.mp4")
try:
    debrid.resolver("magnet:?xt=urn:btih:abc", [])
    comprobar("centro: magnet sin servicios", False)
except debrid.DebridError as e:
    comprobar("centro: magnet sin servicios avisa (%s)" % e, "Debrid" in str(e))
aj = Aj(ad_activo="true", ad_apikey="x", rd_activo="false", rd_token="y", pm_activo="true")
comprobar("centro: solo cuenta los encendidos Y vinculados", [s.id for s in debrid.activos(aj, **sin_espera)] == ["ad"])
try:
    debrid.TorBox(Aj(tb_apikey="clave-falsa"), **sin_espera)._yo()
    comprobar("TB real: clave falsa rechazada", False)
except debrid.DebridError as e:
    comprobar("TB real: clave falsa rechazada (%s)" % str(e)[:40], True)
debrid._peticion = real_peticion
comprobar("TB real: alojamientos (rapidgator admitido)", debrid.TorBox(Aj(tb_apikey="x"), **sin_espera).admite("https://rapidgator.net/file/abc"))

# --- API pública real ------------------------------------------------------------
debrid._peticion = real_peticion
try:
    cod, doms = real_peticion(debrid.RealDebrid.REST + "/hosts/domains")
    comprobar("RD real: %d dominios (1fichier: %s)" % (len(doms), "1fichier.com" in doms), cod == 200 and len(doms) > 20)
except Exception as e:
    comprobar("RD real: dominios (%s)" % e, False)
try:
    pin = debrid.RealDebrid(Aj(), **sin_espera).iniciar_pin()
    comprobar("RD real: código de vinculación %s en %s" % (pin["codigo"], pin["url"]), bool(pin["codigo"]))
except Exception as e:
    comprobar("RD real: código de vinculación (%s)" % e, False)
try:
    debrid.Premiumize(Aj(pm_apikey="clave-falsa"), **sin_espera).cuenta()
    comprobar("PM real: clave falsa rechazada", False)
except debrid.DebridError as e:
    comprobar("PM real: clave falsa rechazada (%s)" % e, True)

print("\n%s" % ("TODO CORRECTO" if not fallos else "%d FALLOS" % fallos))
sys.exit(1 if fallos else 0)
