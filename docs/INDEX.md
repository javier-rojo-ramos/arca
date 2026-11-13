# Arca Media — Índice de la documentación

Catalogador de archivos multimedia (tipo DAM) de escritorio y multiplataforma (Windows, macOS, Linux), inspirado en Lightroom, FastStone, Mp3tag y VisualDivX. Gestiona colecciones de **imágenes** (en curso), **vídeo, audio y ebooks** (previstos). Python 3.14 + PySide6 (vía `qtpy`), SQLite y ExifTool. Uso interno de la empresa; se empaquetará con PyInstaller (pendiente: [PENDIENTE.md](PENDIENTE.md), C.9).

**¿En qué punto está el proyecto?** → [ESTADO.md](ESTADO.md) (qué está hecho, qué falta por verificar y los últimos cambios).
**¿Qué viene después?** → [PENDIENTE.md](PENDIENTE.md).
**Reglas de trabajo** (para personas y para la IA) → [CLAUDE.md](../CLAUDE.md).

## Documentos

| Documento | Qué contiene | Cuándo leerlo |
|---|---|---|
| [ESTADO.md](ESTADO.md) | Lo verificado, lo entregado pendiente de verificar, lo nunca probado y los últimos cambios | Siempre, al empezar |
| [PENDIENTE.md](PENDIENTE.md) | Hoja de ruta por bloques (A: módulos e interfaz; B: mejoras anotadas; C: resto) | Al decidir el siguiente paso |
| [ARQUITECTURA.md](ARQUITECTURA.md) | Principios, componentes, reglas de arquitectura, **mapa del proyecto (qué hace cada archivo)** y qué corre en cada hilo | Para orientarse o encontrar dónde está algo |
| [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md) | Convenciones de los datos, tablas, bloques de columnas (quién escribe cada una), migraciones | Al tocar la base de datos o una consulta |
| [FLUJOS.md](FLUJOS.md) | Paso a paso de cada operación: arranque, catálogo, añadir carpeta, metadatos, miniaturas, cuadrícula, datos del usuario, opciones, barra lateral, cierre, módulos, inspector, eliminar, barra inferior, barra de filtros | Al cambiar el comportamiento de una operación |
| [METADATOS.md](METADATOS.md) | Mapa de campos (qué se extrae y dónde se ve), campos de imagen, vídeo y tracks, prioridad entre etiquetas, equivalencias con Lightroom | Al añadir o corregir un campo |
| [MINIATURAS.md](MINIATURAS.md) | Tamaños, reglas, orígenes por formato, caché | Al tocar las miniaturas |
| [MAPA.md](MAPA.md) | **Diseño, sin implementar**: componente de mapa (`MapView`) para Catálogo, Imagen y Tracks: tecnología, API, capas, elevación, datos, correlación foto-track, edición de GPX y plan por pasos; decisiones pendientes del autor | Antes de empezar la vista de mapa (A.5) o el módulo Tracks (A.6) |
| [COMO_AMPLIAR.md](COMO_AMPLIAR.md) | La tabla «Quiero... → toco...» | Antes de añadir algo nuevo |
| [PRUEBAS.md](PRUEBAS.md) | Autopruebas, ventanas que se abren solas, diagnóstico con ExifTool | Para comprobar un cambio |
| [DECISIONES.md](DECISIONES.md) | Por qué las cosas son como son (con fecha) | Antes de cambiar algo que parece raro |
| [TRAMPAS.md](TRAMPAS.md) | Comportamientos que sorprenden y errores fáciles de cometer | Antes de tocar un área delicada |
| [HISTORIAL.md](HISTORIAL.md) | Registro de cambios y detalle de cómo se probó cada entrega | Solo si hace falta el detalle de algo pasado |

Documentación por módulo (detalle y recetas): [core/metadata/LEEME.md](../core/metadata/LEEME.md) · [core/thumbnails/LEEME.md](../core/thumbnails/LEEME.md) · [core/userdata/LEEME.md](../core/userdata/LEEME.md). Cada archivo `.py` explica en su cabecera qué hace y cómo se usa, y cada función, en su docstring.

## Versiones actuales

Al cambiar una de estas versiones, actualizar esta tabla.

| | |
|---|---|
| Aplicación | Arca Media 26.11.001 (`config/app_paths.py`: `APP_NAME` «arca», `APP_NAME_COMERCIAL` y `APP_VERSION`) |
| Esquema de la base de datos | v4: la v1, consolidada el 05/11/2026, la migración 2 (`metadata_edit_pending`, 10/11/2026), la 3 (`gps_direction` en `media_items`, 11/11/2026) y la 4 (`track_details.overview`, contorno de los tracks, 13/11/2026) (`PRAGMA user_version` = número de migraciones de `core/catalog/catalog_schema.py`; los catálogos llevan la marca `APPLICATION_ID` en `PRAGMA application_id`) |
| Lista de campos de imagen | versión 9 (`IMAGE_FIELDS_VERSION`; incluye la lectura de los datos del usuario y de las palabras clave; GPS con el XMP primero) |
| Lista de campos de vídeo | versión 2 (`VIDEO_FIELDS_VERSION`; con el objetivo; comprobada con vídeos de iPhone) |
| Lector de GPX | versión 3 (`TRACK_EXTRACTOR_VERSION`; umbral de desnivel 8 m; con el contorno simplificado del recorrido, como mucho 1 000 puntos) |
| Motor de miniaturas | versión 2 (`THUMBNAIL_VERSION`) |
| Reglas de las colecciones inteligentes | versión 2 (`collections.rules_json`; con grupos de un nivel; se sigue leyendo la 1); 40 campos en `core/catalog/smart_fields.py` (23 Estándar, 11 Imagen, 6 Tracks GPS; grupos Vídeo, Audio y Ebooks aún vacíos); 29 también como columnas de «Metadatos» (`browse`) |

## Al retomar el proyecto

- **Con Claude Code (VS Code)**: `CLAUDE.md` se lee solo al empezar. Basta con decir qué se quiere hacer.
- **En un chat de claude.ai**: adjuntar el REPOMIX (incluye `CLAUDE.md` y `docs/`) y pedir que lea `CLAUDE.md` y este índice. Si el código y la documentación no coinciden, **manda el código**: hay que corregir la documentación.
- Las salidas de `python -m core.metadata.inspect_cli archivo --json salida.json` de los archivos con los que se esté trabajando ahorran muchas dudas (cuidado: incluyen coordenadas GPS y rutas).
