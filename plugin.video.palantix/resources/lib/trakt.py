"""Trakt.tv: vinculación con código en pantalla, «visto» automático (scrobble), valoraciones,
lista de pendientes (watchlist) y listas personales.

Usa el Client ID de la aplicación para vincular una cuenta con código de dispositivo.
"""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import json
import os
import random
from tempfile import NamedTemporaryFile
import time
import urllib.error
import urllib.request

from . import ganchos

API = "https://api.trakt.tv"
CLIENT_ID_PALANTIX = "W6qEUdrilK5ucvZgQOEViv2VbkjASxcgergDvXu_6Co"
REDIRECT = "urn:ietf:wg:oauth:2.0:oob"
CACHE_VISTOS = "trakt-vistos.json"
NOTAS = ["10 · Obra maestra", "9 · Excelente", "8 · Muy buena", "7 · Buena", "6 · Está bien", "5 · Regular",
         "4 · Flojita", "3 · Mala", "2 · Muy mala", "1 · Horrible"]


class TraktError(Exception):
    pass


class Trakt:
    id, nombre, tipo_vinculo = "trakt", "Trakt", "pin"

    def __init__(self, ajustes, log=print, timeout=20):
        self.aj, self.log, self.timeout = ajustes, log, timeout

    # ------------------------------------------------------------ estado
    def client_id(self):
        return self.aj.get("trakt_client_id").strip() or CLIENT_ID_PALANTIX

    def configurado(self):
        return bool(self.client_id())

    def vinculado(self):
        return bool(self.aj.get("trakt_token"))

    def encendido(self):
        return self.aj.get("trakt_activo") == "true" and self.vinculado()

    # ------------------------------------------------------------ transporte
    def _pedir(self, metodo, ruta, cuerpo=None, auth=True, reintento=True):
        if not self.configurado():
            raise TraktError("Falta el Client ID de la aplicación de Trakt (Ajustes > Trakt)")
        if auth and self.aj.get("trakt_refresh") and float(self.aj.get("trakt_caduca") or 0) < time.time() + 3600:
            self._renovar()
        cab = {"Content-Type": "application/json", "trakt-api-version": "2",
               "trakt-api-key": self.client_id(), "User-Agent": "Palantix/0.3"}
        if auth and self.aj.get("trakt_token"):
            cab["Authorization"] = "Bearer " + self.aj.get("trakt_token")
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        req = urllib.request.Request(API + ruta, data=datos, headers=cab, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                texto = r.read().decode("utf-8")
                return r.status, (json.loads(texto) if texto.strip() else {})
        except urllib.error.HTTPError as e:
            if e.code == 401 and auth and reintento and self.aj.get("trakt_refresh"):
                self._renovar()
                return self._pedir(metodo, ruta, cuerpo, auth, reintento=False)
            texto = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(texto) if texto.strip() else {}
            except ValueError:
                return e.code, {}

    def _ok(self, metodo, ruta, cuerpo=None):
        cod, r = self._pedir(metodo, ruta, cuerpo)
        if cod >= 400:
            raise TraktError("Trakt respondió %d%s" % (cod, (": " + r.get("error_description", "")) if isinstance(r, dict) else ""))
        return r

    def _guardar_token(self, r):
        self.aj.set("trakt_token", r["access_token"])
        self.aj.set("trakt_refresh", r.get("refresh_token", ""))
        self.aj.set("trakt_caduca", str(int(r.get("created_at", time.time())) + int(r.get("expires_in", 7776000))))

    def _credenciales_oauth(self):
        datos = {"client_id": self.client_id()}
        secreto = self.aj.get("trakt_client_secret")
        if secreto and self.aj.get("trakt_client_id").strip():
            datos["client_secret"] = secreto
        return datos

    def _renovar(self):
        cod, r = self._pedir("POST", "/oauth/token", {
            **self._credenciales_oauth(), "refresh_token": self.aj.get("trakt_refresh"),
            "redirect_uri": REDIRECT,
            "grant_type": "refresh_token"}, auth=False)
        if cod >= 400 or "access_token" not in r:
            raise TraktError("La sesión de Trakt ha caducado: vuelve a vincular")
        self._guardar_token(r)

    # ------------------------------------------------------------ vinculación (misma forma que los Debrid)
    def iniciar_pin(self):
        cod, d = self._pedir("POST", "/oauth/device/code", {"client_id": self.client_id()}, auth=False)
        if cod >= 400 or "user_code" not in d:
            raise TraktError("Trakt no reconoce tu Client ID: revisa Ajustes > Trakt")
        return {"url": d.get("verification_url", "https://trakt.tv/activate"), "codigo": d["user_code"],
                "intervalo": int(d.get("interval", 5)), "expira": int(d.get("expires_in", 600)), "datos": d}

    def comprobar_pin(self, datos):
        cod, r = self._pedir("POST", "/oauth/device/token", {
            **self._credenciales_oauth(), "code": datos["device_code"]}, auth=False)
        if cod == 200 and "access_token" in r:
            self._guardar_token(r)
            self.aj.set("trakt_activo", "true")
            return True
        if cod in (400, 429):  # aún pendiente / ir más despacio
            return False
        raise TraktError({404: "Código no válido", 409: "Ese código ya se usó", 410: "El código ha caducado",
                          418: "Has denegado el acceso en Trakt"}.get(cod, "Trakt respondió %d" % cod))

    def cuenta(self):
        u = self._ok("GET", "/users/settings").get("user", {})
        return "%s%s" % (u.get("username", "?"), " · VIP" if u.get("vip") else "")

    # ------------------------------------------------------------ contenido
    @staticmethod
    def _cuerpo(meta):
        """Cuerpo de Trakt para una película o un capítulo a partir del meta de Palantix."""
        if meta.get("tipo") == "episodio":
            return {"show": {"ids": {"tmdb": int(meta["tmdb"])}},
                    "episode": {"season": int(meta["s"]), "number": int(meta["e"])}}
        return {"movie": {"ids": {"tmdb": int(meta["tmdb"])}}}

    def scrobble(self, accion, meta, porcentaje):
        cuerpo = self._cuerpo(meta)
        cuerpo["progress"] = round(max(0.0, min(100.0, porcentaje)), 2)
        cod, r = self._pedir("POST", "/scrobble/" + accion, cuerpo)
        if cod == 409:  # ya se había marcado hace un momento: no es un error
            return r
        if cod >= 400:
            raise TraktError("Trakt no apuntó la reproducción (%d)" % cod)
        return r

    def valorar(self, meta, nota):
        if meta.get("tipo") == "episodio":
            cuerpo = {"shows": [{"ids": {"tmdb": int(meta["tmdb"])}, "seasons": [
                {"number": int(meta["s"]), "episodes": [{"number": int(meta["e"]), "rating": int(nota)}]}]}]}
        else:
            cuerpo = {"movies": [{"ids": {"tmdb": int(meta["tmdb"])}, "rating": int(nota)}]}
        return self._ok("POST", "/sync/ratings", cuerpo)

    def marcar_visto(self, meta, visto):
        contenido = self._cuerpo(meta)
        if meta.get("tipo") == "episodio":
            episodio = contenido["episode"]
            cuerpo = {"shows": [dict(contenido["show"], seasons=[
                {"number": episodio["season"], "episodes": [{"number": episodio["number"]}]}
            ])]}
        else:
            cuerpo = {"movies": [contenido["movie"]]}
        return self._ok("POST", "/sync/history" + ("" if visto else "/remove"), cuerpo)

    def cambiar_pendiente(self, tipo, tmdb_id, poner):
        return self._ok("POST", "/sync/watchlist" + ("" if poner else "/remove"),
                        {tipo: [{"ids": {"tmdb": int(tmdb_id)}}]})

    def pendientes(self, tipo):
        """Lista de pendientes: tipo 'movies' o 'shows' -> [(tmdb_id, titulo, anio)]"""
        clave = "movie" if tipo == "movies" else "show"
        return [(x[clave]["ids"].get("tmdb"), x[clave].get("title"), x[clave].get("year"))
                for x in self._ok("GET", "/sync/watchlist/%s" % tipo) if x.get(clave, {}).get("ids", {}).get("tmdb")]

    def _sesion_cache(self):
        datos = self.client_id() + "\0" + self.aj.get("trakt_token")
        return sha256(datos.encode()).hexdigest()

    def historial_episodios(self, cache):
        """Historial de episodios vistos por ID TMDB. La caché pertenece a la sesión vinculada."""
        if not self.encendido():
            return {}
        ruta = Path(cache) / CACHE_VISTOS
        sesion = self._sesion_cache()
        guardado = {}
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            if datos["sesion"] == sesion and isinstance(datos["series"], dict):
                edad = time.time() - datos["fecha"]
                if 0 <= edad < 120:
                    return datos["series"]
                if 0 <= edad < 86400:
                    guardado = datos["series"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        try:
            filas = self._ok("GET", "/sync/watched/shows")
            if not isinstance(filas, list):
                raise TraktError("Trakt devolvió un historial no válido")
            series = {}
            for fila in filas:
                tmdb = fila["show"]["ids"].get("tmdb")
                if not tmdb:
                    continue
                vistos = series.setdefault(str(tmdb), set())
                for temp in fila["seasons"]:
                    vistos.update("%d:%d" % (temp["number"], ep["number"])
                                  for ep in temp["episodes"] if ep.get("plays", 0) > 0)
            series = {sid: sorted(vistos) for sid, vistos in series.items()}
        except (OSError, ValueError, KeyError, TypeError, AttributeError, TraktError):
            self.log("No se pudo leer el historial de episodios de Trakt")
            return guardado

        if self._sesion_cache() != sesion:
            return series  # una renovación de sesión se reflejará en la próxima consulta
        temporal = None
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=ruta.parent, mode="w", encoding="utf-8", delete=False) as fichero:
                temporal = Path(fichero.name)
                json.dump({"sesion": sesion, "fecha": time.time(), "series": series}, fichero)
            os.replace(temporal, ruta)
        except OSError:
            self.log("No se pudo guardar el historial de episodios de Trakt")
        finally:
            if temporal:
                try:
                    temporal.unlink(missing_ok=True)
                except OSError:
                    pass
        return series

    def progreso_series(self, pagina, limite=12):
        """Una página del historial, con la cuenta vinculada como origen del progreso."""
        ruta = "/sync/watched/shows?page=%d&limit=%d" % (pagina, limite)
        vistas = self._ok("GET", ruta)
        if not isinstance(vistas, list):
            raise TraktError("Trakt devolvió un historial no válido")
        vistas = sorted(vistas, key=lambda fila: fila.get("last_watched_at") or "", reverse=True)

        def completa(fila):
            serie = fila.get("show") or {}
            tid = (serie.get("ids") or {}).get("trakt")
            if not tid:
                return serie, None
            try:
                progreso = self._ok("GET", "/shows/%d/progress/watched" % tid)
                if isinstance(progreso, dict) and all(isinstance(progreso.get(k), int)
                                                      for k in ("aired", "completed")):
                    return serie, progreso
            except (OSError, ValueError, TraktError):
                self.log("No se pudo obtener el progreso de una serie de Trakt")
            return serie, None

        # Los servidores que ignoren la paginación devuelven el historial entero.
        if len(vistas) > limite:
            comienzo = (pagina - 1) * limite
            resultado = vistas[comienzo:comienzo + limite]
            hay_mas = comienzo + limite < len(vistas)
        else:
            resultado = vistas
            hay_mas = len(vistas) == limite
        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(completa, resultado)), hay_mas

    def listas(self):
        """Listas personales: [(id, nombre, número de elementos)]"""
        return [(x["ids"]["trakt"], x.get("name", "?"), x.get("item_count", 0)) for x in self._ok("GET", "/users/me/lists")]

    def lista(self, lista_id):
        """Elementos de una lista: [(tipo 'pelicula'|'serie', tmdb_id, titulo, anio)]"""
        salida = []
        for x in self._ok("GET", "/users/me/lists/%s/items/movie,show" % lista_id):
            if x.get("type") in ("movie", "show"):
                o = x[x["type"]]
                if o.get("ids", {}).get("tmdb"):
                    salida.append(("pelicula" if x["type"] == "movie" else "serie", o["ids"]["tmdb"], o.get("title"), o.get("year")))
        return salida


def toca_preguntar(modo, azar=random.random):
    """modo 0 nunca, 1 a veces (1 de cada 3), 2 siempre."""
    return modo == 2 or (modo == 1 and azar() < 1 / 3.0)


@ganchos.registrar
class TraktGancho:
    """Gancho del servicio: avisa a Trakt al empezar y al parar, y pregunta la nota al terminar."""
    VISTO = 80.0  # Trakt marca como visto a partir del 80 %

    def __init__(self, ajustes=None, preguntar=None, log=None):
        if ajustes is None:
            import xbmcaddon

            class _Aj:
                def get(self, k):
                    return xbmcaddon.Addon().getSetting(k)

                def set(self, k, v):
                    xbmcaddon.Addon().setSetting(k, v)
            ajustes = _Aj()
        if log is None:
            import xbmc
            log = lambda m: xbmc.log("[Palantix Trakt] %s" % m, xbmc.LOGINFO)
        self.t, self.aj, self.log = Trakt(ajustes, log), ajustes, log
        self.preguntar = preguntar or self._preguntar_kodi
        self.pct = 0.0

    def al_empezar(self, meta, reproductor):
        self.pct = 0.0
        if self.t.encendido():
            self._seguro("start", meta, 0.1)

    def al_avanzar(self, meta, reproductor, actual, total):
        if total > 0:
            self.pct = 100.0 * actual / total

    def al_parar(self, meta, reproductor, terminado):
        if not self.t.encendido():
            return
        pct = 100.0 if terminado else self.pct
        self._seguro("stop", meta, pct)
        try:
            modo = int(self.aj.get("trakt_valorar") or 1)
        except ValueError:
            modo = 1
        if pct >= self.VISTO and toca_preguntar(modo):
            nota = self.preguntar(meta)
            if nota:
                try:
                    self.t.valorar(meta, nota)
                except Exception as e:
                    self.log("No se pudo guardar la nota: %s" % e)

    def _seguro(self, accion, meta, pct):
        try:
            self.t.scrobble(accion, meta, pct)
        except Exception as e:
            self.log("scrobble %s: %s" % (accion, e))

    @staticmethod
    def _preguntar_kodi(meta):
        import xbmcgui
        titulo = meta.get("titulo", "")
        if meta.get("tipo") == "episodio":
            titulo = "%s %sx%02d" % (titulo, meta.get("s"), int(meta.get("e") or 0))
        n = xbmcgui.Dialog().select("¿Qué te ha parecido «%s»?" % titulo, NOTAS, autoclose=30000)
        return 10 - n if n >= 0 else None
