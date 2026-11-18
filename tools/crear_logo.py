"""Genera icon.png (512x512) y fanart.jpg (1920x1080) del addon Palantix con Pillow.

Idea del logo: una «P» cuyo bucle es un ojo/orbe (guiño al palantír, la piedra que ve lejos)
con un botón de «play» dentro, en degradado cian -> violeta sobre fondo azul noche.
Uso: python tools/crear_logo.py
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugin.video.palantix")
X = 4  # dibujamos a 4x y reducimos: bordes suaves

FONDO_A, FONDO_B = (10, 14, 38), (30, 20, 70)
CIAN, VIOLETA = (0, 214, 255), (170, 70, 255)
FUENTES = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def degradado(tam, a, b, diagonal=True):
    w, h = tam
    base = Image.new("RGB", (w, h), a)
    capa = Image.new("RGB", (w, h), b)
    if diagonal:
        # se gira un degradado mayor y se recorta el centro: sin bordes de relleno al girar
        lado = int((w * w + h * h) ** 0.5) + 2
        grande = Image.linear_gradient("L").resize((lado, lado)).rotate(-35, resample=Image.BICUBIC)
        x0, y0 = (lado - w) // 2, (lado - h) // 2
        mascara = grande.crop((x0, y0, x0 + w, y0 + h))
    else:
        mascara = Image.linear_gradient("L").resize((w, h))
    return Image.composite(capa, base, mascara)


def fuente(tam):
    for f in FUENTES:
        if os.path.exists(f):
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default()


def simbolo(lado):
    """La P-play sobre fondo transparente, de lado x lado píxeles."""
    s = lado
    capa = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    m = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(m)
    grosor = s * 0.15
    # palo de la P
    d.rounded_rectangle([s * 0.22, s * 0.14, s * 0.22 + grosor, s * 0.86], radius=s * 0.05, fill=255)
    # bucle de la P: forma de «D» con el borde de arriba recto, pegada al palo (una sola pieza)
    caja = [s * 0.22, s * 0.14, s * 0.80, s * 0.64]
    d.rounded_rectangle(caja, radius=(caja[3] - caja[1]) * 0.49, fill=255, corners=(False, True, True, False))
    hueco = [caja[0] + grosor, caja[1] + grosor, caja[2] - grosor, caja[3] - grosor]
    d.ellipse([hueco[0] - s * 0.03, hueco[1], hueco[2], hueco[3]], fill=0)  # el «orbe» interior
    color = degradado((s, s), CIAN, VIOLETA)
    capa.paste(color, (0, 0), m)
    # «play» blanco dentro del orbe
    cx, cy = (hueco[0] + hueco[2]) / 2 + s * 0.01, (hueco[1] + hueco[3]) / 2
    r = s * 0.085
    ImageDraw.Draw(capa).polygon([(cx - r * 0.8, cy - r), (cx - r * 0.8, cy + r), (cx + r, cy)],
                                 fill=(255, 255, 255, 240))
    return capa


def icono():
    t = 512 * X
    img = degradado((t, t), FONDO_A, FONDO_B).convert("RGBA")
    # halo suave detrás del símbolo
    halo = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse([t * 0.18, t * 0.18, t * 0.82, t * 0.82], fill=(90, 120, 255, 70))
    img = Image.alpha_composite(img, halo.filter(ImageFilter.GaussianBlur(t * 0.08)))
    sim = simbolo(int(t * 0.86))
    img.alpha_composite(sim, (int(t * 0.07), int(t * 0.03)))
    # nombre debajo
    d = ImageDraw.Draw(img)
    f = fuente(int(t * 0.13))
    w = d.textlength("PALANTIX", font=f)
    d.text(((t - w) / 2, t * 0.80), "PALANTIX", font=f, fill=(235, 240, 255))
    # esquinas redondeadas
    mascara = Image.new("L", (t, t), 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, t, t], radius=t * 0.18, fill=255)
    img.putalpha(mascara)
    img = img.resize((512, 512), Image.LANCZOS)
    img.save(os.path.join(RAIZ, "icon.png"))


def fanart():
    w, h = 1920 * 2, 1080 * 2
    img = degradado((w, h), FONDO_A, FONDO_B).convert("RGBA")
    halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse([w * 0.05, h * 0.10, w * 0.50, h * 0.90], fill=(80, 100, 255, 60))
    img = Image.alpha_composite(img, halo.filter(ImageFilter.GaussianBlur(h * 0.12)))
    sim = simbolo(int(h * 0.62))
    img.alpha_composite(sim, (int(w * 0.10), int(h * 0.19)))
    d = ImageDraw.Draw(img)
    # el texto se ajusta solo para no salirse por la derecha
    tam = int(h * 0.20)
    while d.textlength("PALANTIX", font=fuente(tam)) > w * 0.50:
        tam -= 4
    d.text((w * 0.43, h * 0.36), "PALANTIX", font=fuente(tam), fill=(240, 244, 255))
    d.text((w * 0.435, h * 0.36 + tam * 1.15), "Películas y series en tu tele", font=fuente(int(h * 0.05)),
           fill=(150, 200, 255))
    img.convert("RGB").resize((1920, 1080), Image.LANCZOS).save(os.path.join(RAIZ, "fanart.jpg"), quality=90)


if __name__ == "__main__":
    icono()
    fanart()
    print("Logo creado en", RAIZ)
