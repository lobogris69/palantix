"""Servicio en segundo plano de Palantix (arranca con Kodi).

Vigila lo que se reproduce desde Palantix y:
  - Siguiente capítulo: al acercarse el final, cuenta atrás y lanza el siguiente (se puede cancelar).
  - Avisa a los módulos opcionales (Trakt, saltar intro) mediante «ganchos».

main.py deja los datos de lo que va a sonar en propiedades de la ventana principal (10000):
  palantix.meta       JSON {tipo, tmdb, s, e, titulo}
  palantix.siguiente  JSON {url, etiqueta}
"""
import json

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
            self._gancho("al_empezar", self.meta, self)

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
        t = tmdb.TMDB(clave, addon.getSetting("idioma") or "es-ES")
        for titulo, ult in novedades.refrescar(perfil, t, log=log):
            texto = "Nuevo capítulo de %s: %dx%02d" % (titulo, ult["s"], ult["e"])
            xbmcgui.Dialog().notification("Palantix", texto, xbmcaddon.Addon().getAddonInfo("icon"), 10000)
            log(texto)
    except Exception as e:
        log("Novedades: %s" % e)


def actualizar_solo():
    """Si hay versión nueva de Palantix, avisa y pide a Kodi que la instale ya (sin esperar al día siguiente)."""
    addon = xbmcaddon.Addon()
    if addon.getSetting("auto_actualizar") == "false":
        return
    try:
        from resources.lib import actualizar
        local, remota = addon.getAddonInfo("version"), actualizar.version_remota()
        if actualizar.hay_nueva(local, remota):
            xbmcgui.Dialog().notification("Palantix", "Actualizando a la versión %s..." % remota,
                                          addon.getAddonInfo("icon"), 8000)
            actualizar.pedir_a_kodi(log)
    except Exception as e:
        log("Actualización: %s" % e)


def main():
    monitor = xbmc.Monitor()
    reproductor = Reproductor()
    log("Arrancado")
    if not monitor.waitForAbort(20):  # dejamos que Kodi termine de arrancar
        actualizar_solo()
        avisar_caducidad()
    segundos = 0
    while not monitor.abortRequested():
        reproductor.vigilar()
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
