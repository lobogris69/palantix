"""Pruebas del conector AllDebrid.

  python tools/prueba_alldebrid.py             -> lógica con respuestas simuladas + API pública real
  ALLDEBRID_APIKEY=xxx python tools/prueba_alldebrid.py URL_O_MAGNET
                                                -> además, prueba real con tu cuenta
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugin.video.palantix"))
from resources.lib.alldebrid import AllDebrid, AllDebridError, NoListo, _aplanar  # noqa: E402

fallos = 0


def comprobar(nombre, cond):
    global fallos
    print(("OK    " if cond else "FALLO ") + nombre)
    fallos += 0 if cond else 1


class Simulado(AllDebrid):
    """Sustituye la red por un guion de respuestas: {ruta: [respuesta1, respuesta2, ...]}."""
    def __init__(self, guion):
        super().__init__("clave", log=lambda m: None, espera=lambda s: None)
        self.guion, self.llamadas = guion, []

    def _req(self, ruta, params=None, metodo="POST", auth=True):
        self.llamadas.append((ruta, params))
        r = self.guion[ruta].pop(0)
        if isinstance(r, Exception):
            raise r
        return r


# --- lógica ------------------------------------------------------------------
ad = Simulado({"/v4/link/unlock": [{"link": "https://directo/x.mkv", "filename": "x.mkv"}]})
comprobar("desbloqueo inmediato", ad.desbloquear("https://alojamiento/abc") == ("https://directo/x.mkv", "x.mkv"))

ad = Simulado({"/v4/link/unlock": [{"delayed": 77, "filename": "y.mp4"}],
               "/v4/link/delayed": [{"status": 1}, {"status": 1}, {"status": 2, "link": "https://directo/y.mp4"}]})
comprobar("desbloqueo diferido espera y devuelve el enlace", ad.desbloquear("https://h/y") == ("https://directo/y.mp4", "y.mp4")
          and len(ad.llamadas) == 4)

ad = Simulado({"/v4/link/unlock": [AllDebridError("LINK_DOWN")]})
try:
    ad.desbloquear("https://h/z")
    comprobar("error traducido", False)
except AllDebridError as e:
    comprobar("error LINK_DOWN traducido al español", str(e) == "El enlace ya no existe en el alojamiento")

arbol = [{"n": "Peli (2020)", "e": [
    {"n": "Peli.2020.1080p.mkv", "s": 8_000_000_000, "l": "https://ad/1"},
    {"n": "sample.mkv", "s": 50_000_000, "l": "https://ad/2"},
    {"n": "Subs", "e": [{"n": "es.srt", "s": 90_000, "l": "https://ad/3"}]}]}]
comprobar("árbol de ficheros aplanado", len(list(_aplanar(arbol))) == 3)

ad = Simulado({"/v4/magnet/upload": [{"magnets": [{"id": 5, "ready": True}]}],
               "/v4/magnet/files": [{"magnets": [{"id": 5, "files": arbol}]}]})
v = ad.magnet("magnet:?xt=urn:btih:abc")
comprobar("magnet listo: solo el vídeo bueno, sin sample ni subtítulos", [x[0] for x in v] == ["Peli (2020)/Peli.2020.1080p.mkv"])

ad = Simulado({"/v4/magnet/upload": [{"magnets": [{"id": 6, "ready": False}]}]})
try:
    ad.magnet("magnet:?xt=urn:btih:def")
    comprobar("magnet no listo avisa", False)
except NoListo:
    comprobar("magnet no listo avisa", True)

doms = {"1fichier.com", "rapidgator.net", "mega.nz"}
comprobar("detecta alojamiento admitido (con subdominio)", AllDebrid.necesita("https://www.1fichier.com/?abc", doms))
comprobar("deja pasar enlaces directos", not AllDebrid.necesita("https://archive.org/download/x/y.mp4", doms))
comprobar("los magnets siempre van a AllDebrid", AllDebrid.necesita("magnet:?xt=urn:btih:abc", doms))

# --- API pública real -------------------------------------------------------
real = AllDebrid()
try:
    d = real.pin_get()
    comprobar("API real: PIN obtenido (%s, %s)" % (d.get("pin"), d.get("user_url")), bool(d.get("pin") and d.get("check")))
except Exception as e:
    comprobar("API real: PIN (%s)" % e, False)
try:
    doms = real.dominios()
    comprobar("API real: %d dominios admitidos (1fichier: %s)" % (len(doms), "1fichier.com" in doms), len(doms) > 20)
except Exception as e:
    comprobar("API real: dominios (%s)" % e, False)
try:
    AllDebrid("clave-falsa").usuario()
    comprobar("API real: clave falsa rechazada", False)
except AllDebridError as e:
    comprobar("API real: clave falsa rechazada (%s)" % e.codigo, e.codigo == "AUTH_BAD_APIKEY")

# --- con cuenta real (opcional) --------------------------------------------
clave = os.environ.get("ALLDEBRID_APIKEY")
if clave:
    cuenta = AllDebrid(clave)
    u = cuenta.usuario()
    print("   Cuenta:", u.get("username"), "premium:", u.get("isPremium"))
    if len(sys.argv) > 1:
        enlace = sys.argv[1]
        if enlace.startswith("magnet:"):
            for nombre, tam, l in cuenta.magnet(enlace):
                print("   %s (%.1f GB)" % (nombre, tam / 1e9))
        else:
            print("   Directo:", cuenta.desbloquear(enlace)[0])

print("\n%s" % ("TODO CORRECTO" if not fallos else "%d FALLOS" % fallos))
sys.exit(1 if fallos else 0)
