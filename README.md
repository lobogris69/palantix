# Palantix

Addon de vídeo para Kodi (20 «Nexus» o superior): catálogo de películas y series de TMDB,
fuentes enchufables (listas propias JSON/M3U, Internet Archive) y servicios Debrid.

## Instalar en la tele (igual que Palantir 3)
1. Ajustes > Sistema > Complementos > activar **Orígenes desconocidos**.
2. Ajustes > Explorador de archivos > **Añadir fuente** > `https://lobogris69.github.io/palantix/` · nombre `palantix`.
3. Complementos > **Instalar desde un archivo zip** > `palantix` > `repository.palantix-1.0.0.zip`.
4. **Instalar desde repositorio** > Repositorio Palantix > Complementos de vídeo > **Palantix**.
5. Abre Palantix > Ajustes: pega tu clave gratuita de TMDB (themoviedb.org > Ajustes > API).

A partir de ahí las versiones nuevas llegan solas.

### Publicar una versión nueva
1. Sube el número de `version` en `plugin.video.palantix/addon.xml`.
2. `python tools/construir_repo.py https://lobogris69.github.io/palantix/`
3. Sube a GitHub (la carpeta `docs/` es la que sirve GitHub Pages: Settings > Pages > rama main, carpeta /docs).

## Qué tiene

**Catálogo**
- Películas: Tendencias, Populares, Novedades en streaming, Mejor valoradas, Géneros, **Por año**, **Sagas**, Buscar.
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

**Inicio, avisos y perfiles**
- En Ajustes → Catálogo puedes priorizar capítulos nuevos, ocultar las
  recomendaciones y elegir alto contraste o un inicio con menos imágenes.
- **Avísame cuando tenga fuente** usa las comprobaciones en segundo plano.
  Los títulos confirmados aparecen en el inicio. Los avisos se guardan en el
  perfil activo de Kodi.
- Si Kodi falla al iniciar una reproducción y quedan alternativas, Palantix
  ofrece abrir el selector de nuevo con el punto de reanudación guardado.
- **Comprobar mi configuración** permite guardar un informe limitado a estados
  de conexión y configuración. **Gestionar perfiles de casa** abre los perfiles
  de Kodi. La cuadrícula de TV requiere un cliente PVR configurado.

**Hoy para ti y reproducción**
- **Hoy para ti** reúne la reanudación, el seguimiento, las favoritas con fuente
  confirmada y la agenda deportiva. **Elegid algo para ver** recoge el género de
  cada persona y una duración máxima con el mando y muestra hasta tres coincidencias
  con fuente confirmada por el índice local.
- Si un enlace falla antes de comenzar el vídeo, la selección manual vuelve a las
  alternativas que ya encontró. El selector indica el formato cuando lo reconoce.
- **Dónde ver** está en el menú contextual de cada película o serie. Muestra datos
  regionales de JustWatch a través de TMDB y enlaza a la ficha de disponibilidad.
- En el menú contextual de una serie se pueden guardar preferencias de audio y
  subtítulos. Las descargas de subtítulos usan la cuenta de OpenSubtitles configurada.
- **Copiar preferencias a otro Kodi → Conectar móvil en la red local** ofrece un
  enlace temporal para exportar o enviar un archivo de preferencias sin credenciales.
  Si está disponible pyqrcode con soporte PNG, también se muestra el QR. Confirma
  cualquier importación en la tele.

**Deportes**
- La agenda agrupa **Hoy**, **Eventos en directo** y **Próximos eventos**. Una
  lista JSON de deportes también puede usar el campo raíz `eventos`. Cada
  entrada admite `inicio` y `fin` en ISO 8601, `canal` y
  `resultado_en_titulo` para ocultar títulos con marcador. Para un evento
  futuro se puede programar un aviso mientras Kodi esté abierto.
- **Guía TV** muestra qué emite cada canal ahora y a continuación con los horarios
  de [EPG dobleM](https://github.com/davidmuma/EPG_dobleM). Pulsa el canal para verlo en directo.
  Las horas se muestran en la zona horaria de Kodi y la programación se guarda durante cuatro horas.
- Si exportas canales a TV desde EKHorus, Palantix añade los que coincidan de
  forma inequívoca con un nombre de la guía.
- **Canales en directo** incluye Teledeporte, Esport3 y Top Barça. Real Madrid TV conserva su programación en la guía y se puede abrir si coincide con un canal exportado desde EKHorus.
  La disponibilidad de cada señal depende del canal y de la ubicación.
- En **Mis fuentes** puedes pegar un enlace Ace Stream, un código de 40 caracteres
  o la URL de una lista M3U o JSON. Las direcciones se guardan en el perfil de Kodi.
- **Mis fuentes** abre los ajustes del reproductor habilitado en Kodi (Horus o
  EKHorus). La reproducción P2P usa ese complemento y el motor Ace Stream del equipo.
- Con EKHorus habilitado, **Canales de EKHorus** abre los canales del propio
  complemento. Horus y EKHorus comparten identificador en Kodi.
- **Hoy** ordena los eventos de tus listas por hora local. En JSON se indica
  `inicio` en formato ISO 8601 (p. ej. `2026-11-19T20:00:00+01:00`) en cada
  entrada del formato mostrado más abajo. En M3U utiliza el atributo
  `inicio="2026-11-19T20:00:00+01:00"` en la línea `#EXTINF`.
  Los enlaces sin fecha quedan disponibles en su propia lista.
- Para consultar más señales y programación puedes usar
  [TDTChannels](https://www.tdtchannels.com/listas/) y
  [RTVE Play Deportes](https://www.rtve.es/play/videos/directo/deportes/).
  [Ace Stream Broadcast Search](https://search-ace.stream/) permite buscar códigos
  de emisiones. Su disponibilidad puede variar.

**Fuentes e idioma**
- **Mis listas**: hasta 3 enlaces o ficheros JSON/M3U (formato abajo), con caché y por grupos.
- Etiquetas leídas del nombre: [CAST] [LAT] [VOSE] [DUAL] [4K] [1080p] [HDR] [CAM], con color a elegir.
- Orden por idioma preferido y calidad máxima; las CAM siempre al final; opción de ocultar otros idiomas.
- **Reproducción automática**: la mejor fuente sin preguntar y, si falla, la siguiente.

**Servicios Debrid** (Ajustes > Servicios Debrid)
- AllDebrid y Real-Debrid: se vinculan con un **código en pantalla** (lo metes desde el móvil).
- Premiumize y TorBox: con la clave de la API de tu cuenta.
- Se prueban en orden: si uno falla, el siguiente. Magnets solo si ya están descargados en el servicio
  (si no, se quedan descargando en tu cuenta para más tarde).
- Aviso cuando a una cuenta le quedan 7 días o menos.

**Trakt** (Ajustes > Trakt)
- En Ajustes → Trakt, pulsa **Vincular con un código en pantalla** y autoriza tu cuenta. El Client ID incluido
  corresponde a la aplicación Development de Palantix, disponible para sus usuarios de prueba.
  Si usas tu propia aplicación, puedes indicar su Client ID en el mismo menú.
- Lo que ves se marca solo en tu Trakt (a partir del 80 %).
- Menú Trakt: películas y series pendientes y tus listas personales (también directamente en el menú principal).
- Al terminar te pregunta qué te ha parecido (nunca / a veces / siempre) y guarda la nota en Trakt.

**Subtítulos** (Ajustes > Subtítulos)
- Con una clave gratuita de OpenSubtitles (opensubtitles.com > API consumers): si el audio no está en tu idioma,
  se descarga y se pone solo el mejor subtítulo en español (los más descargados; las traducciones automáticas, al final).

**Saltar intro**
- Si el vídeo trae un capítulo «Intro»/«Opening», sale el botón «Saltar intro ▶▶».
- Y aprende de ti: la primera vez que adelantas la intro de una serie, la apunta; en los siguientes capítulos
  te ofrece el botón en ese momento (y afina la media cada vez).

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
- `python tools/prueba_extras.py`: subtítulos, Trakt y saltar intro (+ API reales con claves falsas).
- `python tools/crear_logo.py`: regenera icon.png y fanart.jpg.
