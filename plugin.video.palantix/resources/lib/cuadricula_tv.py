"""Guía dobleM por canal con ventanas de tres horas."""
from dataclasses import dataclass
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


def mas_cercano(fila, x):
    return min(fila, key=lambda item: abs(item[0] - x))[1]


@dataclass
class Fila:
    y: int
    numero: int
    numeracion: object
    controles: list
    navegables: list
    actual: object

    def colocar(self, y, numero):
        if self.y != y:
            for control, x, desplazamiento in self.controles:
                control.setPosition(x, y + desplazamiento)
            self.y = y
        if self.numero != numero:
            self.numeracion.setLabel(str(numero))
            self.numero = numero


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
            self.acciones, self.centros, self.vecinos = {}, {}, {}
            self.filas = {}
            self.x_foco = IZQUIERDA
            self.crear_cabecera()
            self.actualizar_horas()
            self.dibujar()

        def boton(self, x, y, ancho, titulo, accion, argumentos, margen=12, alto=ALTO_FILA - 5):
            control = xbmcgui.ControlButton(x, y, ancho, alto, titulo, font="font13",
                                            textOffsetX=margen, alignment=4)
            self.addControl(control)
            self.acciones[control.getId()] = (accion, argumentos)
            self.centros[control.getId()] = x + ancho // 2
            return control

        def texto(self, x, y, ancho, alto, valor="", color="FFF2F5FA", fuente="font13"):
            control = xbmcgui.ControlLabel(x, y, ancho, alto, valor, font=fuente, textColor=color, alignment=4)
            self.addControl(control)
            return control

        def linea(self, x, y, ancho, alto, color):
            control = xbmcgui.ControlImage(x, y, ancho, alto, textura, colorDiffuse=color)
            self.addControl(control)
            return control

        def crear_cabecera(self):
            self.botones = [
                self.boton(255, 34, 185, "◀  Horas", self.mover, (-1, 0), alto=55),
                self.boton(449, 34, 185, "Horas  ▶", self.mover, (1, 0), alto=55),
                self.boton(675, 34, 205, "▲  Canales", self.mover, (0, -1), alto=55),
                self.boton(889, 34, 205, "Canales  ▼", self.mover, (0, 1), alto=55),
                self.boton(1135, 34, 225, "Opciones de TV", self.abrir_opciones, (), alto=55),
            ]
            if categorias:
                self.botones.append(self.boton(1372, 34, 150, "Grupos", self.elegir_grupo, (), alto=55))
            self.fecha = self.texto(1535, 36, 325, 52, fuente="font27")
            self.linea(MARGEN, 108, 1816, 2, "FF354258")
            self.titulo_grupo = self.texto(MARGEN, 120, 340, 48, color="FFB1C5DC")
            self.relojes = []
            for h in range(6):
                x = IZQUIERDA + h * ANCHO // 6
                self.relojes.append(self.texto(x + 6, 120, 225, 48, color="FFB1C5DC"))
                self.linea(x, 168, 1, 835, "FF27364B")
            self.marca_cabecera = self.linea(IZQUIERDA, 163, 3, 15, "B078C9FF")
            self.contador = self.texto(MARGEN, 1013, 900, 44, color="FFB1C5DC")
            self.borde_superior = self.boton(1867, 168, 1, "", self.desplazar, (-1,), alto=1)
            self.borde_inferior = self.boton(1867, 1003, 1, "", self.desplazar, (1,), alto=1)
            self.bordes = {self.borde_superior.getId(): -1, self.borde_inferior.getId(): 1}
            self.titulo_grupo.setLabel("Canales")

        def actualizar_horas(self):
            self.fecha.setLabel(datetime.fromtimestamp(self.inicio).strftime("%d/%m/%Y"))
            for h, reloj in enumerate(self.relojes):
                reloj.setLabel(datetime.fromtimestamp(self.inicio + h * 1800).strftime("%H:%M"))
            presente = self.inicio <= hora < self.inicio + DURACION
            self.x_hora = IZQUIERDA + int((hora - self.inicio) * ANCHO / DURACION) if presente else None
            self.marca_cabecera.setVisible(presente)
            if presente:
                self.marca_cabecera.setPosition(self.x_hora, 163)

        def crear_fila(self, cid, canal, y, numero):
            nombre, enlace = canal
            logo = logos.get(cid)
            max_nombre = 22 if logo else 27
            etiqueta = nombre if len(nombre) <= max_nombre else nombre[:max_nombre - 1] + "…"
            directo = self.boton(MARGEN, y, IZQUIERDA - MARGEN - 8, etiqueta, self.programa,
                                 (nombre, enlace, self.inicio, self.inicio + DURACION, ""), 122 if logo else 62)
            numeracion = self.texto(MARGEN + 13, y, 42, ALTO_FILA - 5, str(numero), "FFD2E7FF")
            controles = [(directo, MARGEN, 0), (numeracion, MARGEN + 13, 0)]
            navegables = [(self.centros[directo.getId()], directo)]
            if logo:
                imagen = xbmcgui.ControlImage(MARGEN + 56, y + 12, 54, 46, logo, aspectRatio=2)
                self.addControl(imagen)
                controles.append((imagen, MARGEN + 56, 12))
            bloques = tramos(programas.get(cid, []), self.inicio) or [
                (IZQUIERDA, ANCHO, self.inicio, self.inicio + DURACION, "")]
            actual = None
            for x, ancho, inicio, fin, titulo in bloques:
                if ancho < 11:
                    continue
                if titulo and ocultar and fin <= hora:
                    titulo = "Programa anterior"
                n = max(1, (ancho - 22) // 14)
                visible = titulo if len(titulo) <= n else titulo[:n - 1] + "…"
                boton = self.boton(x + 2, y, ancho - 5, visible, self.programa, (nombre, enlace, inicio, fin, titulo))
                controles.append((boton, x + 2, 0))
                navegables.append((self.centros[boton.getId()], boton))
                if actual is None and (not titulo or inicio <= hora < fin):
                    actual = boton
            if self.x_hora is not None:
                marca = self.linea(self.x_hora, y, 3, ALTO_FILA, "B078C9FF")
                controles.append((marca, self.x_hora, 0))
            return Fila(y, numero, numeracion, controles, navegables, actual)

        def retirar_filas(self, canales_salientes):
            controles = []
            for cid in canales_salientes:
                fila = self.filas.pop(cid)
                for control, _, _ in fila.controles:
                    controles.append(control)
                    cid_control = control.getId()
                    self.acciones.pop(cid_control, None)
                    self.centros.pop(cid_control, None)
                    self.vecinos.pop(cid_control, None)
            if controles:
                self.removeControls(controles)

        def navegar(self, filas, borde_superior, borde_inferior):
            for i, fila in enumerate(filas):
                anterior, siguiente = filas[max(0, i - 1)], filas[min(i + 1, len(filas) - 1)]
                for j, (x, control) in enumerate(fila):
                    arriba = (borde_superior if i == 1 else None) or mas_cercano(anterior, x)
                    abajo = (borde_inferior if i == len(filas) - 1 else None) or mas_cercano(siguiente, x)
                    izquierda = self.botones[-1] if i and j == 0 else fila[max(0, j - 1)][1]
                    vecinos = (arriba, abajo, izquierda, fila[min(j + 1, len(fila) - 1)][1])
                    if self.vecinos.get(control.getId()) != vecinos:
                        control.setNavigation(*vecinos)
                        self.vecinos[control.getId()] = vecinos

        def dibujar(self, ancla=None, boton_cabecera=None):
            recorte = self.canales_visibles[self.pagina:self.pagina + CANALES_POR_PAGINA]
            # En vertical solo salen y entran los canales de los bordes. Los demás conservan sus controles.
            self.retirar_filas(self.filas.keys() - {cid for cid, _ in recorte})
            cabecera = [(self.centros[b.getId()], b) for b in self.botones]
            filas = [cabecera]
            actual = None
            for i, (cid, canal) in enumerate(recorte):
                y, numero = INICIO_FILAS + i * ALTO_FILA, self.pagina + i + 1
                fila = self.filas.get(cid)
                if fila is None:
                    fila = self.filas[cid] = self.crear_fila(cid, canal, y, numero)
                else:
                    fila.colocar(y, numero)
                filas.append(fila.navegables)
                actual = actual or fila.actual

            quedan = self.pagina + len(recorte) < len(self.canales_visibles)
            self.navegar(filas, self.borde_superior if self.pagina else None, self.borde_inferior if quedan else None)
            self.contador.setLabel("%d–%d de %d canales" %
                                  (self.pagina + 1, self.pagina + len(recorte), len(self.canales_visibles))
                                  if recorte else "")
            if boton_cabecera is not None:
                destino = self.botones[boton_cabecera]
            elif ancla is not None:
                fila, x = ancla
                destino = mas_cercano(filas[fila], x)
            else:
                destino = actual or filas[1 if recorte else 0][0][1]
            self.x_foco = self.centros[destino.getId()]
            self.setFocus(destino)

        def desplazar(self, delta):
            maximo = max(0, len(self.canales_visibles) - CANALES_POR_PAGINA)
            pagina = min(maximo, max(0, self.pagina + delta))
            if pagina == self.pagina:
                return
            self.pagina = pagina
            self.dibujar(ancla=(-1 if delta > 0 else 1, self.x_foco))

        def mover(self, horas, canales_delta):
            cabecera = (1 if horas > 0 else 0) if horas else (3 if canales_delta > 0 else 2)
            if horas:
                inicio = max(self.minimo, min(self.maximo, self.inicio + horas * DURACION))
                if inicio != self.inicio:
                    self.inicio = inicio
                    self.actualizar_horas()
                    self.retirar_filas(list(self.filas))
            if canales_delta:
                maximo = max(0, len(self.canales_visibles) - CANALES_POR_PAGINA)
                self.pagina = min(maximo, max(0, self.pagina + canales_delta * CANALES_POR_PAGINA))
            self.dibujar(boton_cabecera=cabecera)

        def elegir_grupo(self):
            opciones = ["Todos los canales"] + categorias
            seleccion = xbmcgui.Dialog().select("Grupos de TV", opciones,
                                                  preselect=opciones.index(self.categoria) if self.categoria else 0)
            if seleccion < 0:
                return
            self.categoria = opciones[seleccion] if seleccion else ""
            self.pagina = 0
            self.titulo_grupo.setLabel(self.categoria or "Canales")
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
            elif codigo in (104, 105, 111, 112):
                self.desplazar(1 if codigo in (105, 112) else -1)

        def onFocus(self, control_id):
            if control_id in self.bordes:
                self.desplazar(self.bordes[control_id])
            elif control_id in self.centros:
                self.x_foco = self.centros[control_id]

        def onClick(self, control_id):
            if control_id in self.acciones:
                accion, argumentos = self.acciones[control_id]
                accion(*argumentos)

    ventana = Guia("palantix-guia.xml", addon.getAddonInfo("path"), "default", "1080i")
    ventana.opciones = False
    ventana.doModal()
    return ventana.opciones
