"""Texturas de la pantalla de inicio de Palantix (resources/skins/default/media).

python tools/crear_texturas.py
"""
import os

from PIL import Image, ImageDraw, ImageFilter

MEDIA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "plugin.video.palantix", "resources", "skins", "default", "media")
os.makedirs(MEDIA, exist_ok=True)


def guardar(im, nombre):
    im.save(os.path.join(MEDIA, nombre))
    print("creada", nombre, im.size)


# color plano (se tiñe con colordiffuse)
guardar(Image.new("RGBA", (8, 8), (255, 255, 255, 255)), "blanco.png")

# degradado lateral del cartel: negro opaco a la izquierda -> transparente a la derecha
w, h = 1920, 1080
im = Image.new("RGBA", (w, h))
dr = ImageDraw.Draw(im)
for x in range(w):
    resto = max(0.0, 1 - (x - 380) / 1000.0)  # sin bajar de 0 (una potencia de negativo da complejo)
    a = 255 if x < 380 else int(255 * resto ** 1.6)
    dr.line([(x, 0), (x, h)], fill=(11, 11, 16, a))
guardar(im, "degradado_izq.png")

# degradado inferior: transparente arriba -> fondo opaco abajo (las filas se leen sobre él)
w, h = 1920, 700
im = Image.new("RGBA", (w, h))
dr = ImageDraw.Draw(im)
for y in range(h):
    a = int(255 * min(1, (y / (h * 0.75))) ** 1.4)
    dr.line([(0, y), (w, y)], fill=(11, 11, 16, a))
guardar(im, "degradado_abajo.png")

# máscara de esquinas redondeadas para carátulas y miniaturas
for nombre, (w, h), r in (("mascara_poster.png", (400, 600), 22), ("mascara_ancha.png", (640, 360), 22)):
    X = 4
    m = Image.new("RGBA", (w * X, h * X), (0, 0, 0, 0))
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * X - 1, h * X - 1], radius=r * X, fill=(255, 255, 255, 255))
    guardar(m.resize((w, h), Image.LANCZOS), nombre)

# borde de selección (se estira con border=, se tiñe del color de Palantix)
X = 4
w, h, r, g = 120, 120, 26, 6
b = Image.new("RGBA", (w * X, h * X), (0, 0, 0, 0))
d = ImageDraw.Draw(b)
d.rounded_rectangle([0, 0, w * X - 1, h * X - 1], radius=r * X, fill=(255, 255, 255, 255))
d.rounded_rectangle([g * X, g * X, (w - g) * X - 1, (h - g) * X - 1], radius=(r - g) * X, fill=(0, 0, 0, 0))
guardar(b.resize((w, h), Image.LANCZOS), "borde.png")

# sombra suave bajo la carátula enfocada
s = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
ImageDraw.Draw(s).rounded_rectangle([30, 30, 130, 130], radius=20, fill=(0, 0, 0, 200))
guardar(s.filter(ImageFilter.GaussianBlur(14)), "sombra.png")

# píldora redondeada (etiquetas «NUEVO», botones)
X = 4
p = Image.new("RGBA", (120 * X, 40 * X), (0, 0, 0, 0))
ImageDraw.Draw(p).rounded_rectangle([0, 0, 120 * X - 1, 40 * X - 1], radius=20 * X, fill=(255, 255, 255, 255))
guardar(p.resize((120, 40), Image.LANCZOS), "pildora.png")
