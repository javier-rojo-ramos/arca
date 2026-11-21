# Arca Media — Índice de la documentación

Catalogador de archivos multimedia (tipo DAM) de escritorio y multiplataforma (Windows, macOS, Linux), inspirado en Lightroom, FastStone, Mp3tag y VisualDivX. Gestiona colecciones de **imágenes** (en curso), **vídeo, audio y ebooks** (previstos). Python 3.14 + PySide6 (vía `qtpy`), SQLite y ExifTool. Uso interno de la empresa; se empaquetará con PyInstaller (pendiente: [PENDIENTE.md](PENDIENTE.md), `GEN 5`).

**¿En qué punto está el proyecto?** → [ESTADO.md](ESTADO.md) (qué está hecho, qué falta por verificar y los últimos cambios).
**¿Qué viene después?** → [PENDIENTE.md](PENDIENTE.md).
**Reglas de trabajo** (para personas y para la IA) → [CLAUDE.md](../CLAUDE.md).

## Documentos

| Documento | Qué contiene | Cuándo leerlo |
|---|---|---|
| [ESTADO.md](ESTADO.md) | Lo verificado, lo entregado pendiente de verificar, lo nunca probado y los últimos cambios | Siempre, al empezar |
| [PENDIENTE.md](PENDIENTE.md) | Hoja de ruta por categorías (GENERAL y una por módulo: CATÁLOGO, IMAGEN, MÚSICA, VÍDEO, EBOOKS y TRACKS), en fases y pasos (`TRK 6.3`); al final, la equivalencia con la numeración anterior (A, B, C) | Al decidir el siguiente paso |
| [ARQUITECTURA.md](ARQUITECTURA.md) | Principios, componentes, reglas de arquitectura, **mapa del proyecto (qué hace cada archivo)** y qué corre en cada hilo | Para orientarse o encontrar dónde está algo |
| [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md) | Convenciones de los datos, tablas, bloques de columnas (quién escribe cada una), migraciones | Al tocar la base de datos o una consulta |
| [FLUJOS.md](FLUJOS.md) | Paso a paso de cada operación: arranque, catálogo, añadir carpeta, metadatos, miniaturas, cuadrícula, datos del usuario, opciones, barra lateral, cierre, módulos, inspector, eliminar, barra inferior, barra de filtros | Al cambiar el comportamiento de una operación |
| [METADATOS.md](METADATOS.md) | Mapa de campos (qué se extrae y dónde se ve), campos de imagen, vídeo y tracks, prioridad entre etiquetas, equivalencias con Lightroom | Al añadir o corregir un campo |
| [MINIATURAS.md](MINIATURAS.md) | Tamaños, reglas, orígenes por formato, caché | Al tocar las miniaturas |
| [FORMATOS.md](FORMATOS.md) | Los formatos admitidos, por biblioteca: si se catalogan, si tienen miniatura, si se leen sus metadatos y dónde se guardan los datos del usuario | Al preguntar si se admite un formato o al añadir uno |
| [MOD_TRACKS.md](MOD_TRACKS.md) | **Módulo Tracks y componente de mapa** (antes `MAPA.md`; `MapView` lo usan también el Catálogo e Imagen): arquitectura (tecnología, API, capas, elevación, datos, correlación foto-track, edición de GPX; qué hay hecho y dónde) y plan en fases (`TRK`). Hechas las fases 0 a 5; pendientes, la 6, la 7 y la 8 | Al tocar el mapa o seguir con el módulo Tracks |
| [MOD_CATALOGO.md](MOD_CATALOGO.md) | **Módulo Catálogo** y lo que es del catálogo entero: qué es un catálogo, añadir y sincronizar carpetas, bibliotecas, ausentes, colecciones, eliminar; dónde está cada cosa y lo que falta (`CAT 1`, `CAT 2` y lo de otras categorías que le afecta). Escrito a posteriori, desde el código | Para orientarse en el Catálogo |
| [MOD_IMAGEN.md](MOD_IMAGEN.md) | **Módulo Imagen** (fotos y vídeos personales): cómo funciona hoy (barra, vistas, inspector, filtros, datos, lo que se guarda en los archivos, miniaturas), dónde está cada cosa y lo que falta (`IMG 1` a `IMG 3` y lo de otras categorías que le afecta). Escrito a posteriori, desde el código | Para orientarse en el módulo Imagen |
| [MOD_MUSICA.md](MOD_MUSICA.md) | **Módulo Música** (Audio): arquitectura prevista (mutagen, `audio_details`, tabla campo ↔ etiqueta, escritura en los archivos, carátulas) y plan en fases `MUS 1` a `MUS 10`. Diseño acordado el 16/11/2026; sin implementar | Antes de cada paso del módulo Música |
| [MOD_VIDEO.md](MOD_VIDEO.md) | **Módulo Vídeo** (películas, series, documentales...): arquitectura prevista (fichas por obra, una tarjeta por obra, géneros y personas, descarga de la web, visto / no visto) y plan en fases `VID 1` a `VID 10`. Diseño acordado el 16/11/2026; sin implementar | Antes de cada paso del módulo Vídeo |
| [MOD_EBOOKS.md](MOD_EBOOKS.md) | **Módulo Ebooks** (Libros): lo básico de los formatos (EPUB, PDF, Kindle) y arquitectura prevista (lectura, portadas, escritura en EPUB, convivencia con Calibre); plan en fases `EBK 1` a `EBK 11`. Diseño acordado el 16/11/2026 como punto de partida; sin implementar | Antes de cada paso del módulo Ebooks |
| [COMO_AMPLIAR.md](COMO_AMPLIAR.md) | La tabla «Quiero... → toco...» | Antes de añadir algo nuevo |
| [PRUEBAS.md](PRUEBAS.md) | Autopruebas, ventanas que se abren solas, diagnóstico con ExifTool | Para comprobar un cambio |
| [DECISIONES.md](DECISIONES.md) | Por qué las cosas son como son (con fecha) | Antes de cambiar algo que parece raro |
| [TRAMPAS.md](TRAMPAS.md) | Comportamientos que sorprenden y errores fáciles de cometer | Antes de tocar un área delicada |
| [HISTORIAL.md](HISTORIAL.md) | Registro de cambios y detalle de cómo se probó cada entrega | Solo si hace falta el detalle de algo pasado |

**Un documento `MOD_` por módulo de la aplicación** (acordado el 16/11/2026): `MOD_<MÓDULO>.md` describe, por un lado, la arquitectura del módulo y, por otro, su planificación (fases y pasos, con los códigos de [PENDIENTE.md](PENDIENTE.md)). Existen los cinco: `MOD_CATALOGO.md`, `MOD_IMAGEN.md`, `MOD_MUSICA.md`, `MOD_VIDEO.md` y `MOD_TRACKS.md`, y `MOD_EBOOKS.md` (su módulo aún no existe).

Documentación por carpeta del código (detalle y recetas): [core/metadata/LEEME.md](../core/metadata/LEEME.md) · [core/thumbnails/LEEME.md](../core/thumbnails/LEEME.md) · [core/userdata/LEEME.md](../core/userdata/LEEME.md). Cada archivo `.py` explica en su cabecera qué hace y cómo se usa, y cada función, en su docstring.

## Versiones actuales

Al cambiar una de estas versiones, actualizar esta tabla.

| | |
|---|---|
| Aplicación | Arca Media 26.11.001 (`config/app_paths.py`: `APP_NAME` «arca», `APP_NAME_COMERCIAL` y `APP_VERSION`) |
| Esquema de la base de datos | v6: la v1, consolidada el 05/11/2026, la migración 2 (`metadata_edit_pending`, 10/11/2026), la 3 (`gps_direction` en `media_items`, 11/11/2026), la 4 (`track_details.overview`, contorno de los tracks, 13/11/2026) la 5 (`file_operations`, registro de las operaciones con archivos, 19/11/2026) y la 6 (`folders`, las carpetas del catálogo, 19/11/2026) (`PRAGMA user_version` = número de migraciones de `core/catalog/catalog_schema.py`; los catálogos llevan la marca `APPLICATION_ID` en `PRAGMA application_id`) |
| Lista de campos de imagen | versión 14 (`IMAGE_FIELDS_VERSION`; incluye la lectura de los datos del usuario y de las palabras clave; GPS con el XMP primero; el tamaño de HEIC, HEIF y AVIF girado con su `irot`; el área útil de los RAW de Nikon, Olympus y Pentax; el objetivo sin códigos numéricos y, en las réflex Nikon, con sus números; los CRW, sin EXIF; la marca de la cámara, con su nombre corto) |
| Lista de campos de vídeo | versión 6 (`VIDEO_FIELDS_VERSION`; la marca de la cámara, con su nombre corto; con el objetivo, sin códigos numéricos y, en las réflex Nikon, con sus números; la hora local de las Nikon y de los AVI de compactas; comprobada con vídeos de iPhone, una Nikon D3100 y compactas Canon y Ricoh) |
| Lector de GPX | versión 5 (`TRACK_EXTRACTOR_VERSION`; umbral de desnivel 8 m; con el contorno simplificado del recorrido, como mucho 1 000 puntos; la actividad, como clave de la lista) |
| Motor de miniaturas | versión 2 (`THUMBNAIL_VERSION`) |
| Reglas de las colecciones inteligentes | versión 2 (`collections.rules_json`; con grupos de un nivel; se sigue leyendo la 1); 40 campos en `core/catalog/smart_fields.py` (23 Estándar, 11 Imagen, 6 Tracks GPS; grupos Vídeo, Audio y Ebooks aún vacíos); 29 también como columnas de «Metadatos» (`browse`) |

## Al retomar el proyecto

- **Con Claude Code (VS Code)**: `CLAUDE.md` se lee solo al empezar. Basta con decir qué se quiere hacer.
- **En un chat de claude.ai**: adjuntar el REPOMIX (incluye `CLAUDE.md` y `docs/`) y pedir que lea `CLAUDE.md` y este índice. Si el código y la documentación no coinciden, **manda el código**: hay que corregir la documentación.
- Las salidas de `python -m core.metadata.inspect_cli archivo --json salida.json` de los archivos con los que se esté trabajando ahorran muchas dudas (cuidado: incluyen coordenadas GPS y rutas).
