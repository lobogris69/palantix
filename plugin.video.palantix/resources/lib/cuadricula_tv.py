"""Guía dobleM por canal con ventanas de tres horas."""
from datetime import datetime

DURACION = 3 * 3600
CANALES_POR_PAGINA = 5
IZQUIERDA, ANCHO = 365, 1480


def tramos(programas, inicio):
    fin = inicio + DURACION
    visibles = []
    for a, b, titulo in programas:
        if a >= fin or b <= inicio:
            continue
        x = IZQUIERDA + int((max(a, inicio) - inicio) * ANCHO / DURACION)
        extremo = IZQUIERDA + int((min(b, fin) - inicio) * ANCHO / DURACION)
        visibles.append((x, max(1, extremo - x), a, b, titulo))
    return visibles


def mostrar(addon, canales, programas, hora, ocultar, seleccionar):
    import xbmcgui

    class Guia(xbmcgui.WindowXMLDialog):
        def onInit(self):
            self.inicio = int(hora) - (datetime.fromtimestamp(hora).minute % 30) * 60 - int(hora) % 60
            self.minimo, self.maximo = self.inicio - DURACION, self.inicio + 15 * DURACION
            self.pagina = 0
            self.controles = []
            self.dibujar()

        def dibujar(self):
            if self.controles:
                self.removeControls(self.controles)
            self.controles, self.acciones = [], {}

            def agregar(control):
                self.addControl(control)
                self.controles.append(control)
                return control

            def boton(x, y, ancho, alto, titulo, accion, argumentos):
                control = agregar(xbmcgui.ControlButton(x, y, ancho, alto, titulo, font="font13"))
                self.acciones[control.getId()] = (accion, argumentos)
                return control

            botones = [
                boton(55, 130, 235, 60, "◀  Horas", self.mover, (-1, 0)),
                boton(300, 130, 235, 60, "Horas  ▶", self.mover, (1, 0)),
                boton(560, 130, 235, 60, "▲  Canales", self.mover, (0, -1)),
                boton(805, 130, 235, 60, "Canales  ▼", self.mover, (0, 1)),
                boton(1050, 130, 235, 60, "Opciones de TV", self.abrir_opciones, ()),
            ]
            fecha = datetime.fromtimestamp(self.inicio).strftime("%d/%m/%Y")
            agregar(xbmcgui.ControlLabel(1450, 135, 390, 50, fecha, font="font27"))
            for h in range(6):
                reloj = datetime.fromtimestamp(self.inicio + h * 1800).strftime("%H:%M")
                agregar(xbmcgui.ControlLabel(IZQUIERDA + h * ANCHO // 6, 220, 225, 50, reloj, font="font13"))
            filas = [[(55 + i * 250, b) for i, b in enumerate(botones)]]
            primer_canal = None
            recorte = list(canales.items())[self.pagina:self.pagina + CANALES_POR_PAGINA]
            for indice, (cid, (nombre, enlace)) in enumerate(recorte):
                y = 290 + indice * 125
                agregar(xbmcgui.ControlLabel(65, y + 20, 285, 65, nombre, font="font13"))
                bloques = tramos(programas.get(cid, []), self.inicio) or [
                    (IZQUIERDA, ANCHO, self.inicio, self.inicio + DURACION, "")]
                controles = []
                for x, ancho, inicio, fin, titulo in bloques:
                    if ancho < 7:
                        continue
                    if titulo and ocultar and fin <= hora:
                        titulo = "Programa anterior"
                    argumentos = (nombre, enlace, inicio, fin, titulo)
                    reloj = datetime.fromtimestamp(inicio).strftime("%H:%M")
                    n = max(2, (ancho - 12) // 13)
                    corta = titulo[:n - 1] + "…" if len(titulo) > n else titulo
                    etiqueta = ((reloj + "  " + corta) if ancho >= 140 else corta) if titulo else ""
                    control = boton(x, y, ancho - 3, 88, etiqueta, self.programa, argumentos)
                    if primer_canal is None and (not titulo or inicio <= hora < fin):
                        primer_canal = control
                    controles.append((x + ancho // 2, control))
                if controles:
                    filas.append(controles)

            for i, fila in enumerate(filas):
                anterior, siguiente = filas[max(0, i - 1)], filas[min(i + 1, len(filas) - 1)]
                for j, (x, control) in enumerate(fila):
                    arriba = min(anterior, key=lambda item: abs(item[0] - x))[1]
                    abajo = min(siguiente, key=lambda item: abs(item[0] - x))[1]
                    control.setNavigation(arriba, abajo, fila[max(0, j - 1)][1],
                                          fila[min(j + 1, len(fila) - 1)][1])
            if self.inicio <= hora < self.inicio + DURACION:
                x = IZQUIERDA + int((hora - self.inicio) * ANCHO / DURACION)
                agregar(xbmcgui.ControlLabel(x, 268, 120, 35, "▾ AHORA", font="font13", textColor="FF76D6FF"))
            self.setFocus((primer_canal or botones[0]) if self.foco is None else botones[self.foco])

        def mover(self, horas, canales_delta):
            self.foco = (1 if horas > 0 else 0) if horas else (3 if canales_delta > 0 else 2)
            if horas:
                self.inicio = max(self.minimo, min(self.maximo, self.inicio + horas * DURACION))
            if canales_delta:
                pagina = self.pagina + canales_delta * CANALES_POR_PAGINA
                if 0 <= pagina < len(canales):
                    self.pagina = pagina
            self.dibujar()

        def abrir_opciones(self):
            self.opciones = True
            self.close()

        def programa(self, *args):
            if seleccionar(*args):
                self.close()

        def onAction(self, accion):
            if accion.getId() in (9, 10, 92):
                self.close()

        def onClick(self, control_id):
            if control_id in self.acciones:
                accion, argumentos = self.acciones[control_id]
                accion(*argumentos)

    ventana = Guia("palantix-guia.xml", addon.getAddonInfo("path"), "default", "1080i")
    ventana.foco = None
    ventana.opciones = False
    ventana.doModal()
    return ventana.opciones
