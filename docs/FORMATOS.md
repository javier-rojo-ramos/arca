# Arca Media — Formatos admitidos

> Qué hace hoy la aplicación con cada formato, por biblioteca: si se cataloga, si tiene miniatura, si se leen sus metadatos y dónde se guardan los datos del usuario. Sacado del código el 19/11/2026.
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

Los vídeos de cámara o de móvil van a Imagen; las películas y las series, a Vídeo; los dudosos quedan «Sin clasificar» ([MOD_CATALOGO.md](MOD_CATALOGO.md)). En los dos módulos se tratan igual.

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
| MP3, M4A, AAC, FLAC, OGG, OPUS, WAV, AIFF, AIF, MKA | Sí | Genérica, sin duración | **No** (`MUS 1`) | `.arca.json` |
| WMA | Solo si el sistema conoce la extensión † | Genérica | No | `.arca.json` |
| APE, DSF, M4B (audiolibro) | No | — | — | — |

Las etiquetas del propio archivo (ID3...) no se escriben hasta `MUS 6`; las carátulas, en `MUS 3` y `MUS 9`.

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
- **Probados con archivos reales**: JPEG, HEIC, DNG, NEF (su sidecar), PSD, los vídeos del iPhone y los GPX. Los demás RAW, WebP, AVIF y JPEG 2000 no se han probado con archivos de verdad ([ESTADO.md](ESTADO.md), «Nunca probado»).

## Dónde se decide cada columna

Al cambiar uno de estos sitios, actualizar este documento.

| Columna | Dónde |
|---|---|
| Se cataloga | `core/catalog/media_detector.py` (`DEFAULT_EXTENSION_TO_TYPE`, `DEFAULT_EXTENSION_MIME`) y, la biblioteca, `core/catalog/libraries.py` |
| Miniatura | `core/thumbnails/registry.py` y sus orígenes en `core/thumbnails/sources/` |
| Metadatos | `core/metadata/registry.py` (un extractor por tipo de medio: foto, vídeo y track) |
| Datos del usuario | `core/userdata/policy.py` (`_EMBEDDED_EXTENSIONS`, `_SIDECAR_EXTENSIONS`; lo demás, `.arca.json`) |
