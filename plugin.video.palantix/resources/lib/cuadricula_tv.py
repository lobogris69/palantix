"""Guía dobleM por canal con ventanas de tres horas."""
from datetime import datetime
from pathlib import Path

DURACION = 3 * 3600
CANALES_POR_PAGINA = 11
MARGEN, IZQUIERDA, ANCHO = 52, 412, 1456
INICIO_FILAS, ALTO_FILA = 178, 75


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


def mostrar(addon, canales, programas, hora, ocultar, seleccionar, logos=None, grupos=None):
    import xbmcgui

    logos = logos or {}
    textura = str(Path(addon.getAddonInfo("path")) / "resources" / "skins" / "default" / "media" / "blanco.png")
    grupos = grupos or {}
    categorias = sorted(set(grupos.values()), key=lambda g: (g != "Generalistas", g.casefold()))
    if categorias and len(grupos) < len(canales) and "Otros canales" not in categorias:
        categorias.append("Otros canales")

    class Guia(xbmcgui.WindowXMLDialog):
        def onInit(self):
            self.inicio = int(hora) - (datetime.fromtimestamp(hora).minute % 30) * 60 - int(hora) % 60
            self.minimo, self.maximo = self.inicio - DURACION, self.inicio + 15 * DURACION
            self.pagina = 0
            self.categoria = ""
            self.canales_visibles = list(canales.items())
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

            def boton(x, y, ancho, alto, titulo, accion, argumentos, margen=12):
                control = agregar(xbmcgui.ControlButton(x, y, ancho, alto, titulo, font="font13",
                                                       textOffsetX=margen, alignment=4))
                self.acciones[control.getId()] = (accion, argumentos)
                return control

            def texto(x, y, ancho, alto, valor, color="FFF2F5FA", fuente="font13"):
                return agregar(xbmcgui.ControlLabel(x, y, ancho, alto, valor, font=fuente,
                                                   textColor=color, alignment=4))

            def linea(x, y, ancho, alto, color):
                agregar(xbmcgui.ControlImage(x, y, ancho, alto, textura, colorDiffuse=color))

            botones = [
                boton(255, 34, 185, 55, "◀  Horas", self.mover, (-1, 0)),
                boton(449, 34, 185, 55, "Horas  ▶", self.mover, (1, 0)),
                boton(675, 34, 205, 55, "▲  Canales", self.mover, (0, -1)),
                boton(889, 34, 205, 55, "Canales  ▼", self.mover, (0, 1)),
                boton(1135, 34, 225, 55, "Opciones de TV", self.abrir_opciones, ()),
            ]
            if categorias:
                botones.append(boton(1372, 34, 150, 55, "Grupos", self.elegir_grupo, ()))
            fecha = datetime.fromtimestamp(self.inicio).strftime("%d/%m/%Y")
            texto(1535, 36, 325, 52, fecha, fuente="font27")
            linea(MARGEN, 108, 1816, 2, "FF354258")
            texto(MARGEN, 120, 340, 48, self.categoria or "Canales", "FFB1C5DC")
            for h in range(6):
                x = IZQUIERDA + h * ANCHO // 6
                reloj = datetime.fromtimestamp(self.inicio + h * 1800).strftime("%H:%M")
                texto(x + 6, 120, 225, 48, reloj, "FFB1C5DC")
                linea(x, 168, 1, 835, "FF27364B")
            filas = [[(b.getX() + b.getWidth() // 2, b) for b in botones]]
            primer_programa = None
            recorte = self.canales_visibles[self.pagina:self.pagina + CANALES_POR_PAGINA]
            for indice, (cid, (nombre, enlace)) in enumerate(recorte):
                y = INICIO_FILAS + indice * ALTO_FILA
                numero = self.pagina + indice + 1
                margen = 122 if logos.get(cid) else 62
                max_nombre = 22 if logos.get(cid) else 27
                etiqueta = nombre if len(nombre) <= max_nombre else nombre[:max_nombre - 1] + "…"
                directo = boton(MARGEN, y, IZQUIERDA - MARGEN - 8, ALTO_FILA - 5, etiqueta,
                                self.programa, (nombre, enlace, self.inicio, self.inicio + DURACION, ""), margen)
                texto(MARGEN + 13, y, 42, ALTO_FILA - 5, str(numero), "FFD2E7FF")
                if logos.get(cid):
                    agregar(xbmcgui.ControlImage(MARGEN + 56, y + 12, 54, 46, logos[cid], aspectRatio=2))
                bloques = tramos(programas.get(cid, []), self.inicio) or [
                    (IZQUIERDA, ANCHO, self.inicio, self.inicio + DURACION, "")]
                controles = [(MARGEN + (IZQUIERDA - MARGEN) // 2, directo)]
                for x, ancho, inicio, fin, titulo in bloques:
                    if ancho < 11:
                        continue
                    if titulo and ocultar and fin <= hora:
                        titulo = "Programa anterior"
                    n = max(1, (ancho - 22) // 14)
                    visible = titulo if len(titulo) <= n else titulo[:n - 1] + "…"
                    control = boton(x + 2, y, ancho - 5, ALTO_FILA - 5, visible,
                                    self.programa, (nombre, enlace, inicio, fin, titulo))
                    if primer_programa is None and (not titulo or inicio <= hora < fin):
                        primer_programa = control
                    controles.append((x + ancho // 2, control))
                filas.append(controles)

            if recorte:
                texto(MARGEN, 1013, 900, 44, "%d–%d de %d canales" %
                      (self.pagina + 1, self.pagina + len(recorte), len(self.canales_visibles)), "FFB1C5DC")
            for i, fila in enumerate(filas):
                anterior, siguiente = filas[max(0, i - 1)], filas[min(i + 1, len(filas) - 1)]
                for j, (x, control) in enumerate(fila):
                    arriba = min(anterior, key=lambda item: abs(item[0] - x))[1]
                    abajo = min(siguiente, key=lambda item: abs(item[0] - x))[1]
                    control.setNavigation(arriba, abajo, fila[max(0, j - 1)][1],
                                          fila[min(j + 1, len(fila) - 1)][1])
            if self.inicio <= hora < self.inicio + DURACION:
                x = IZQUIERDA + int((hora - self.inicio) * ANCHO / DURACION)
                linea(x, 163, 3, 15 + ALTO_FILA * len(recorte), "B078C9FF")
            inicial = primer_programa or (filas[1][0][1] if recorte else botones[0])
            self.setFocus(inicial if self.foco is None else botones[self.foco])

        def mover(self, horas, canales_delta):
            self.foco = (1 if horas > 0 else 0) if horas else (3 if canales_delta > 0 else 2)
            if horas:
                self.inicio = max(self.minimo, min(self.maximo, self.inicio + horas * DURACION))
            if canales_delta:
                pagina = self.pagina + canales_delta * CANALES_POR_PAGINA
                if 0 <= pagina < len(self.canales_visibles):
                    self.pagina = pagina
            self.dibujar()

        def elegir_grupo(self):
            opciones = ["Todos los canales"] + categorias
            seleccion = xbmcgui.Dialog().select("Grupos de TV", opciones,
                                                  preselect=opciones.index(self.categoria) if self.categoria else 0)
            if seleccion < 0:
                return
            self.categoria = opciones[seleccion] if seleccion else ""
            self.pagina, self.foco = 0, None
            self.canales_visibles = [(cid, canal) for cid, canal in canales.items()
                                    if not self.categoria or grupos.get(cid, "Otros canales") == self.categoria]
            self.dibujar()

        def abrir_opciones(self):
            self.opciones = True
            self.close()

        def programa(self, *args):
            if seleccionar(*args):
                self.close()

        def onAction(self, accion):
            codigo = accion.getId()
            if codigo in (9, 10, 92):
                self.close()
            elif codigo in (5, 6):
                self.mover(0, 1 if codigo == 6 else -1)

        def onClick(self, control_id):
            if control_id in self.acciones:
                accion, argumentos = self.acciones[control_id]
                accion(*argumentos)

    ventana = Guia("palantix-guia.xml", addon.getAddonInfo("path"), "default", "1080i")
    ventana.foco = None
    ventana.opciones = False
    ventana.doModal()
    return ventana.opciones
