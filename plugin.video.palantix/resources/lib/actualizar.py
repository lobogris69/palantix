"""Actualizaciones fáciles: Palantix mira en su repositorio si hay versión nueva y pide a Kodi que la instale.

Kodi solo refresca los repositorios una vez al día; con UpdateAddonRepos lo hace al momento y,
como las actualizaciones automáticas de Kodi vienen activadas, la versión nueva se instala sola.
"""
import re
import urllib.request

REPO = "https://lobogris69.github.io/palantix/addons.xml"
ID = "plugin.video.palantix"


def a_tupla(version):
    return tuple(int(x) for x in re.findall(r"\d+", version or "0"))


def version_remota(url=REPO, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Palantix", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        texto = r.read().decode("utf-8", "replace")
    m = re.search(r'<addon[^>]*id="%s"[^>]*version="([^"]+)"' % re.escape(ID), texto) or \
        re.search(r'<addon[^>]*version="([^"]+)"[^>]*id="%s"' % re.escape(ID), texto)
    return m.group(1) if m else None


def hay_nueva(local, remota):
    return bool(remota) and a_tupla(remota) > a_tupla(local)


def pedir_a_kodi(log=print):
    """Refresca los repositorios ya (y Kodi instala la actualización si tiene las automáticas activadas)."""
    import xbmc
    xbmc.executebuiltin("UpdateAddonRepos")
    xbmc.executebuiltin("UpdateLocalAddons")
    log("[Palantix] pedido a Kodi que busque actualizaciones")
