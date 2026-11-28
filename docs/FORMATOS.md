# Arca Media — Formatos admitidos

> Qué hace hoy la aplicación con cada formato, por biblioteca: si se cataloga, si tiene miniatura, si se leen sus metadatos y dónde se guardan los datos del usuario; y qué se ha probado con archivos reales. Sacado del código el 19/11/2026 y revisado con él el 21/11/2026, con las pruebas al día. Criterio: los formatos estándar y los de las cámaras y móviles de uso común; los demás, cuando hagan falta ([DECISIONES.md](DECISIONES.md), 21/11/2026).
> Índice: [INDEX.md](INDEX.md).

**Columnas**

- **Se cataloga**: si el archivo entra al añadir su carpeta. En una carpeta declarada («¿Qué contiene esta carpeta?»), solo entran los tipos de esa biblioteca ([MOD_CATALOGO.md](MOD_CATALOGO.md)).
- **Miniatura**: *Sí*, o *genérica* (el icono de su tipo; en los vídeos, con la duración). Lo que tiene miniatura se ve también en la vista individual y a 1:1.
- **Metadatos**: si se leen del archivo (fechas, cámara, medidas, GPS...).
- **Datos del usuario**: dónde se guardan, además de en el catálogo, la valoración, la marca, el color y las palabras clave (y, en Imagen, lo editado en el inspector): **XMP en el archivo**, un **`.xmp` al lado** (sidecar, como Lightroom con los RAW) o el **`.arca.json`** de la carpeta. Reglas: [core/userdata/LEEME.md](../core/userdata/LEEME.md).

## Imagen: fotos

| Formatos | Se cataloga | Miniatura | Metadatos | Datos del usuario |
|---|---|---|---|---|
| JPG, JPEG, JPE, JFIF, PNG, GIF, TIF, TIFF, WebP | Sí | Sí | Sí (ExifTool) | XMP en el archivo |
| BMP | Sí | Sí | Sí | `.arca.json` (el formato no admite XMP) |
| HEIC, HEIF, HIF (Canon, Fujifilm) | Sí | Sí (con `pillow-heif`) | Sí | XMP en el archivo |
| AVIF | Sí | Sí | Sí | XMP en el archivo |
| JP2 (JPEG 2000) | Sí | Sí | Sí | `.arca.json` |
| PSD | Sí | Sí, los de 8 bits guardados con «Maximizar compatibilidad»; los demás, genérica (el motivo, en `scan_errors`) | Sí | XMP en el archivo |
| PSB | Sí | Genérica | Sí | `.arca.json` |
| DNG | Sí | Sí (su vista previa interna) | Sí | XMP en el archivo |
| NEF, NRW, CR2, CR3, CRW, ARW, SRF, SR2, ORF, RW2, RAW, PEF, RAF, SRW, X3F, 3FR, FFF, IIQ, RWL, MRW, ERF, KDC, DCR, MOS | Sí | Sí (su vista previa interna; sin ninguna, genérica) | Sí | `.xmp` al lado |
| JXL (JPEG XL) | Solo si el sistema conoce la extensión † | Genérica | Sí | `.arca.json` |
| SVG, ICO | Sí | Genérica | ExifTool los lee (sin comprobar) | `.arca.json` |
| TGA, EXR, HDR, EPS, AI | No | — | — | — |

Las fotos con GPS salen en el mapa. El tamaño de la miniatura de un RAW es el de su vista previa ([MINIATURAS.md](MINIATURAS.md)).

## Vídeo

Los vídeos de cámara o de móvil van a Imagen; las películas y las series, a Vídeo; los dudosos quedan «Sin clasificar» ([MOD_CATALOGO.md](MOD_CATALOGO.md)). Se decide por la carpeta, por el nombre o por los metadatos: con marca o modelo de cámara, GPS o una fecha que solo escribe una cámara, Imagen ([FLUJOS.md](FLUJOS.md)). En los dos módulos se tratan igual. La fecha de captura sale de la etiqueta de hora local de cada marca (iPhone, Sony, videocámaras AVCHD, Nikon, AVI de compactas, XMP) o, si no hay ninguna, de la de QuickTime en UTC pasada a la hora local (`core/metadata/video/rules.py`).

| Formatos | Se cataloga | Miniatura | Metadatos | Datos del usuario |
|---|---|---|---|---|
| MP4, M4V, MOV, AVI, MKV, WMV, MPG, MPEG, WebM | Sí | Genérica, con la duración | Sí (ExifTool: fecha, duración, medidas, cámara, GPS) | `.arca.json` |
| 3GP | Sí, como vídeo en Windows ‡ | Genérica, con la duración | Sí | `.arca.json` |
| MTS, M2TS (videocámara) | Sí (van a Imagen) | Genérica, con la duración | Sí | `.arca.json` |
| FLV, VOB, TS, INSV y LRV (Insta360) | No (Windows toma `.ts` por TypeScript) | — | — | — |

Los vídeos con GPS salen en el mapa. El fotograma como miniatura, en `VID 4`.

## Música

| Formatos | Se cataloga | Miniatura | Metadatos | Datos del usuario |
|---|---|---|---|---|
| MP3, M4A, FLAC, OGG, OPUS, WAV, AIFF, AIF | Sí | La carátula incrustada (desde `MUS 3.1`); sin ella, la genérica; con la duración | Sí, con mutagen (`MUS 1.3`): etiquetas (ID3, Vorbis o MP4), datos técnicos y carátula | `.arca.json`; en el MP3, lo editado de sus etiquetas, en el propio archivo (`MUS 6.2b`); en FLAC, M4A y Ogg, con `MUS 6.3` y `6.4` |
| AAC (sin contenedor) | Sí | Genérica, con la duración | Solo los datos técnicos (mutagen no lee sus etiquetas) | `.arca.json` |
| MKA | Sí | Genérica | No (mutagen no lee Matroska: «sin soporte todavía») | `.arca.json` |
| WMA | Solo si el sistema conoce la extensión † | Genérica | Solo los datos técnicos (sus etiquetas ASF no se traducen) | `.arca.json` |
| APE, DSF, M4B (audiolibro) | No | — | — | — |

Desde `MUS 6.2b` (28/11/2026), el MP3 es un formato **partido** (destino `AUDIO_TAGS` de `core/userdata/policy.py`): lo editado de sus etiquetas (título, artista, comentario, álbum, artista del álbum, pista, disco, género y compositor) se escribe en el propio archivo, y la valoración, la marca, el color, las palabras clave y lo demás, en el `.arca.json`. FLAC, M4A y Ogg, todo en el `.arca.json` hasta `MUS 6.3` y `6.4`. Las carátulas, en `MUS 9`.

## Tracks

| Formatos | Se cataloga | Miniatura | Metadatos | Datos del usuario |
|---|---|---|---|---|
| GPX | Sí | El recorrido, dibujado | Sí (lector propio: distancia, desnivel, altitud, duración, velocidad, puntos, actividad, programa y waypoints) | `.arca.json`, también la actividad |
| KML, KMZ, TCX, FIT | No | — | — | — |

El GPX no se modifica nunca; su edición, sobre el propio archivo, es `TRK 6`.

## Libros

El módulo aún no existe: los libros se ven en el Catálogo ([MOD_EBOOKS.md](MOD_EBOOKS.md)).

| Formatos | Se cataloga | Miniatura | Metadatos | Datos del usuario |
|---|---|---|---|---|
| EPUB, MOBI, AZW3, FB2 | Sí, en la biblioteca Libros | Genérica | No (`EBK 2`) | `.arca.json` |
| AZW, PDF | No (`EBK 1.2`: los PDF, solo en carpetas declaradas de libros) | — | — | — |
| CBZ, CBR, DJVU | No (`EBK 11`) | — | — | — |

## Qué se escribe en los archivos

- **Valoración, marca, color y palabras clave**: de cualquier formato y en todos los módulos, en el destino de su fila.
- **Título, pie, creador, copyright, ubicación y GPS**: se editan en el inspector de Imagen (fotos y vídeos de Imagen); en el XMP o el `.xmp` de las fotos y en el `.arca.json` de los vídeos.
- **La actividad de un track**: en el `.arca.json`.
- **Nunca** se toca el contenido (los píxeles, el audio), ni se escribe hoy dentro de un vídeo, una canción, un GPX o un libro. Previsto: las etiquetas del audio (`MUS 6`), el GPX (`TRK 6.1`) y el EPUB (`EBK 7`).

## Notas

- † **Depende del sistema**: el detector mira primero su propia tabla de extensiones y después `mimetypes`, que en Windows lee el registro (los programas instalados registran extensiones). Lo que no está en ninguna de las dos solo entra si se reconoce por el contenido (`puremagic`). Todos los formatos de foto con miniatura o con datos en XMP están en la tabla propia o en la de Python: la autoprueba de `media_detector` lo comprueba.
- ‡ La tabla interna de Python da `.3gp` como audio; en Windows, el registro lo da como vídeo.

## Qué se ha probado con archivos reales

Al día el 21/11/2026 (los archivos de prueba, en «3 Fotos/Pruebas de formatos» del catálogo del autor; los RAW de otras marcas, de raw.pixls.us). **Leer**: se cataloga, con sus metadatos y su miniatura (y la vista individual y el 1:1). **Escribir**: los datos del usuario, comprobados con Lightroom («Leer metadatos del archivo») o en el `.arca.json`.

| Formato | Leer | Escribir | Notas |
|---|---|---|---|
| JPEG, HEIC | Sí | Sí | También en vertical: orientación EXIF y, en el HEIC, su `irot` |
| `.jfif` | Sí | Sí | Un JPEG con otra extensión: la que pone Windows a algunas imágenes descargadas con Chrome o Edge |
| PNG, WebP | Sí | Sí | Una captura de pantalla y una imagen de la web |
| GIF | Sí | Sí | Uno animado: la miniatura, del primer fotograma; la escritura, leída con ExifTool (Lightroom no abre los GIF) |
| TIFF | Sí | Sí | Con orientación 6 (Pillow 12 lo endereza al cargarlo: [TRAMPAS.md](TRAMPAS.md)) |
| AVIF | Sí | — | Con el giro solo en su `irot` |
| JPEG 2000 | Sí | Sí (`.arca.json`) | Sin el perfil de color: algo más apagado |
| PSD | Sí | — | Los de 8 bits con «Maximizar compatibilidad» |
| DNG | Sí | Sí | De una Nikon Df, iPhone (vertical), DJI y Ricoh; el tamaño, como Lightroom. El del DJI, con `-m` (su nota del fabricante está dañada: [TRAMPAS.md](TRAMPAS.md)) |
| NEF, CR3 | Sí | Sí (`.xmp` al lado) | Nikon Df (también en vertical) y Z6, Canon EOS R y M50. Las réflex Nikon no guardan el nombre del objetivo: se compone con sus números, como Lightroom («20.0 mm f/1.8»; versión 12) |
| PEF | Sí | Sí (`.xmp` al lado) | Una Pentax K-5 (y un JPEG de una K-70): el tamaño, el área útil, como Lightroom (versión 13). Sin objetivo: las Pentax solo guardan su código (Lightroom muestra el nombre, de su propia lista) |
| CR2, ARW, ORF, RW2, RAF | Sí | Sí (`.xmp` al lado) | El tamaño, el objetivo y la toma, comparados con Lightroom y con la lista de resultados del juego de RAW |
| CRW | Sí | Sí (`.xmp` al lado) | Una Canon EOS D60. Sin EXIF: la cámara, la toma y la fecha, de su propio formato (versión 12; antes salía sin ellas y con la fecha del archivo); el diafragma no se lee (basura cuando el objetivo no lo da) |
| NRW, SRF, SR2 | Sí | Sí (`.xmp` al lado) | El tamaño, el del sensor: entre un 0,5 % y un 3 % mayor que el de Lightroom (no traen el área útil) |
| Vídeo: MOV del iPhone | Sí | Sí (`.arca.json`) | Horizontal y vertical |
| Vídeo: MOV de una réflex Nikon (D3100) | Sí | Sí (`.arca.json`) | La hora, de su nota del fabricante (la de QuickTime es la local); el objetivo, con sus números, como en las fotos («18.0-55.0 mm f/3.5-5.6») |
| Vídeo: AVI de compactas (Canon, Ricoh) | Sí | Sí (`.arca.json`) | La fecha, de `RIFF:DateTimeOriginal`; van a Imagen por ella |
| Vídeo: película MKV | Sí, sin el códec (`VID 1.1`) | Sí (`.arca.json`) | Va a Vídeo; la fecha, la del archivo |
| GPX | Sí | Sí (`.arca.json`) | |
| Audio: MP3 (CBR y VBR), M4A (AAC LC), FLAC y Ogg Vorbis | Sí (las 75 canciones del autor, comparadas con Mp3tag el 25/11/2026) | Sí (`.arca.json`) | Los títulos, artistas, álbumes, años, pistas, géneros, duraciones y tasas de bits, como Mp3tag; en Ogg Vorbis, la tasa media (mutagen da la nominal: [TRAMPAS.md](TRAMPAS.md)). Sin probar: Opus, WAV, AIFF, ALAC |

**Falta**, por orden de utilidad:

- **Vídeos**: uno de Android y uno de cámara (GoPro, DJI, Sony o Canon sin espejo, una videocámara `.MTS`): sobre todo, si la fecha es la local o la UTC ([ESTADO.md](ESTADO.md), «Comprobaciones sueltas»). Una película MP4, con `VID 1.1`.
- **BMP**: la escritura en el `.arca.json` (como el JPEG 2000).
- Solo si aparece: un `.hif` (HEIF de Canon o Fujifilm). Los formatos poco comunes de las tablas (RAW antiguos o raros, PSB, SVG, ICO, JPEG XL...) no se buscan.

## Dónde se decide cada columna

Al cambiar uno de estos sitios, actualizar este documento.

| Columna | Dónde |
|---|---|
| Se cataloga | `core/catalog/media_detector.py` (`DEFAULT_EXTENSION_TO_TYPE`, `DEFAULT_EXTENSION_MIME`) y, la biblioteca, `core/catalog/libraries.py` |
| Miniatura | `core/thumbnails/registry.py` y sus orígenes en `core/thumbnails/sources/` |
| Metadatos | `core/metadata/registry.py` (un extractor por tipo de medio: foto, vídeo y track) |
| Datos del usuario | `core/userdata/policy.py` (`_EMBEDDED_EXTENSIONS`, `_SIDECAR_EXTENSIONS`; lo demás, `.arca.json`) |
