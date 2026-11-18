# Palantix

Addon de vídeo para Kodi (20 «Nexus» o superior): catálogo de películas y series de TMDB,
fuentes enchufables (listas propias JSON/M3U, Internet Archive) y servicios Debrid.

## Instalar en la tele (igual que Palantir 3)
1. Ajustes > Sistema > Complementos > activar **Orígenes desconocidos**.
2. Ajustes > Explorador de archivos > **Añadir fuente** > `https://USUARIO.github.io/palantix/` · nombre `palantix`.
3. Complementos > **Instalar desde un archivo zip** > `palantix` > `repository.palantix-1.0.0.zip`.
4. **Instalar desde repositorio** > Repositorio Palantix > Complementos de vídeo > **Palantix**.
5. Abre Palantix > Ajustes: pega tu clave gratuita de TMDB (themoviedb.org > Ajustes > API).

A partir de ahí las versiones nuevas llegan solas.

### Publicar una versión nueva
1. Sube el número de `version` en `plugin.video.palantix/addon.xml`.
2. `python tools/construir_repo.py https://USUARIO.github.io/palantix/`
3. Sube a GitHub (la carpeta `docs/` es la que sirve GitHub Pages: Settings > Pages > rama main, carpeta /docs).

## Qué tiene

**Catálogo**
- Películas: Tendencias, Populares, En cines, Mejor valoradas, Géneros, **Por año**, **Sagas**, Buscar.
- Series: Tendencias, Populares, Mejor valoradas, Géneros, Por año, Buscar → temporadas → capítulos.
- Orden configurable (populares, recientes, mejor valoradas, alfabético) y 20/40/60 elementos por pantalla.
- Búsquedas recientes recordadas.

**Seguir viendo**
- **Continuar viendo películas**: barra de progreso en la carátula; al abrir, «Reanudar desde…» o «Desde el principio».
- **Series en seguimiento**: se apuntan solas al ver un capítulo (85 %). Cada una abre su siguiente capítulo.
  Primero las que tienen capítulos **● NUEVOS** (salidos después de la última vez que la viste), luego las pendientes,
  y las que tienes al día (opcional) con la fecha del próximo capítulo.
- La piel pinta el número de capítulos pendientes en la carátula; los capítulos vistos llevan ✓.
- Aviso en la tele cuando sale un capítulo nuevo (al arrancar y cada 6 h).
- **Siguiente capítulo** automático con cuenta atrás al final (se puede cancelar).

**Fuentes e idioma**
- **Mis listas**: hasta 3 enlaces o ficheros JSON/M3U (formato abajo), con caché y por grupos.
- Etiquetas leídas del nombre: [CAST] [LAT] [VOSE] [DUAL] [4K] [1080p] [HDR] [CAM], con color a elegir.
- Orden por idioma preferido y calidad máxima; las CAM siempre al final; opción de ocultar otros idiomas.
- **Reproducción automática**: la mejor fuente sin preguntar y, si falla, la siguiente.

**Servicios Debrid** (Ajustes > Servicios Debrid)
- AllDebrid y Real-Debrid: se vinculan con un **código en pantalla** (lo metes desde el móvil).
- Premiumize: con la clave de la API de tu cuenta.
- Se prueban en orden: si uno falla, el siguiente. Magnets solo si ya están descargados en el servicio
  (si no, se quedan descargando en tu cuenta para más tarde).
- Aviso cuando a una cuenta le quedan 7 días o menos.

**Otros**: favoritas, tráiler (con el addon de YouTube), Internet Archive (cine de dominio público).

## Formato de una lista
JSON:
```json
{"nombre": "Mi lista", "peliculas": [
  {"titulo": "Nosferatu", "anio": 1922, "tmdb_id": 653, "url": "https://.../video.mp4",
   "calidad": "720p", "idioma": "CAST", "grupo": "Terror", "poster": "https://...", "sinopsis": "..."},
  {"serie": "Mi serie", "tmdb_id": 1399, "temporada": 1, "episodio": 2, "url": "https://..."}
]}
```
M3U:
```
#EXTM3U
#EXTINF:-1 tvg-logo="https://.../poster.jpg" group-title="Terror" tmdb-id="653",Nosferatu (1922)
https://.../video.mp4
#EXTINF:-1,Mi serie S01E02 Castellano
https://.../capitulo.mkv
```
Con `tmdb_id` el emparejamiento con el catálogo es exacto (en capítulos, el de la serie).
Sin él, por título (o título original) y año. Las URL pueden ser directas, de alojamientos o magnets
(estas dos últimas necesitan un servicio Debrid).

## Añadir otra fuente por código
Clase en `resources/lib/providers/` que herede de `Proveedor` (ver `base.py`), añadida a `PROVEEDORES`.

## Pruebas (sin Kodi)
- `python tools/prueba_local.py`: simula Kodi y recorre menús, listas, series, seguimiento, progreso y servicio.
- `python tools/prueba_debrid.py`: Real-Debrid, Premiumize y el orden entre servicios (+ API pública real).
- `python tools/prueba_alldebrid.py`: AllDebrid (con `ALLDEBRID_APIKEY=...` prueba tu cuenta real).
- `python tools/crear_logo.py`: regenera icon.png y fanart.jpg.
