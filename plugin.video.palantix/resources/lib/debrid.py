"""Centro de servicios Debrid: todos con la misma forma de uso.

Cada servicio sabe: si admite una URL, convertirla en enlace directo, vincular la cuenta
(PIN / código en pantalla o clave) y resumir el estado de la cuenta.
`ajustes` es cualquier objeto con get(clave) y set(clave, valor) (en Kodi, los ajustes del addon).
Solo librería estándar: se prueba fuera de Kodi.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlparse

from . import alldebrid as ad_mod
from .http import AGENTE

VIDEO = ad_mod.VIDEO


class DebridError(Exception):
    pass


class NoListo(Exception):
    """El magnet aún no está descargado en el servicio: queda descargándose para más tarde."""


def _peticion(url, datos=None, cabeceras=None, metodo=None):
    """Devuelve (código_http, json). No lanza por 4xx: los servicios mandan el error en JSON."""
    c = {"User-Agent": AGENTE, "Accept": "application/json"}
    c.update(cabeceras or {})
    cuerpo = None
    if datos is not None:
        cuerpo = urlencode(datos, doseq=True).encode()
        c["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=cuerpo, headers=c, method=metodo or ("POST" if cuerpo is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            texto = r.read().decode("utf-8")
            return r.status, (json.loads(texto) if texto.strip() else {})
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(texto) if texto.strip() else {}
        except ValueError:
            return e.code, {"error": texto[:200]}


def _host_en(url, dominios):
    host = (urlparse(url).hostname or "").lower()
    partes = host.split(".")
    return any(".".join(partes[i:]) in dominios for i in range(len(partes) - 1))


def _cache_json(cache_dir, nombre, ttl, obtener):
    ruta = os.path.join(cache_dir, nombre) if cache_dir else None
    if ruta and os.path.exists(ruta) and time.time() - os.path.getmtime(ruta) < ttl:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    datos = obtener()
    if ruta:
        os.makedirs(cache_dir, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f)
    return datos


def solo_videos(ficheros):
    """[(nombre, tamaño, dato)] -> solo vídeos, sin «sample», de mayor a menor."""
    v = [f for f in ficheros if f[0].lower().endswith(VIDEO)]
    v = [f for f in v if not re.search(r"\bsample\b", f[0], re.I)] or v
    return sorted(v, key=lambda f: -f[1])


class Servicio:
    id = "base"
    nombre = "Base"
    tipo_vinculo = "pin"  # "pin" (código en pantalla) o "clave" (se pega la API key)

    def __init__(self, ajustes, cache_dir=None, log=print, espera=time.sleep):
        self.aj, self.cache_dir, self.log, self.espera = ajustes, cache_dir, log, espera

    def encendido(self):
        return self.aj.get(self.id + "_activo") == "true"

    def vinculado(self):
        raise NotImplementedError

    def admite(self, url):
        raise NotImplementedError

    def resolver(self, url, elegir=lambda videos: 0, cancelado=lambda: False):
        raise NotImplementedError

    def iniciar_pin(self):
        """-> {'url', 'codigo', 'intervalo', 'expira', 'datos'}"""
        raise NotImplementedError

    def comprobar_pin(self, datos):
        """True si ya está vinculado (y guarda las credenciales)."""
        raise NotImplementedError

    def cuenta(self):
        raise NotImplementedError

    def dias_restantes(self):
        """Días de premium que quedan, o None si no se sabe."""
        return None


# ---------------------------------------------------------------------- AllDebrid
class AllDebridServicio(Servicio):
    id, nombre = "ad", "AllDebrid"

    def _cli(self):
        return ad_mod.AllDebrid(self.aj.get("ad_apikey"), log=self.log, espera=self.espera)

    def vinculado(self):
        return bool(self.aj.get("ad_apikey"))

    def admite(self, url):
        return self._cli().necesita(url, self._cli().dominios(self.cache_dir))

    def resolver(self, url, elegir=lambda v: 0, cancelado=lambda: False):
        c = self._cli()
        try:
            if url.startswith("magnet:"):
                videos = solo_videos(c.magnet(url))
                if not videos:
                    raise DebridError("El magnet no contiene vídeos")
                n = 0 if len(videos) == 1 else elegir(videos)
                if n < 0:
                    raise DebridError("Cancelado")
                url = videos[n][2]
            return c.desbloquear(url, cancelado=cancelado)[0]
        except ad_mod.NoListo as e:
            raise NoListo(str(e))
        except ad_mod.AllDebridError as e:
            raise DebridError(str(e))

    def iniciar_pin(self):
        d = self._cli().pin_get()
        return {"url": d.get("user_url", "https://alldebrid.com/pin/"), "codigo": d["pin"], "intervalo": 5,
                "expira": int(d.get("expires_in", 600)), "datos": d}

    def comprobar_pin(self, datos):
        try:
            clave = ad_mod.AllDebrid().pin_check(datos["pin"], datos["check"])
        except ad_mod.AllDebridError as e:
            raise DebridError(str(e))
        if clave:
            self.aj.set("ad_apikey", clave)
            self.aj.set("ad_activo", "true")
            return True
        return False

    def dias_restantes(self):
        hasta = self._cli().usuario().get("premiumUntil") or 0
        return max(0, int((hasta - time.time()) // 86400)) if hasta else None

    def cuenta(self):
        u = self._cli().usuario()
        hasta = u.get("premiumUntil") or 0
        return "%s · premium: %s%s" % (u.get("username", "?"), "sí" if u.get("isPremium") else "no",
                                       time.strftime(" hasta el %d-%m-%Y", time.localtime(hasta)) if hasta else "")


# ---------------------------------------------------------------------- Real-Debrid
class RealDebrid(Servicio):
    """API REST 1.0 + OAuth de dispositivo con el client_id para apps de código abierto."""
    id, nombre = "rd", "Real-Debrid"
    REST = "https://api.real-debrid.com/rest/1.0"
    OAUTH = "https://api.real-debrid.com/oauth/v2"
    CLIENTE_ABIERTO = "X245A4XAIBGVM"
    GRANT = "http://oauth.net/grant_type/device/1.0"
    ERRORES = {8: "La sesión de Real-Debrid ha caducado: vuelve a vincular", 9: "Real-Debrid deniega el permiso",
               18: "Límite diario de ese alojamiento alcanzado", 23: "Tráfico de Real-Debrid agotado",
               24: "El fichero ya no está disponible", 34: "Demasiadas peticiones, espera un poco",
               35: "Contenido bloqueado por Real-Debrid", 16: "Alojamiento no admitido"}

    def vinculado(self):
        return bool(self.aj.get("rd_token"))

    # --- transporte con renovación automática del token
    def _api(self, ruta, datos=None, metodo=None, reintento=True):
        if float(self.aj.get("rd_caduca") or 0) < time.time() + 60 and self.aj.get("rd_refresh"):
            self._renovar()
        cod, r = _peticion(self.REST + ruta, datos, {"Authorization": "Bearer " + self.aj.get("rd_token")}, metodo)
        if cod == 401 and reintento and self.aj.get("rd_refresh"):
            self._renovar()
            return self._api(ruta, datos, metodo, reintento=False)
        if cod >= 400:
            codigo = r.get("error_code") if isinstance(r, dict) else None
            raise DebridError(self.ERRORES.get(codigo, "Real-Debrid: %s" % (r.get("error") if isinstance(r, dict) else cod)))
        return r

    def _renovar(self):
        cod, r = _peticion(self.OAUTH + "/token", {
            "client_id": self.aj.get("rd_client_id"), "client_secret": self.aj.get("rd_client_secret"),
            "code": self.aj.get("rd_refresh"), "grant_type": self.GRANT})
        if cod >= 400 or "access_token" not in r:
            raise DebridError("No se pudo renovar la sesión de Real-Debrid: vuelve a vincular")
        self._guardar_token(r)

    def _guardar_token(self, r):
        self.aj.set("rd_token", r["access_token"])
        self.aj.set("rd_refresh", r.get("refresh_token", self.aj.get("rd_refresh")))
        self.aj.set("rd_caduca", str(int(time.time() + int(r.get("expires_in", 3600)))))

    # --- capacidades
    def admite(self, url):
        if url.startswith("magnet:"):
            return True
        doms = _cache_json(self.cache_dir, "rd_dominios.json", 86400,
                           lambda: _peticion(self.REST + "/hosts/domains")[1])
        return _host_en(url, set(doms if isinstance(doms, list) else []))

    def _desbloquear(self, enlace):
        r = self._api("/unrestrict/link", {"link": enlace})
        if not r.get("download"):
            raise DebridError("Real-Debrid no devolvió enlace")
        return r["download"]

    def resolver(self, url, elegir=lambda v: 0, cancelado=lambda: False):
        if not url.startswith("magnet:"):
            return self._desbloquear(url)
        tid = self._api("/torrents/addMagnet", {"magnet": url})["id"]
        info = self._esperar(tid, ("waiting_files_selection", "downloaded"), 20, cancelado)
        if info["status"] == "waiting_files_selection":
            ids = [str(f["id"]) for f in info.get("files", []) if f["path"].lower().endswith(VIDEO)]
            if not ids:
                raise DebridError("El magnet no contiene vídeos")
            self._api("/torrents/selectFiles/%s" % tid, {"files": ",".join(ids)})
            info = self._esperar(tid, ("downloaded",), 8, cancelado)
        if info["status"] != "downloaded":
            raise NoListo("El magnet se está descargando en Real-Debrid (%s%%); prueba más tarde" % info.get("progress", 0))
        # Real-Debrid da un enlace por cada fichero seleccionado, en el mismo orden
        elegidos = [f for f in info.get("files", []) if f.get("selected")]
        pares = [(f["path"].lstrip("/"), int(f.get("bytes") or 0), l) for f, l in zip(elegidos, info.get("links", []))]
        videos = solo_videos(pares)
        if not videos:
            raise DebridError("El magnet no contiene vídeos")
        n = 0 if len(videos) == 1 else elegir(videos)
        if n < 0:
            raise DebridError("Cancelado")
        return self._desbloquear(videos[n][2])

    EN_CURSO = ("queued", "downloading", "compressing", "uploading")  # no hay que esperar: no estará en segundos
    ROTO = ("magnet_error", "error", "virus", "dead")

    def _esperar(self, tid, estados, segundos, cancelado):
        fin = time.time() + segundos
        while True:
            info = self._api("/torrents/info/%s" % tid)
            estado = info.get("status")
            if estado in self.ROTO:
                raise DebridError("Real-Debrid no puede con este magnet (%s)" % estado)
            if estado in estados or estado in self.EN_CURSO:
                return info
            if time.time() > fin or cancelado():
                return info
            self.espera(2)

    # --- vinculación por código en pantalla
    def iniciar_pin(self):
        cod, d = _peticion(self.OAUTH + "/device/code?" + urlencode(
            {"client_id": self.CLIENTE_ABIERTO, "new_credentials": "yes"}))
        if cod >= 400 or "user_code" not in d:
            raise DebridError("Real-Debrid no dio código")
        return {"url": d.get("verification_url", "https://real-debrid.com/device"), "codigo": d["user_code"],
                "intervalo": int(d.get("interval", 5)), "expira": int(d.get("expires_in", 1800)), "datos": d}

    def comprobar_pin(self, datos):
        cod, cred = _peticion(self.OAUTH + "/device/credentials?" + urlencode(
            {"client_id": self.CLIENTE_ABIERTO, "code": datos["device_code"]}))
        if cod >= 400 or "client_secret" not in cred:
            return False  # aún no autorizado
        cod, tok = _peticion(self.OAUTH + "/token", {"client_id": cred["client_id"], "client_secret": cred["client_secret"],
                                                     "code": datos["device_code"], "grant_type": self.GRANT})
        if cod >= 400 or "access_token" not in tok:
            raise DebridError("Real-Debrid no entregó la sesión")
        self.aj.set("rd_client_id", cred["client_id"])
        self.aj.set("rd_client_secret", cred["client_secret"])
        self._guardar_token(tok)
        self.aj.set("rd_activo", "true")
        return True

    def dias_restantes(self):
        segundos = self._api("/user").get("premium")
        return max(0, int(segundos) // 86400) if segundos is not None else None

    def cuenta(self):
        u = self._api("/user")
        return "%s · %s%s" % (u.get("username", "?"), u.get("type", "?"),
                              (" hasta el %s" % u["expiration"][:10]) if u.get("expiration") else "")


# ---------------------------------------------------------------------- Premiumize
class Premiumize(Servicio):
    """API con la clave de la cuenta (premiumize.me/account) por cabecera Bearer."""
    id, nombre = "pm", "Premiumize"
    tipo_vinculo = "clave"
    API = "https://www.premiumize.me/api"

    def vinculado(self):
        return bool(self.aj.get("pm_apikey"))

    def _api(self, ruta, datos=None):
        cod, r = _peticion(self.API + ruta, datos, {"Authorization": "Bearer " + self.aj.get("pm_apikey")})
        if cod >= 400 or r.get("status") != "success":
            raise DebridError("Premiumize: %s" % (r.get("message") or cod))
        return r

    def admite(self, url):
        if url.startswith("magnet:"):
            return True
        def obtener():
            s = self._api("/services/list")
            doms = set(s.get("directdl", [])) | set(s.get("cache", []))
            for lista in (s.get("aliases") or {}).values():
                doms |= set(lista)
            return sorted(doms)
        return _host_en(url, set(_cache_json(self.cache_dir, "pm_dominios.json", 86400, obtener)))

    def resolver(self, url, elegir=lambda v: 0, cancelado=lambda: False):
        if url.startswith("magnet:"):
            cache = self._api("/cache/check", {"items[]": [url]})
            if not (cache.get("response") or [False])[0]:
                self._api("/transfer/create", {"src": url})
                raise NoListo("No estaba en Premiumize: se está descargando en tu nube; prueba más tarde")
        r = self._api("/transfer/directdl", {"src": url})
        videos = solo_videos([(c.get("path", ""), int(c.get("size") or 0), c.get("link")) for c in r.get("content", [])])
        if not videos:
            raise DebridError("Premiumize no devolvió vídeos")
        n = 0 if len(videos) == 1 else elegir(videos)
        if n < 0:
            raise DebridError("Cancelado")
        return videos[n][2]

    def dias_restantes(self):
        hasta = self._api("/account/info").get("premium_until") or 0
        return max(0, int((hasta - time.time()) // 86400)) if hasta else None

    def cuenta(self):
        r = self._api("/account/info")
        hasta = r.get("premium_until") or 0
        return "Cliente %s%s" % (r.get("customer_id", "?"),
                                 time.strftime(" · premium hasta el %d-%m-%Y", time.localtime(hasta)) if hasta else "")


# ---------------------------------------------------------------------- centro
SERVICIOS = [AllDebridServicio, RealDebrid, Premiumize]


def activos(ajustes, **kw):
    servicios = [S(ajustes, **kw) for S in SERVICIOS]
    return [s for s in servicios if s.encendido() and s.vinculado()]


def por_id(sid, ajustes, **kw):
    return next(S(ajustes, **kw) for S in SERVICIOS if S.id == sid)


def resolver(url, servicios, elegir=lambda v: 0, cancelado=lambda: False, log=print):
    """Prueba los servicios en orden. Devuelve la URL directa.
    Si ninguno admite la URL, la devuelve tal cual (enlace directo normal)."""
    ultimo = None
    alguno = False
    for s in servicios:
        try:
            if not s.admite(url):
                continue
            alguno = True
            return s.resolver(url, elegir=elegir, cancelado=cancelado)
        except NoListo as e:
            ultimo = e
        except DebridError as e:
            log("[Palantix] %s: %s" % (s.nombre, e))
            ultimo = e
        except Exception as e:  # red caída, respuesta rara...
            log("[Palantix] %s fallo inesperado: %s" % (s.nombre, e))
            ultimo = DebridError("%s no responde" % s.nombre)
    if ultimo:
        raise ultimo
    if url.startswith("magnet:") and not alguno:
        raise DebridError("Para magnets activa y vincula un servicio Debrid en Ajustes")
    return url


def avisos_caducidad(servicios, umbral=7):
    """['Real-Debrid caduca en 3 días', ...] para las cuentas a punto de caducar."""
    salida = []
    for s in servicios:
        try:
            d = s.dias_restantes()
        except Exception:
            continue
        if d is not None and d <= umbral:
            salida.append("%s %s" % (s.nombre, "ha caducado" if d == 0 else "caduca en %d día%s" % (d, "" if d == 1 else "s")))
    return salida
