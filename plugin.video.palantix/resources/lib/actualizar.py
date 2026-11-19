"""Consulta la versión publicada y solicita a Kodi refrescar sus repositorios."""
import re
import urllib.request

REPO = "https://lobogris69.github.io/palantix/addons.xml"
ID = "plugin.video.palantix"
ID_REPOSITORIO = "repository.palantix"


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
    """Solicita una búsqueda en Kodi y devuelve si el repositorio está habilitado."""
    import xbmc
    if not xbmc.getCondVisibility("System.AddonIsEnabled(%s)" % ID_REPOSITORIO):
        return False
    xbmc.executebuiltin("UpdateAddonRepos")
    log("[Palantix] pedido a Kodi que refresque los repositorios")
    return True
