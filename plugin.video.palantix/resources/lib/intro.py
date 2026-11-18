"""Saltar intro.

Dos fuentes, sin depender de terceros:
  1. Capítulos del propio vídeo llamados «Intro», «Opening», «Cabecera»... -> botón que salta al siguiente capítulo.
  2. Lo aprendido: si en una serie adelantas a mano la intro (salto hacia delante de 20 a 180 s dentro
     de los primeros 8 minutos), se apunta inicio y fin para esa serie y en los siguientes capítulos
     aparece el botón «Saltar intro ▶▶» en ese momento.
intros.json en el perfil: {tmdb_serie: {"inicio": s, "fin": s, "veces": n}}
"""
import json
import os
import re

from . import ganchos

NOMBRE_INTRO = re.compile(r"\b(intro|opening|op|cabecera|apertura|cr[eé]ditos? iniciales|prologue)\b", re.I)
VENTANA_INICIAL = 8 * 60   # solo se aprenden saltos en los primeros 8 minutos
SALTO_MIN, SALTO_MAX = 20, 180
MARGEN = 4                 # el botón aparece un poco antes y dura unos segundos


def _ruta(perfil):
    return os.path.join(perfil, "intros.json")


def leer(perfil):
    try:
        with open(_ruta(perfil), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def guardar(perfil, datos):
    os.makedirs(perfil, exist_ok=True)
    with open(_ruta(perfil), "w", encoding="utf-8") as f:
        json.dump(datos, f)


def aprender(perfil, sid, inicio, fin):
    """Apunta (o afina, con la media) la intro de una serie."""
    datos = leer(perfil)
    previo = datos.get(str(sid))
    if previo and abs(previo["inicio"] - inicio) < 30:
        n = previo.get("veces", 1)
        inicio = (previo["inicio"] * n + inicio) / (n + 1)
        fin = (previo["fin"] * n + fin) / (n + 1)
        datos[str(sid)] = {"inicio": round(inicio, 1), "fin": round(fin, 1), "veces": n + 1}
    else:
        datos[str(sid)] = {"inicio": round(inicio, 1), "fin": round(fin, 1), "veces": 1}
    guardar(perfil, datos)


class Detector:
    """Lógica pura (sin Kodi): recibe la posición cada segundo y decide qué hacer.
    Devuelve ("ofrecer", destino) cuando hay que enseñar el botón, o None."""

    def __init__(self, perfil, meta):
        self.perfil, self.meta = perfil, meta
        self.sid = str(meta.get("tmdb")) if meta.get("tipo") == "episodio" else None
        self.intro = leer(perfil).get(self.sid) if self.sid else None
        self.anterior = None      # (posición en el vídeo, hora real)
        self.racha = None         # salto manual en curso: [inicio, fin, segundos sin saltar]
        self.ofrecido = False
        self.saltado_por_boton = False

    def paso(self, actual, capitulo="", ahora=None):
        import time
        ahora = time.time() if ahora is None else ahora
        evento = None
        # 1) capítulo del vídeo con nombre de intro
        if capitulo and NOMBRE_INTRO.search(capitulo) and not self.ofrecido:
            self.ofrecido = True
            evento = ("capitulo", None)
        # 2) intro aprendida para esta serie
        elif self.intro and not self.ofrecido and self.intro["inicio"] - 1 <= actual <= self.intro["inicio"] + MARGEN:
            self.ofrecido = True
            evento = ("ofrecer", self.intro["fin"])
        # 3) aprender: saltos manuales hacia delante al principio del capítulo.
        #    El salto se mide descontando el tiempo real transcurrido (si el vídeo avanza solo, no es salto),
        #    y varios saltos seguidos (+30, +30, +30) cuentan como uno.
        if self.sid and self.anterior is not None:
            pos0, t0 = self.anterior
            salto = (actual - pos0) - (ahora - t0)
            if salto >= 5 and not self.saltado_por_boton:
                if self.racha and self.racha[2] <= 3:
                    self.racha[1], self.racha[2] = actual, 0
                else:
                    self.racha = [pos0, actual, 0]
            elif self.racha:
                self.racha[2] += 1
                if self.racha[2] > 3:  # se acabó la racha: ¿parece una intro?
                    inicio, fin, _ = self.racha
                    if SALTO_MIN <= fin - inicio <= SALTO_MAX and inicio <= VENTANA_INICIAL:
                        aprender(self.perfil, self.sid, inicio, fin)
                        self.intro = leer(self.perfil).get(self.sid)
                    self.racha = None
        self.saltado_por_boton = False
        self.anterior = (actual, ahora)
        return evento

    def boton_usado(self):
        """El salto lo ha hecho el botón: que no se aprenda como si fuese manual."""
        self.saltado_por_boton = True


@ganchos.registrar
class SaltarIntro:
    """Gancho del servicio: enseña el botón «Saltar intro» encima del vídeo."""

    def __init__(self, perfil=None):
        import xbmcaddon
        import xbmcvfs
        self.addon = xbmcaddon.Addon()
        self.perfil = perfil or xbmcvfs.translatePath(self.addon.getAddonInfo("profile"))
        self.detector = None

    def activo(self):
        return self.addon.getSetting("intro_activo") != "false"

    def al_empezar(self, meta, reproductor):
        self.detector = Detector(self.perfil, meta)

    def al_avanzar(self, meta, reproductor, actual, total):
        import xbmc
        if not self.detector:
            return
        evento = self.detector.paso(actual, xbmc.getInfoLabel("Player.ChapterName"))
        if evento:
            tipo, destino = evento
            if mostrar_boton(self.addon):
                self.detector.boton_usado()
                if tipo == "capitulo":
                    xbmc.executebuiltin("Action(ChapterOrBigStepForward)")
                else:
                    reproductor.seekTime(float(destino))

    def al_parar(self, meta, reproductor, terminado):
        self.detector = None


def mostrar_boton(addon, segundos=10):
    """Botón «Saltar intro ▶▶» en la esquina inferior derecha. True si lo pulsan."""
    import xbmc
    import xbmcgui

    class Boton(xbmcgui.WindowXMLDialog):
        pulsado = False

        def onClick(self, control_id):
            Boton.pulsado = True
            self.close()

    ventana = Boton("palantix-saltar.xml", addon.getAddonInfo("path"), "default", "1080i")
    ventana.show()
    for _ in range(segundos * 10):
        if Boton.pulsado or not xbmc.Player().isPlayingVideo():
            break
        xbmc.sleep(100)
    ventana.close()
    del ventana
    return Boton.pulsado
