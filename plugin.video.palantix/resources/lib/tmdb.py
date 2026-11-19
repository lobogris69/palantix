"""Catálogo: The Movie Database (TMDB). Solo metadatos (títulos, carátulas, sinopsis), nunca vídeo."""
from .http import get_json

API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/"


# Orden de los listados (Ajustes > Catálogo): clave -> (sort_by películas, sort_by series, filtros extra)
ORDENES = {
    "popularidad": ("popularity.desc", "popularity.desc", {}),
    "estreno": ("primary_release_date.desc", "first_air_date.desc", {"vote_count.gte": 20}),
    "valoracion": ("vote_average.desc", "vote_average.desc", {"vote_count.gte": 300}),
    "titulo": ("title.asc", "name.asc", {"vote_count.gte": 20}),
}

# Sagas conocidas para el menú (se buscan en TMDB por nombre al abrir el menú)
SAGAS = ["Harry Potter", "El Señor de los Anillos", "Star Wars", "Marvel Los Vengadores", "Misión: Imposible",
         "Fast & Furious", "James Bond", "Jurassic Park", "Piratas del Caribe", "Indiana Jones", "Toy Story",
         "Regreso al futuro", "El Padrino", "Matrix", "John Wick", "Shrek", "Los juegos del hambre",
         "Terminator", "Alien", "Rocky", "Mad Max", "Ocean's", "Torrente", "Ice Age", "Minions"]


# Idiomas del catálogo (Ajustes > General): (nombre, idioma TMDB, región)
IDIOMAS = [("Español (España)", "es-ES", "ES"), ("Español (Latinoamérica)", "es-MX", "MX"), ("English", "en-US", "US"),
           ("Français", "fr-FR", "FR"), ("Italiano", "it-IT", "IT"), ("Português", "pt-PT", "PT"), ("Deutsch", "de-DE", "DE")]


def idioma_de(indice):
    try:
        _, idioma, region = IDIOMAS[int(indice)]
    except (ValueError, IndexError, TypeError):
        _, idioma, region = IDIOMAS[0]
    return idioma, region


def es_token(clave):
    return clave.startswith("eyJ") and clave.count(".") == 2


def limpiar_clave(texto):
    """Quita espacios, saltos y comillas que se cuelan al pegar o teclear la clave."""
    return "".join(texto.split()).strip("\"'")


def validar(clave):
    """True si TMDB acepta la clave, False si la rechaza, None si no se pudo comprobar (sin Internet)."""
    import urllib.error
    try:
        TMDB(clave)._get("/configuration")
        return True
    except urllib.error.HTTPError as e:
        return False if e.code in (401, 403) else None
    except Exception:
        return None


class TMDB:
    def __init__(self, api_key, idioma="es-ES", region="ES", orden="popularidad"):
        self.key = api_key
        self.idioma = idioma
        self.region = region
        self.orden = orden if orden in ORDENES else "popularidad"

    def _descubrir(self, tipo, page, **filtros):
        peli, serie, extra = ORDENES[self.orden]
        filtros.update(extra)
        filtros["sort_by"] = peli if tipo == "movie" else serie
        if tipo == "movie" and self.orden == "estreno":  # sin futuros estrenos sin fecha real
            import time as _t
            filtros["primary_release_date.lte"] = _t.strftime("%Y-%m-%d")
        return self._get("/discover/%s" % tipo, page=page, **filtros)

    def _get(self, ruta, **params):
        params.setdefault("language", self.idioma)
        cab = None
        if es_token(self.key):  # «Token de acceso de lectura» (v4): va en la cabecera
            cab = {"Authorization": "Bearer " + self.key}
        else:                   # «Clave de la API» (v3): va en la dirección
            params["api_key"] = self.key
        return get_json(API + ruta, params, cabeceras=cab)

    # --- Listados -------------------------------------------------------
    def tendencias(self, page=1):
        return self._get("/trending/movie/week", page=page)

    def populares(self, page=1):
        return self._get("/movie/popular", page=page, region=self.region)

    def mejor_valoradas(self, page=1):
        return self._get("/movie/top_rated", page=page, region=self.region)

    def en_cines(self, page=1):
        return self._get("/movie/now_playing", page=page, region=self.region)

    def generos(self):
        return self._get("/genre/movie/list").get("genres", [])

    def por_genero(self, genero_id, page=1):
        return self._descubrir("movie", page, with_genres=genero_id)

    def por_anio(self, anio, page=1):
        return self._descubrir("movie", page, primary_release_year=anio)

    def buscar_saga(self, texto, page=1):
        return self._get("/search/collection", query=texto, page=page)

    def saga(self, coleccion_id):
        """Películas de una saga en orden de estreno."""
        c = self._get("/collection/%s" % coleccion_id)
        partes = sorted(c.get("parts", []), key=lambda m: m.get("release_date") or "9999")
        return {"page": 1, "total_pages": 1, "results": partes, "name": c.get("name", "")}

    def buscar(self, texto, page=1):
        return self._get("/search/movie", query=texto, page=page)

    def detalle(self, tmdb_id):
        return self._get("/movie/%s" % tmdb_id)

    # --- Series ---------------------------------------------------------
    def s_tendencias(self, page=1):
        return self._get("/trending/tv/week", page=page)

    def s_populares(self, page=1):
        return self._get("/tv/popular", page=page)

    def s_mejor_valoradas(self, page=1):
        return self._get("/tv/top_rated", page=page)

    def s_generos(self):
        return self._get("/genre/tv/list").get("genres", [])

    def s_por_genero(self, genero_id, page=1):
        return self._descubrir("tv", page, with_genres=genero_id)

    def s_por_anio(self, anio, page=1):
        return self._descubrir("tv", page, first_air_date_year=anio)

    def s_buscar(self, texto, page=1):
        return self._get("/search/tv", query=texto, page=page)

    def serie(self, tmdb_id):
        return self._get("/tv/%s" % tmdb_id)

    def temporada(self, tmdb_id, numero):
        return self._get("/tv/%s/season/%s" % (tmdb_id, numero))

    def trailer_youtube(self, tmdb_id, tipo="movie"):
        """Clave de YouTube del tráiler: primero en el idioma del catálogo, si no en inglés."""
        for idioma in (self.idioma, "en-US"):
            videos = self._get("/%s/%s/videos" % (tipo, tmdb_id), language=idioma).get("results", [])
            for v in videos:
                if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser"):
                    return v["key"]
        return None

    def siguiente(self, tmdb_id, temporada, episodio, hoy=None):
        """Capítulo que va después de SxE (salta a la temporada siguiente). None si no hay o no se ha emitido."""
        import time as _t
        hoy = hoy or _t.strftime("%Y-%m-%d")
        for s, desde in ((temporada, episodio), (temporada + 1, 0)):
            try:
                eps = self.temporada(tmdb_id, s).get("episodes", [])
            except Exception:
                return None
            for ep in sorted(eps, key=lambda x: x["episode_number"]):
                if ep["episode_number"] > desde:
                    if not ep.get("air_date") or ep["air_date"] > hoy:
                        return None
                    return {"temporada": s, "episodio": ep["episode_number"], "nombre": ep.get("name") or ""}
        return None

    # --- Utilidades -----------------------------------------------------
    @staticmethod
    def imagen(ruta, tam="w500"):
        return IMG + tam + ruta if ruta else ""
