"""Genera resources/skins/default/1080i/palantix-inicio.xml: la pantalla de inicio estilo plataforma.

Estructura (1920x1080):
  - Fondo: arte del elemento enfocado, con degradados para leer el texto.
  - Cartel (arriba-izquierda): título, año · nota · duración, etiqueta NUEVO, sinopsis.
  - Filas de carátulas (abajo): cada una es una lista horizontal dentro de un grupo vertical.
  - Menú lateral con iconos (se despliega con nombres al enfocarlo).
python tools/crear_inicio_xml.py
"""
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "plugin.video.palantix", "resources", "skins", "default", "1080i", "palantix-inicio.xml")

ACENTO = "FF14A9FF"      # azul Palantix
FONDO = "FF0B0B10"
TEXTO2 = "FFB8BCC8"

# (id, forma): «ancha» = miniatura 16:9 con barra de progreso; «poster» = carátula 2:3
FILAS = [(100, "ancha"), (101, "ancha"), (102, "ancha"), (103, "poster"), (104, "poster"), (105, "poster"),
         (106, "poster"), (107, "poster"), (108, "poster"), (109, "poster"), (110, "poster"), (111, "poster")]
MENU = 200
TAM = {"poster": (196, 294), "ancha": (352, 198)}


def capa_item(forma, enfocado, fid=0):
    w, h = TAM[forma]
    mascara = "mascara_poster.png" if forma == "poster" else "mascara_ancha.png"
    arte = "$INFO[ListItem.Art(poster)]" if forma == "poster" else "$INFO[ListItem.Art(thumb)]"
    activo = "Control.HasFocus(%d)" % fid
    zoom = ('<animation effect="zoom" start="100" end="108" center="%d,%d" time="180" tween="cubic" easing="out" '
            'reversible="true" condition="%s">Conditional</animation>' % (w // 2 + 10, h // 2 + 18, activo)) if enfocado else ""
    borde = ('<control type="image"><left>2</left><top>10</top><width>%d</width><height>%d</height>'
             '<texture border="26" colordiffuse="%s">borde.png</texture><visible>%s</visible>'
             '<animation effect="fade" start="0" end="100" time="150">Visible</animation></control>'
             % (w + 16, h + 16, ACENTO, activo)) if enfocado else ""
    sombra = ('<control type="image"><left>-20</left><top>-10</top><width>%d</width><height>%d</height>'
              '<texture border="40">sombra.png</texture><visible>%s</visible></control>' % (w + 56, h + 60, activo)) if enfocado else ""
    progreso = ""
    titulo = ""
    if forma == "ancha":
        progreso = ('<control type="progress"><left>26</left><top>%d</top><width>%d</width><height>6</height>'
                    '<info>ListItem.PercentPlayed</info><texturebg colordiffuse="66FFFFFF">blanco.png</texturebg>'
                    '<midtexture colordiffuse="%s">blanco.png</midtexture>'
                    '<visible>Integer.IsGreater(ListItem.PercentPlayed,0)</visible></control>' % (h - 4, w - 32, ACENTO))
        titulo = ('<control type="label"><left>10</left><top>%d</top><width>%d</width><height>40</height>'
                  '<font>font12</font><textcolor>%s</textcolor><label>$INFO[ListItem.Label2]</label></control>'
                  % (h + 26, w, "FFFFFFFF" if enfocado else TEXTO2))
        if enfocado:  # el título blanco solo en la fila activa
            titulo = titulo.replace("<label>", "<label>").replace(
                "</control>", "<textcolor>FFFFFFFF</textcolor></control>", 0)
    nuevo = ('<control type="group"><left>%d</left><top>20</top><visible>String.IsEqual(ListItem.Property(nuevo),1)</visible>'
             '<control type="image"><width>110</width><height>34</height><texture colordiffuse="FF1DB954">pildora.png</texture></control>'
             '<control type="label"><width>110</width><height>34</height><align>center</align><aligny>center</aligny>'
             '<font>font10</font><textcolor>FFFFFFFF</textcolor><label>[B]NUEVO[/B]</label></control></control>' % (w - 104))
    seguida = ('<control type="group"><left>15</left><top>20</top><visible>!String.IsEmpty(ListItem.Property(seguida))</visible>'
               '<control type="image"><width>165</width><height>34</height><texture colordiffuse="FF2764A3">pildora.png</texture></control>'
               '<control type="label"><width>165</width><height>34</height><align>center</align><aligny>center</aligny>'
               '<font>font10</font><textcolor>FFFFFFFF</textcolor><label>[B]$INFO[ListItem.Property(seguida)][/B]</label></control></control>')
    a_medias = ('<control type="group"><left>15</left><top>20</top><visible>String.IsEqual(ListItem.Property(a_medias),1)</visible>'
                '<control type="image"><width>114</width><height>34</height><texture colordiffuse="FF2764A3">pildora.png</texture></control>'
                '<control type="label"><width>114</width><height>34</height><align>center</align><aligny>center</aligny>'
                '<font>font10</font><textcolor>FFFFFFFF</textcolor><label>[B]A MEDIAS[/B]</label></control></control>')
    return ('<control type="group">%s%s'
            '<control type="image"><left>10</left><top>18</top><width>%d</width><height>%d</height>'
            '<texture colordiffuse="FF22242E">blanco.png</texture><visible>String.IsEmpty(%s)</visible></control>'
            '<control type="label"><left>20</left><top>28</top><width>%d</width><height>%d</height><align>center</align>'
            '<aligny>center</aligny><font>font13</font><textcolor>FFFFFFFF</textcolor><wrapmultiline>true</wrapmultiline>'
            '<label>$INFO[ListItem.Label]</label><visible>String.IsEmpty(%s)</visible></control>'
            '<control type="image"><left>10</left><top>18</top><width>%d</width><height>%d</height>'
            '<texture diffuse="%s" background="true">%s</texture><aspectratio>scale</aspectratio></control>'
            '%s%s%s%s%s%s</control>' % (zoom, sombra, w, h, arte.replace("$INFO[", "").rstrip("]"),
                                    w - 20, h - 20, arte.replace("$INFO[", "").rstrip("]"),
                                    w, h, mascara, arte, borde, progreso, nuevo, seguida, a_medias, titulo))


def fila(fid, forma, siguiente, anterior):
    w, h = TAM[forma]
    alto_item = h + (80 if forma == "ancha" else 40)
    return '''
            <control type="label" id="%(lab)d">
                <width>1600</width><height>54</height><font>font27</font><textcolor>FFFFFFFF</textcolor>
                <label>[B]$INFO[Window.Property(fila%(id)d)][/B]</label>
                <visible>Integer.IsGreater(Container(%(id)d).NumItems,0)</visible>
            </control>
            <control type="list" id="%(id)d">
                <width>1520</width><height>%(alto)d</height>
                <orientation>horizontal</orientation>
                <onleft>%(menu)d</onleft>
                <scrolltime tween="cubic" easing="out">260</scrolltime>
                <visible>Integer.IsGreater(Container(%(id)d).NumItems,0)</visible>
                <itemlayout width="%(iw)d" height="%(alto)d">%(normal)s</itemlayout>
                <focusedlayout width="%(iw)d" height="%(alto)d">%(foco)s</focusedlayout>
            </control>''' % {"lab": fid + 500, "id": fid, "alto": alto_item, "menu": MENU, "iw": w + 22,
                             "normal": capa_item(forma, False, fid), "foco": capa_item(forma, True, fid)}


def cartel(fid):
    c = "Container(%d).ListItem" % fid
    return '''
        <control type="group">
            <visible>Control.HasFocus(%(id)d)</visible>
            <animation effect="fade" start="0" end="100" time="300">Visible</animation>
            <control type="image">
                <left>420</left><top>0</top><width>1500</width><height>844</height>
                <texture background="true">$INFO[%(c)s.Art(fanart)]</texture><aspectratio>scale</aspectratio>
                <fadetime>400</fadetime>
            </control>
            <control type="image"><width>1920</width><height>1080</height><texture>degradado_izq.png</texture></control>
            <control type="image"><top>380</top><width>1920</width><height>700</height><texture>degradado_abajo.png</texture></control>
            <control type="grouplist">
                <left>400</left><top>150</top><width>1100</width><height>400</height>
                <orientation>vertical</orientation><itemgap>4</itemgap><usecontrolcoords>true</usecontrolcoords>
                <control type="label">
                    <width>1100</width><height>90</height>
                    <font>font52_title</font><textcolor>FFFFFFFF</textcolor><scroll>true</scroll>
                    <label>[B]$INFO[%(c)s.Label][/B]</label>
                </control>
                <control type="label">
                    <width>1100</width><height>40</height>
                    <font>font13</font><textcolor>%(acento)s</textcolor>
                    <label>[B]$INFO[%(c)s.Property(destacado)][/B]</label>
                    <visible>!String.IsEmpty(%(c)s.Property(destacado))</visible>
                </control>
                <control type="label">
                    <width>1100</width><height>46</height>
                    <font>font14</font><textcolor>%(t2)s</textcolor>
                    <label>$INFO[%(c)s.Property(info)]</label>
                </control>
                <control type="textbox">
                    <width>820</width><height>152</height>
                    <font>font13</font><textcolor>FFE4E6EE</textcolor>
                    <autoscroll delay="7000" time="4000" repeat="9000">true</autoscroll>
                    <label>$INFO[%(c)s.Plot]</label>
                </control>
            </control>
        </control>''' % {"id": fid, "c": c, "acento": ACENTO, "t2": TEXTO2}


def xml():
    filas = "".join(fila(fid, forma, None, None) for fid, forma in FILAS)
    carteles = "".join(cartel(fid) for fid, _ in FILAS)
    return '''<?xml version="1.0" encoding="UTF-8"?>
<!-- Pantalla de inicio de Palantix. Generada con tools/crear_inicio_xml.py: no editar a mano. -->
<window>
    <defaultcontrol always="true">9000</defaultcontrol>
    <backgroundcolor>%(fondo)s</backgroundcolor>
    <animation effect="fade" start="0" end="100" time="350">WindowOpen</animation>
    <animation effect="fade" start="100" end="0" time="250">WindowClose</animation>
    <controls>
        <control type="image"><width>1920</width><height>1080</height><texture colordiffuse="%(fondo)s">blanco.png</texture></control>
        <!-- cartel por defecto (con el menú enfocado o mientras carga) -->
        <control type="group">
            <visible>%(ninguna)s</visible>
            <control type="image"><left>420</left><width>1500</width><height>844</height><texture>$INFO[Window.Property(fondo_palantix)]</texture><aspectratio>scale</aspectratio></control>
            <control type="image"><width>1920</width><height>1080</height><texture>degradado_izq.png</texture></control>
            <control type="image"><top>380</top><width>1920</width><height>700</height><texture>degradado_abajo.png</texture></control>
        </control>
        %(carteles)s
        <!-- logo -->
        <control type="image"><left>400</left><top>52</top><width>64</width><height>64</height><texture>$INFO[Window.Property(logo)]</texture></control>
        <control type="label"><left>480</left><top>58</top><width>500</width><height>54</height><font>font32_title</font><textcolor>FFFFFFFF</textcolor><label>[B]PALANTIX[/B]</label></control>
        <control type="label"><left>720</left><top>64</top><width>600</width><height>46</height><font>font27</font><textcolor>%(acento)s</textcolor><label>$INFO[Window.Property(pestana),|   ,]</label></control>
        <control type="label"><left>482</left><top>104</top><width>400</width><height>28</height><font>font10</font><textcolor>80FFFFFF</textcolor><label>$INFO[Window.Property(version),versión ,]</label></control>
        <control type="label"><left>1400</left><top>58</top><width>460</width><height>54</height><align>right</align><font>font_clock</font><textcolor>FFFFFFFF</textcolor><label>$INFO[System.Time]</label></control>
        <!-- mensaje mientras carga -->
        <control type="label"><left>400</left><top>620</top><width>1460</width><height>60</height><font>font27</font><textcolor>%(t2)s</textcolor>
            <label>$INFO[Window.Property(estado)]</label><visible>!String.IsEmpty(Window.Property(estado))</visible></control>
        <!-- filas -->
        <control type="grouplist" id="9000">
            <left>400</left><top>560</top><width>1520</width><height>520</height>
            <orientation>vertical</orientation><itemgap>6</itemgap>
            <scrolltime tween="cubic" easing="out">320</scrolltime>
            <onleft>%(menu)d</onleft>
            %(filas)s
        </control>
        <!-- menú lateral fijo -->
        <control type="group">
            <control type="image"><width>365</width><height>1080</height><texture colordiffuse="FF131722">blanco.png</texture></control>
            <control type="list" id="%(menu)d">
                <left>0</left><top>103</top><width>365</width><height>952</height>
                <onright>9000</onright><orientation>vertical</orientation>
                <itemlayout width="365" height="68">
                    <control type="image"><left>12</left><top>5</top><width>340</width><height>58</height><texture colordiffuse="FF1C2A40" border="20">pildora.png</texture>
                        <visible>String.IsEqual(ListItem.Property(activa),1)</visible></control>
                    <control type="image"><left>28</left><top>16</top><width>36</width><height>36</height><texture>$INFO[ListItem.Icon]</texture></control>
                    <control type="label"><left>80</left><top>0</top><width>274</width><height>68</height><aligny>center</aligny><font>font27</font><textcolor>FFF1F4FA</textcolor>
                        <label>$INFO[ListItem.Label]</label></control>
                </itemlayout>
                <focusedlayout width="365" height="68">
                    <control type="image"><left>12</left><top>5</top><width>340</width><height>58</height><texture colordiffuse="FF1C2A40" border="20">pildora.png</texture>
                        <visible>!Control.HasFocus(%(menu)d) + String.IsEqual(ListItem.Property(activa),1)</visible></control>
                    <control type="image"><left>12</left><top>5</top><width>340</width><height>58</height><texture colordiffuse="FF254469" border="20">pildora.png</texture>
                        <visible>Control.HasFocus(%(menu)d)</visible></control>
                    <control type="image"><left>12</left><top>17</top><width>4</width><height>34</height><texture colordiffuse="%(acento)s">blanco.png</texture>
                        <visible>Control.HasFocus(%(menu)d)</visible></control>
                    <control type="image"><left>28</left><top>16</top><width>36</width><height>36</height><texture>$INFO[ListItem.Icon]</texture></control>
                    <control type="label"><left>80</left><top>0</top><width>268</width><height>68</height><aligny>center</aligny><font>font27</font><textcolor>FFF1F4FA</textcolor>
                        <label>$INFO[ListItem.Label]</label><visible>!Control.HasFocus(%(menu)d)</visible></control>
                    <control type="label"><left>80</left><top>0</top><width>268</width><height>68</height><aligny>center</aligny><font>font27</font><textcolor>FFFFFFFF</textcolor>
                        <label>[B]$INFO[ListItem.Label][/B]</label><visible>Control.HasFocus(%(menu)d)</visible></control>
                </focusedlayout>
            </control>
        </control>
    </controls>
</window>
''' % {"fondo": FONDO, "carteles": carteles, "filas": filas, "menu": MENU, "acento": ACENTO, "t2": TEXTO2,
       "ninguna": " + ".join("!Control.HasFocus(%d)" % fid for fid, _ in FILAS)}


if __name__ == "__main__":
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as f:
        f.write(xml())
    import xml.dom.minidom
    xml.dom.minidom.parse(SALIDA)
    print("generado y válido:", SALIDA)
