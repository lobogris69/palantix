"""Historial local de títulos terminados, con una valoración por título."""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
import time

from . import ganchos, novedades, progreso, seguimiento

TIPOS = {"pelicula": "Películas", "serie": "Series"}
OPCIONES = ["%s  %d/5" % ("★" * n, n) for n in range(5, 0, -1)]


@contextmanager
def _abrir(perfil):
    ruta = Path(perfil) / "historial-vistos.sqlite"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(ruta))) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("""CREATE TABLE IF NOT EXISTS vistos (
            tipo TEXT, tmdb INTEGER, titulo TEXT, original TEXT, anio TEXT,
            poster TEXT, fanart TEXT, fecha INTEGER, nota INTEGER,
            PRIMARY KEY (tipo, tmdb)
        )""")
        yield db


def registrar(perfil, meta, fecha=None, nota=None):
    tipo = meta["tipo"]
    tmdb = int(meta["tmdb"])
    if tipo not in TIPOS or tmdb <= 0 or (nota is not None and nota not in range(1, 6)):
        raise ValueError("Título o valoración no válidos")
    campos = [str(meta.get(k) or "") for k in ("titulo", "original", "anio", "poster", "fanart")]
    with _abrir(perfil) as db:
        db.execute("""INSERT INTO vistos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tipo, tmdb) DO UPDATE SET
                titulo=coalesce(nullif(excluded.titulo, ''), vistos.titulo),
                original=coalesce(nullif(excluded.original, ''), vistos.original),
                anio=coalesce(nullif(excluded.anio, ''), vistos.anio),
                poster=coalesce(nullif(excluded.poster, ''), vistos.poster),
                fanart=coalesce(nullif(excluded.fanart, ''), vistos.fanart),
                fecha=max(vistos.fecha, excluded.fecha),
                nota=coalesce(excluded.nota, vistos.nota)""",
                   (tipo, tmdb, *campos, int(time.time() if fecha is None else fecha), nota))
        return db.execute("SELECT nota FROM vistos WHERE tipo=? AND tmdb=?", (tipo, tmdb)).fetchone()["nota"]


def leer(perfil, tipo):
    if tipo not in TIPOS:
        return []
    with _abrir(perfil) as db:
        return [dict(fila) for fila in db.execute(
            "SELECT * FROM vistos WHERE tipo=? ORDER BY fecha DESC, titulo COLLATE NOCASE", (tipo,))]


def importar_series(perfil, seguidas, estados):
    """Recupera las series completas ya detectadas por el seguimiento anterior."""
    guardadas = {str(fila["tmdb"]) for fila in leer(perfil, "serie")}
    for sid, datos in seguidas.items():
        estado = estados.get(sid) or {}
        if (sid not in guardadas and novedades.estado_vista(estado) == "terminada"
                and (estado.get("revision") or [])[:6] == novedades.revision_local(datos)):
            registrar(perfil, dict(datos, tmdb=sid, tipo="serie"), fecha=datos.get("fecha") or 0)


def preguntar(titulo):
    import xbmcgui
    elegida = xbmcgui.Dialog().select("Valora «%s»" % (titulo or "Título"), OPCIONES, autoclose=30000)
    return 5 - elegida if 0 <= elegida < len(OPCIONES) else None


def serie_completa(t, sid, vistos, ficha=None):
    ficha = t.serie(sid) if ficha is None else ficha
    if (ficha.get("status") not in ("Ended", "Canceled")
            or ficha.get("in_production") or ficha.get("next_episode_to_air")):
        return False
    estado = novedades.estado(t, sid, 0, 0, vistos.get("fecha"), vistos, serie=ficha, detalle=False)
    return novedades.estado_vista(estado) == "terminada"


@ganchos.registrar
class Historial:
    def __init__(self, perfil=None, ajustes=None, cliente=None, vistos_trakt=None, valorar=None):
        if perfil is None or ajustes is None:
            import xbmcaddon
            import xbmcvfs
            addon = xbmcaddon.Addon()
            perfil = perfil if perfil is not None else xbmcvfs.translatePath(addon.getAddonInfo("profile"))
            ajustes = ajustes if ajustes is not None else addon.getSetting
        self.perfil, self.ajustes = perfil, ajustes
        self.cliente = cliente if cliente is not None else self._cliente
        self.vistos_trakt = vistos_trakt if vistos_trakt is not None else self._vistos_trakt
        self.valorar = valorar if valorar is not None else preguntar
        self.fraccion = 0.0

    def _cliente(self):
        from . import tmdb
        clave = tmdb.limpiar_clave(self.ajustes("tmdb_key"))
        idioma, region = tmdb.idioma_de(self.ajustes("idioma_cat") or 0)
        return tmdb.TMDB(clave, idioma, region) if clave else None

    def _vistos_trakt(self, sid):
        from .trakt import Trakt
        from types import SimpleNamespace
        import xbmcaddon
        addon = xbmcaddon.Addon()
        cliente = Trakt(SimpleNamespace(get=self.ajustes, set=addon.setSetting), timeout=5)
        return cliente.historial_episodios(Path(self.perfil) / "cache").get(str(sid))

    def al_empezar(self, meta, reproductor):
        self.fraccion = 0.0

    def al_avanzar(self, meta, reproductor, actual, total):
        if total > 0:
            self.fraccion = max(self.fraccion, actual / total)

    def al_parar(self, meta, reproductor, terminado):
        if not meta.get("tmdb"):
            return
        tipo = meta.get("tipo")
        if tipo == "pelicula":
            if not terminado and self.fraccion < progreso.TERMINADO:
                return
        elif tipo == "episodio" and (terminado or self.fraccion >= seguimiento.umbral_visto(self.ajustes)):
            t = self.cliente()
            if not t:
                return
            sid = meta["tmdb"]
            ficha = t.serie(sid)
            if ficha.get("status") not in ("Ended", "Canceled") or ficha.get("next_episode_to_air"):
                return
            vistos = seguimiento.con_historial_trakt(
                seguimiento.leer(self.perfil).get(str(sid)) or {}, self.vistos_trakt(sid))
            if not serie_completa(t, sid, vistos, ficha):
                return
            tipo = "serie"
        else:
            return
        ficha = dict(meta, tipo=tipo)
        nota = registrar(self.perfil, ficha)
        if self.ajustes("valorar_al_terminar") != "false":
            meta["valoracion_titulo"] = True
            if nota is None:
                meta["valoracion_pendiente"] = ficha

    def al_valorar(self, meta, reproductor):
        ficha = meta.pop("valoracion_pendiente", None)
        if ficha is not None:
            nota = self.valorar(ficha.get("titulo"))
            if nota is not None:
                registrar(self.perfil, ficha, fecha=0, nota=nota)
