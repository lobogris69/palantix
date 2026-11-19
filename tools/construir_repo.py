"""Construye el repositorio de Kodi de Palantix en la carpeta docs/, lista para GitHub Pages.

Uso:  python tools/construir_repo.py https://USUARIO.github.io/palantix/

Qué genera (lo mismo que usan los repositorios de addons conocidos):
  docs/index.html                           <- lo que ve Kodi al navegar la «fuente»
  docs/repository.palantix-1.0.0.zip        <- el zip que se instala a mano la primera vez
  docs/addons.xml + addons.xml.md5          <- el índice que Kodi consulta para instalar y ACTUALIZAR
  docs/plugin.video.palantix/plugin.video.palantix-X.Y.Z.zip (+ icon.png, fanart.jpg)
  docs/repository.palantix/repository.palantix-1.0.0.zip
  docs/.nojekyll                            <- GitHub Pages sirve los ficheros tal cual

En Kodi: Ajustes > Explorador de archivos > Añadir fuente > la URL de arriba, nombre «palantix».
Complementos > Instalar desde un archivo zip > palantix > repository.palantix-1.0.0.zip
Complementos > Instalar desde repositorio > Repositorio Palantix > Complementos de vídeo > Palantix.
Para publicar una versión nueva: sube el número en plugin.video.palantix/addon.xml, vuelve a
ejecutar este script y sube docs/ a GitHub. Las teles se actualizan solas.
"""
import hashlib
import html
import os
import re
import shutil
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "docs")
ADDON = os.path.join(RAIZ, "plugin.video.palantix")
IGNORAR = ("__pycache__", ".pyc", ".git")
GUARDAR = 6  # versiones anteriores que se mantienen en el repositorio


def version(carpeta):
    xml = open(os.path.join(carpeta, "addon.xml"), encoding="utf-8").read()
    return re.search(r'<addon[^>]*\bversion="([^"]+)"', xml).group(1), xml


def comprimir(carpeta, destino_dir):
    addon_id = os.path.basename(carpeta)
    ver, _ = version(carpeta)
    os.makedirs(destino_dir, exist_ok=True)
    ruta_zip = os.path.join(destino_dir, "%s-%s.zip" % (addon_id, ver))
    with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _dirs, ficheros in os.walk(carpeta):
            if any(i in base for i in IGNORAR):
                continue
            for f in ficheros:
                if f.endswith(IGNORAR):
                    continue
                completo = os.path.join(base, f)
                z.write(completo, os.path.join(addon_id, os.path.relpath(completo, carpeta)))
    for arte in ("icon.png", "fanart.jpg"):  # Kodi enseña el arte del repositorio antes de instalar
        if os.path.exists(os.path.join(carpeta, arte)):
            shutil.copy(os.path.join(carpeta, arte), destino_dir)
    return ruta_zip


def crear_addon_repositorio(url_base):
    carpeta = os.path.join(RAIZ, "build", "repository.palantix")
    shutil.rmtree(carpeta, ignore_errors=True)
    os.makedirs(carpeta)
    for arte in ("icon.png", "fanart.jpg"):
        if os.path.exists(os.path.join(ADDON, arte)):
            shutil.copy(os.path.join(ADDON, arte), carpeta)
    url_base = url_base.rstrip("/") + "/"
    with open(os.path.join(carpeta, "addon.xml"), "w", encoding="utf-8") as f:
        f.write("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="repository.palantix" name="Repositorio Palantix" version="1.0.0" provider-name="Palantix">
    <extension point="xbmc.addon.repository" name="Repositorio Palantix">
        <dir>
            <info compressed="false">{u}addons.xml</info>
            <checksum>{u}addons.xml.md5</checksum>
            <datadir zip="true">{u}</datadir>
        </dir>
    </extension>
    <extension point="xbmc.addon.metadata">
        <summary lang="es_ES">Repositorio del addon Palantix</summary>
        <description lang="es_ES">Instala Palantix y lo mantiene actualizado.</description>
        <platform>all</platform>
        <assets>
            <icon>icon.png</icon>
            <fanart>fanart.jpg</fanart>
        </assets>
    </extension>
</addon>
""".format(u=url_base))
    return carpeta


def indice(carpeta, titulo):
    """index.html con un enlace por fichero/carpeta: es lo que Kodi lee al navegar una fuente web."""
    entradas = sorted(e for e in os.listdir(carpeta) if not e.startswith(".") and e != "index.html")
    enlaces = "\n".join('<a href="%s%s">%s%s</a><br>' % (
        html.escape(e), "/" if os.path.isdir(os.path.join(carpeta, e)) else "", html.escape(e),
        "/" if os.path.isdir(os.path.join(carpeta, e)) else "") for e in entradas)
    with open(os.path.join(carpeta, "index.html"), "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\"><title>%s</title></head><body>\n"
                "<h1>%s</h1>\n%s\n</body></html>\n" % (titulo, titulo, enlaces))


def main():
    if len(sys.argv) < 2 or not sys.argv[1].startswith("http"):
        sys.exit(__doc__)
    # Se GUARDAN los zips de versiones anteriores: una tele que tenga apuntada una versión algo
    # antigua en su revisión diaria tiene que poder descargarla (si no, Kodi da «Update failed»).
    previos = os.path.join(SALIDA, "plugin.video.palantix")
    viejos = {}
    if os.path.isdir(previos):
        for f in os.listdir(previos):
            if f.endswith(".zip"):
                with open(os.path.join(previos, f), "rb") as z:
                    viejos[f] = z.read()
    shutil.rmtree(SALIDA, ignore_errors=True)
    os.makedirs(SALIDA)
    os.makedirs(previos)
    conservar = sorted(viejos, key=lambda n: [int(x) for x in re.findall(r"\d+", n)])[-GUARDAR:]
    for f in conservar:
        with open(os.path.join(previos, f), "wb") as z:
            z.write(viejos[f])
    carpetas = [ADDON, crear_addon_repositorio(sys.argv[1])]
    bloques = []
    for c in carpetas:
        addon_id = os.path.basename(c)
        print("Empaquetado:", comprimir(c, os.path.join(SALIDA, addon_id)))
        _, xml = version(c)
        bloques.append(re.sub(r"^<\?xml[^>]*\?>\s*", "", xml).strip())
    # el zip del repositorio también en la raíz: es el que se instala a mano la primera vez
    shutil.copy(comprimir(carpetas[1], os.path.join(SALIDA, "repository.palantix")), SALIDA)
    addons_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n%s\n</addons>\n' % "\n".join(bloques)
    # en binario: la huella se calcula sobre los MISMOS bytes que descargará Kodi (sin saltos de Windows)
    datos = addons_xml.encode("utf-8")
    with open(os.path.join(SALIDA, "addons.xml"), "wb") as f:
        f.write(datos)
    with open(os.path.join(SALIDA, "addons.xml.md5"), "wb") as f:
        f.write(hashlib.md5(datos).hexdigest().encode())
    open(os.path.join(SALIDA, ".nojekyll"), "w").close()
    for base, dirs, _ in os.walk(SALIDA):
        indice(base, "Palantix" if base == SALIDA else os.path.basename(base))
    print("Repositorio listo en", SALIDA)


if __name__ == "__main__":
    main()
