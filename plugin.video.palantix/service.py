"""Servicio en segundo plano de Palantix (arranca con Kodi).

Vigila lo que se reproduce desde Palantix y:
  - Siguiente capítulo: al acercarse el final, cuenta atrás y lanza el siguiente (se puede cancelar).
  - Avisa a los módulos opcionales (Trakt, saltar intro) mediante «ganchos».

main.py deja los datos de lo que va a sonar en propiedades de la ventana principal (10000):
  palantix.meta       JSON {tipo, tmdb, s, e, titulo}
  palantix.siguiente  JSON {url, etiqueta}
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor

import xbmc
import xbmcaddon
import xbmcgui

VENTANA = xbmcgui.Window(10000)


def ajuste(clave, defecto=""):
    try:
        return xbmcaddon.Addon().getSetting(clave) or defecto
    except Exception:
        return defecto


def propiedad_json(nombre):
    try:
        return json.loads(VENTANA.getProperty(nombre) or "null")
    except ValueError:
        return None


def log(msg):
    xbmc.log("[Palantix servicio] %s" % msg, xbmc.LOGINFO)


class Reproductor(xbmc.Player):
    def __init__(self):
        super().__init__()
        self.meta = None
        self.siguiente = None
        self.ofrecido = False
        self.ganchos = []  # módulos opcionales: objetos con al_empezar/al_avanzar/al_parar
        try:
            from resources.lib import ganchos
            self.ganchos = ganchos.cargar(log)
        except Exception as e:
            log("Sin ganchos opcionales: %s" % e)

    # --- eventos de Kodi
    def onAVStarted(self):
        self.meta = propiedad_json("palantix.meta")
        self.siguiente = propiedad_json("palantix.siguiente")
        self.ofrecido = False
        # las propiedades son de un solo uso: si luego se reproduce otra cosa, no la confundimos
        VENTANA.clearProperty("palantix.meta")
        VENTANA.clearProperty("palantix.siguiente")
        if self.meta:
            log("Reproduciendo %s" % self.meta.get("titulo"))
            self.elegir_audio(self.meta.get("prioridad_audio", ()))
            self._gancho("al_empezar", self.meta, self)

    def elegir_audio(self, prioridad):
        if not prioridad or prioridad[0] not in {"LAT", "CAST"}:
            return
        from resources.lib.audio import pista_preferida

        try:
            peticion = {"jsonrpc": "2.0", "id": 1, "method": "Player.GetProperties",
                        "params": {"playerid": 1, "properties": ["audiostreams", "currentaudiostream"]}}
            respuesta = json.loads(xbmc.executeJSONRPC(json.dumps(peticion))).get("result", {})
            if not isinstance(respuesta, dict):
                return
            actual = (respuesta.get("currentaudiostream") or {}).get("index")
            pista = pista_preferida(respuesta.get("audiostreams", []), prioridad, actual)
            if pista is not None and pista != actual:
                self.setAudioStream(pista)
        except (RuntimeError, ValueError, TypeError, KeyError):
            log("Kodi no pudo aplicar el idioma de audio preferido")

    def onPlayBackStopped(self):
        self._fin(terminado=False)

    def onPlayBackEnded(self):
        self._fin(terminado=True)

    def _fin(self, terminado):
        if self.meta:
            self._gancho("al_parar", self.meta, self, terminado)
        self.meta = None
        self.siguiente = None

    def _gancho(self, nombre, *args):
        for g in self.ganchos:
            try:
                getattr(g, nombre, lambda *a: None)(*args)
            except Exception as e:
                log("Gancho %s.%s falló: %s" % (type(g).__name__, nombre, e))

    # --- cada segundo
    def vigilar(self):
        if not self.meta or not self.isPlayingVideo():
            return
        try:
            total, actual = self.getTotalTime(), self.getTime()
        except RuntimeError:
            return
        if total <= 0:
            return
        self._gancho("al_avanzar", self.meta, self, actual, total)
        quedan = total - actual
        aviso = int(ajuste("siguiente_seg", "30") or 30)
        if (self.siguiente and not self.ofrecido and ajuste("siguiente_activo", "true") == "true"
                and 0 < quedan <= aviso and total > 300):
            self.ofrecido = True
            self.ofrecer_siguiente(quedan)

    def ofrecer_siguiente(self, quedan):
        sig = self.siguiente
        espera = max(3, min(10, int(quedan) - 2))
        dlg = xbmcgui.DialogProgress()
        dlg.create("Siguiente capítulo", "%s\nEmpieza en %d s. Pulsa Cancelar para terminar de ver este." % (sig["etiqueta"], espera))
        for i in range(espera * 10):
            if dlg.iscanceled() or not self.isPlayingVideo():
                dlg.close()
                return
            dlg.update(int(100 * i / (espera * 10)),
                       "%s\nEmpieza en %d s. Pulsa Cancelar para terminar de ver este." % (sig["etiqueta"], espera - i // 10))
            xbmc.sleep(100)
        dlg.close()
        log("Siguiente capítulo: %s" % sig["etiqueta"])
        xbmc.executebuiltin("PlayMedia(%s)" % sig["url"])


def avisar_caducidad():
    """Una vez al día: avisa si alguna cuenta Debrid caduca en 7 días o menos."""
    import time
    hoy = time.strftime("%Y-%m-%d")
    addon = xbmcaddon.Addon()
    if addon.getSetting("aviso_caducidad") == "false" or addon.getSetting("ultimo_aviso") == hoy:
        return
    addon.setSetting("ultimo_aviso", hoy)
    try:
        import os
        import xbmcvfs
        from resources.lib import debrid

        class Aj:
            def get(self, k):
                return addon.getSetting(k)

            def set(self, k, v):
                addon.setSetting(k, v)

        cache = os.path.join(xbmcvfs.translatePath(addon.getAddonInfo("profile")), "cache")
        for texto in debrid.avisos_caducidad(debrid.activos(Aj(), cache_dir=cache, log=log)):
            xbmcgui.Dialog().notification("Palantix", texto, xbmcgui.NOTIFICATION_WARNING, 8000)
            log(texto)
    except Exception as e:
        log("Aviso de caducidad: %s" % e)


def comprobar_novedades():
    """Refresca las series en seguimiento y avisa de cada capítulo nuevo."""
    addon = xbmcaddon.Addon()
    clave = "".join(addon.getSetting("tmdb_key").split())
    if not clave or addon.getSetting("aviso_novedades") == "false":
        return
    try:
        import xbmcvfs
        from resources.lib import novedades, tmdb
        perfil = xbmcvfs.translatePath(addon.getAddonInfo("profile"))
        idioma, region = tmdb.idioma_de(addon.getSetting("idioma_cat") or 0)
        t = tmdb.TMDB(clave, idioma, region)
        for titulo, ult in novedades.refrescar(perfil, t, log=log):
            texto = "Nuevo capítulo de %s: %dx%02d" % (titulo, ult["s"], ult["e"])
            xbmcgui.Dialog().notification("Palantix", texto, xbmcaddon.Addon().getAddonInfo("icon"), 10000)
            log(texto)
    except Exception as e:
        log("Novedades: %s" % e)


def actualizar_solo():
    """Avisa al detectar una versión y solicita la búsqueda automática si está habilitada."""
    addon = xbmcaddon.Addon()
    try:
        from resources.lib import actualizar
        local, remota = addon.getAddonInfo("version"), actualizar.version_remota()
        if not actualizar.hay_nueva(local, remota):
            return
        if addon.getSetting("ultima_version_avisada") != remota:
            xbmcgui.Dialog().notification(
                "Palantix", "Versión %s disponible. Actualiza desde la ficha del complemento en Kodi." % remota,
                addon.getAddonInfo("icon"), 8000)
            addon.setSetting("ultima_version_avisada", remota)
        if addon.getSetting("auto_actualizar") != "false":
            actualizar.pedir_a_kodi(log)
    except Exception as e:
        log("Actualización: %s" % e)


def comprobar_fuentes():
    """Procesa un lote sin bloquear el reproductor ni los listados."""
    import xbmcvfs
    from resources.lib import disponibilidad, fuentes_catalogo, mislistas, tmdb

    addon = xbmcaddon.Addon()
    ajustes = addon.getSetting
    peliculas = ajustes("solo_peliculas_con_fuentes") == "true"
    episodios = ajustes("comprobar_fuentes_episodios") == "true"
    if not (peliculas or episodios):
        return
    perfil = xbmcvfs.translatePath(addon.getAddonInfo("profile"))
    cache = os.path.join(perfil, "cache")
    clave = tmdb.limpiar_clave(ajustes("tmdb_key"))
    idioma, region = tmdb.idioma_de(ajustes("idioma_cat") or 0)
    cliente = tmdb.TMDB(clave, idioma, region) if clave else None
    origenes = [l["origen"] for l in mislistas.leer(perfil)]
    buscar, proveedores = fuentes_catalogo.consulta(cliente, ajustes, origenes, cache, log)
    pref = fuentes_catalogo.preferencias(ajustes)
    def consultar(ficha):
        return fuentes_catalogo.hay_fuentes(ficha, buscar, pref)

    if episodios:
        disponibilidad.comprobar_lote(cache, (proveedores, pref, "episodios"), consultar)
    if peliculas:
        disponibilidad.comprobar_lote(cache, (proveedores, pref), consultar)


def main():
    monitor = xbmc.Monitor()
    reproductor = Reproductor()
    log("Arrancado")
    if not monitor.waitForAbort(20):  # dejamos que Kodi termine de arrancar
        actualizar_solo()
        avisar_caducidad()
    segundos = 0
    pendiente = None
    with ThreadPoolExecutor(max_workers=1) as consultas:
        while not monitor.abortRequested():
            reproductor.vigilar()
            if segundos % 3 == 0 and (pendiente is None or pendiente.done()):
                if pendiente is not None and pendiente.exception() is not None:
                    log("No se pudo actualizar el índice de fuentes")
                if not reproductor.isPlayingVideo():
                    pendiente = consultas.submit(comprobar_fuentes)
                else:
                    pendiente = None
            if segundos % (6 * 3600) == 40 and not reproductor.isPlayingVideo():  # al arrancar y cada 6 h
                comprobar_novedades()
                if segundos > 40:
                    actualizar_solo()
            segundos += 1
            if monitor.waitForAbort(1):
                break
    log("Parado")


if __name__ == "__main__":
    main()
