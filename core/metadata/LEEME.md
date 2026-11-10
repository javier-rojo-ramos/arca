# Extracción de metadatos: cómo está organizada

Todo lo que lee los metadatos de los archivos (EXIF, XMP, IPTC...) y los guarda en la
base de datos está en `core/metadata/`. Ningún módulo de aquí usa Qt.

## Mapa

```
core/metadata/
├── registry.py            ► AQUÍ se registra qué extractor lee cada TIPO de medio
├── processor.py             El trabajo que recorre los archivos pendientes (igual para todos los tipos)
├── base.py                  El contrato de un extractor + columnas protegidas
│
├── exiftool_runner.py       Ejecuta ExifTool por lotes (compartido por todos los tipos)
├── exiftool_extractor.py    Extractor genérico basado en ExifTool: lotes, sidecars .xmp, lista de campos y de datos del usuario
├── field_spec.py            Cómo se escribe un campo ("esta columna sale de estas etiquetas") y sus conversores
├── keyword_tags.py          Palabras clave de un archivo (lr:HierarchicalSubject, dc:Subject, IPTC): rutas y sueltas
│
├── image/                 ► Todo lo de las IMÁGENES, en su carpeta
│   ├── fields.py          ► AQUÍ se añaden campos de imagen (una línea por campo) + la versión;
│   │                        también IMAGE_USER_FIELDS (rating, marca y color que trae el archivo)
│   ├── rules.py             Reglas especiales: fecha de captura, orientación, tamaño y recorte, flash, GPS
│   ├── extractor.py         Une lista de campos + reglas en el extractor de imágenes
│   └── pillow_extractor.py  Alternativa sin ExifTool (solo JPEG/PNG/TIFF/WebP/GIF/BMP y EXIF)
│
├── video/                 ► Todo lo de los VÍDEOS (con ExifTool; misma estructura que image/)
│   ├── fields.py          ► AQUÍ se añaden campos de vídeo + VIDEO_FIELDS_VERSION
│   │                        (y el conversor 'aperture': la apertura «F1.78» de los iPhone)
│   ├── rules.py             Reglas: fecha (hora local o QuickTime en UTC), tamaño con rotación, GPS
│   └── extractor.py         VideoExtractor (tabla de detalles: video_details)
├── track/                   Tracks GPS (GPX), sin ExifTool
├── audio/  (futuro)
└── inspect_cli.py           Herramienta de diagnóstico: qué lee ExifTool y qué se guardaría
```

## Cómo fluye

```
add_folder  →  media_items (scan_version = 0)
                    │
   process_pending_metadata  (trabajo en segundo plano, con barra y botón Cancelar)
                    │   lotes de 100 archivos
                    ▼
   registry.get(media_type)  →  extractor del tipo  →  extract_batch(rutas)
                    │                                        │
                    │              ExifToolExtractor: ExifTool (1 llamada por lote) + sidecars
                    │                                        │
                    │              lista de campos (fields.py)  →  reglas (rules.py)
                    ▼
   guarda en media_items (+ tabla de detalles del tipo) y anota scan_version
                    │
                    └─ datos del usuario del archivo (result.user_data)  →  apply_file_user_data
                       (core/userdata/sync.py: manda el archivo, salvo en los campos
                        pendientes de escribir; ver core/userdata/LEEME.md)
```

Un archivo está **pendiente** si el extractor de su tipo tiene una `version` mayor que
la `scan_version` guardada en el archivo. Por eso subir la versión de un extractor hace
que se relean todos los archivos de ese tipo: ese es el "reescaneo".

## Receta 1: añadir un campo de imagen

Ejemplo: guardar el "modo de exposición" (`ExifIFD:ExposureMode`: 0 = automática, 1 = manual,
2 = horquillado), que ExifTool ya devuelve para tus fotos.

1. **Columna** (si no existe): una migración nueva al final de `MIGRATIONS` en
   `core/catalog/catalog_schema.py`. Nunca se editan las anteriores.
   - Campo válido para cualquier tipo de medio → `ALTER TABLE media_items ADD COLUMN ...`
   - Campo solo de fotos → `ALTER TABLE photo_details ADD COLUMN ...`
2. **Una línea** en `IMAGE_FIELDS` de `image/fields.py`:
   - `common("columna", ("Grupo:Etiqueta", ...), conversor)` para `media_items`
   - `detail("columna", ("Grupo:Etiqueta", ...), conversor)` para `photo_details`
   Las etiquetas se prueban por orden y gana la primera que exista. Con
   `python -m core.metadata.inspect_cli archivo.jpg` se ven las etiquetas y grupos reales.
3. **Subir** `IMAGE_FIELDS_VERSION` en el mismo archivo.
4. **Comprobar**: `python -m core.metadata.image.fields` (confirma que la columna existe).
   y `python -m core.metadata.inspect_cli archivo.jpg --campos` para ver el valor.

Al abrir la aplicación, la migración se aplica sola y las fotos se vuelven a leer.
(Editar la migración 1 solo vale si se van a crear de nuevo todos los catálogos, como al
consolidar el esquema el 05/11/2026.)

Si el campo necesita lógica (depende de varias etiquetas, hay que derivarlo o validarlo),
se escribe en `image/rules.py` en lugar de en la lista.

Conversores disponibles (`field_spec.py`): `text`, `real`, `integer`, `datetime_text`,
`orientation_code`, `image_width`, `image_height` y, para los datos del usuario,
`rating_value` (0 a 5; un 0 escrito es un dato) y `pick_flag` (1 marcada, 0 sin marca,
-1 rechazada). Ambos devuelven None si la etiqueta no está ("el archivo no dice nada").

## Receta 1b: datos del usuario que trae el archivo (rating, marca, color)

Rating, marca y etiqueta de color son del **usuario** (bloque C), no metadatos extraídos,
así que NO van en `IMAGE_FIELDS` sino en `IMAGE_USER_FIELDS` (`image/fields.py`):

```python
common("rating", ("XMP-xmp:Rating",), rating_value),
common("flag", ("XMP-xmpDM:Pick",), pick_flag),
common("color_label", ("XMP-photoshop:LabelColor", "XMP-xmp:Label"), normalize_color_label),
```

- El extractor los lee (`user_fields` en la clase del extractor) y los devuelve en
  `ExtractionResult.user_data`; nunca escribe esas columnas (siguen en `PROTECTED_COLUMNS`).
  Los lee de donde la aplicación los escribe (`core/userdata/policy.py`): del sidecar en
  los RAW (si existe), del propio archivo en los demás (nunca del sidecar del RAW en una
  pareja RAW + JPEG). Si un sidecar no se pudo leer, `user_data` queda vacío; si la lectura
  se canceló antes de leer el sidecar, el archivo cuenta como no leído.
- El procesador los aplica solo en los formatos con destino XMP, con
  `core.userdata.sync.apply_file_user_data`: **manda el archivo**, campo a campo, salvo en
  los campos pendientes de escribir (`user_data_pending`); un campo que el archivo no trae
  no toca nada. Los formatos sin XMP (vídeo, audio...) toman estos datos del archivo de
  carpeta `.arca.json` al añadir la carpeta (`apply_folder_files`).
- Subir `IMAGE_FIELDS_VERSION` relee las fotos: lo que el usuario cambió aquí y aún no se
  ha escrito está protegido; lo demás se actualiza con lo que digan los archivos.
- Otro tipo de medio que tenga estos datos en su archivo define su propia lista
  `<TIPO>_USER_FIELDS` y la asigna a `user_fields` en su extractor.

## Receta 2: añadir un tipo de medio nuevo (vídeo, audio, ebooks...)

1. Crear `core/metadata/<tipo>/` con `__init__.py`, `fields.py` y `extractor.py`, copiando
   la estructura de `image/`:
   - `fields.py`: la lista `VIDEO_FIELDS` y `VIDEO_FIELDS_VERSION` (empieza en 1).
   - `extractor.py`: una clase que hereda de `ExifToolExtractor` y define `media_type`,
     `version`, `details_table` y `fields` (y `apply_rules` si hace falta).
2. Crear la tabla de detalles del tipo (`video_details`...) con una migración nueva:
   `media_id INTEGER PRIMARY KEY REFERENCES media_items(id) ON DELETE CASCADE` y sus columnas.
3. Registrarlo en `registry.default_registry()`: `registry.register(VideoExtractor(runner))`.

Nada más: el procesador, el trabajo en segundo plano y la barra de progreso lo usan
sin cambios. Los archivos de ese tipo, que hasta entonces estaban pendientes, se leerán
al abrir el catálogo. Si un tipo no puede usar ExifTool, se escribe un extractor que
herede directamente de `MetadataExtractor` (implementa `extract`, y `extract_batch` si
su motor lo agradece).

## Reglas que conviene recordar

- **Prioridad entre fuentes**: datos descriptivos (título, pie, ubicación, autor) →
  XMP, luego IPTC, luego EXIF. Datos técnicos de la toma → EXIF, luego XMP. El sidecar
  `.xmp` manda sobre el XMP incrustado. La prioridad es el orden de las etiquetas en
  cada línea de la lista.
- **Columnas protegidas** (`base.PROTECTED_COLUMNS`): los extractores nunca escriben las
  del archivo, las del usuario (valoración, marcas, etiquetas, notas) ni las de control.
  Si se intenta, el trabajo falla con un mensaje claro. (Los datos del usuario que trae el archivo
  no se escriben desde el extractor: viajan en `user_data`, ver la receta 1b.)
- **Un valor `None`** deja la columna vacía (borra un valor antiguo). Solo `title` es
  distinto: nunca se vacía, porque es obligatorio; el procesador pone el nombre del
  archivo sin extensión.
- **Metadatos editables** (título, pie, ubicación...; `core/userdata/editable_fields.py`):
  el procesador no pisa los que el usuario ha cambiado y aún no están escritos (su bit de
  `metadata_edit_pending`), y en los formatos sin XMP manda lo editado en el `.arca.json`.
  El extractor no tiene que hacer nada especial.
- **Un archivo que falla** no para el trabajo: se anota en `scan_errors` (fase `metadata`)
  y no se reintenta hasta que cambie el archivo o suba la versión.
