"""Intercambio temporal de preferencias no sensibles en la red local."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import secrets

from . import preferencias_copia

PAGINA = b"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width">
<title>Preferencias de Palantix</title><h1>Preferencias de Palantix</h1>
<p><a href="preferencias.json" download>Descargar preferencias de esta tele</a></p>
<label>Importar preferencias en la tele <input id="archivo" type="file" accept=".json"></label>
<button id="enviar">Enviar a la tele</button><p id="estado"></p>
<script>
document.querySelector('#enviar').onclick = async () => {
  const archivo = document.querySelector('#archivo').files[0];
  if (!archivo || archivo.size > 8192) return;
  const r = await fetch(location.pathname, {method:'POST', body:await archivo.text()});
  document.querySelector('#estado').textContent = r.ok ? 'Confirma en la tele.' : 'Archivo no valido.';
};
</script>"""


def servidor(ip, preferencias):
    ip = ipaddress.IPv4Address(ip)
    if not ip.is_private or ip.is_loopback or ip.is_unspecified:
        raise ValueError("Se necesita una dirección IPv4 local")
    ruta = "/" + secrets.token_urlsafe(24) + "/"

    class Peticion(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(1)
            super().setup()

        def log_message(self, *args):
            pass

        def responder(self, codigo, contenido=b"", tipo="text/plain"):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(contenido)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(contenido)

        def do_GET(self):
            if self.path == ruta:
                return self.responder(200, PAGINA, "text/html; charset=utf-8")
            if self.path == ruta + "preferencias.json":
                return self.responder(200, preferencias.encode(), "application/json")
            self.responder(404)

        def do_POST(self):
            if self.path != ruta or self.server.datos is not None:
                return self.responder(404)
            try:
                longitud = int(self.headers.get("Content-Length", 0))
                if not 0 < longitud <= preferencias_copia.MAX_BYTES:
                    raise ValueError()
                datos = preferencias_copia.importar(self.rfile.read(longitud).decode("utf-8"))
            except (OSError, ValueError):
                return self.responder(400)
            self.server.datos = datos
            self.responder(200)

    sesion = HTTPServer((str(ip), 0), Peticion)
    sesion.timeout = 0.25
    sesion.datos = None
    return sesion, "http://%s:%d%s" % (ip, sesion.server_port, ruta)
