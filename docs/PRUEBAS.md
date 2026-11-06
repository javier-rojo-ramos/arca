# Arca Media — Herramientas y pruebas

> Autopruebas de cada módulo, ventanas que se pueden abrir solas y herramientas de diagnóstico (ExifTool, miniaturas, GPX).
> Índice: [INDEX.md](INDEX.md).

**Autopruebas** (desde la raíz del proyecto; cada una termina con "Autoprueba finalizada correctamente"):

```
python -m core.jobs.progress                 python -m core.metadata.field_spec
python -m core.catalog.catalog_schema        python -m core.metadata.exiftool_runner
python -m core.catalog.catalog_builder       python -m core.metadata.exiftool_extractor
python -m core.catalog.catalog_opener        python -m core.metadata.image.fields
python -m core.catalog.storage_locations     python -m core.metadata.image.extractor
python -m core.catalog.scan_filter           python -m core.metadata.image.pillow_extractor
python -m core.catalog.media_detector        python -m core.metadata.processor
python -m core.catalog.folder_scanner        python -m core.metadata.inspect_cli --autoprueba
python -m core.catalog.catalog_writer        python -m core.database.db_manager
python -m core.catalog.folder_importer
python -m core.thumbnails.sizes              python -m core.thumbnails.generator
python -m core.thumbnails.imaging            python -m core.thumbnails.job
python -m core.thumbnails.cache               python -m core.catalog.color_labels
                                             python -m core.catalog.media_queries
python -m core.catalog.availability          python -m core.catalog.libraries
python -m core.metadata.video.fields         python -m core.metadata.video.rules
python -m core.metadata.video.extractor
python -m core.catalog.smart_fields          python -m core.catalog.smart_rules
python -m core.catalog.system_collections    python -m core.catalog.user_collections
python -m core.catalog.folder_tree           python -m core.catalog.missing_items
python -m core.catalog.selection_metadata    python -m ui_helpers.inspector.formatting
python -m ui_helpers.inspector.metadata_fields  (todas las vistas sobre una foto y un vídeo de ejemplo)
python -m core.catalog.media_removal        (papelera simulada: nunca toca la del sistema)
python -m core.metadata.track.gpx_reader     python -m core.metadata.track.extractor
python -m core.metadata.track.inspect_cli ruta.gpx    (diagnóstico de GPX: resumen y desnivel con varios umbrales)
python -m core.userdata.policy               python -m core.userdata.xmp_writer   (ExifTool)
python -m core.userdata.folder_file          python -m core.userdata.sync         (ExifTool; ida y vuelta completa)
python -m ui_helpers.helpers.card_marks      (dibuja las marcas en una imagen; necesita PySide6)
python -m ui_helpers.widgets.organize_bar    (lógica de la barra y la barra sola en una ventana)
python -m ui_helpers.helpers.theme_style     (colores de los indicadores y una ventana con todos sus estados)
```

El modelo, el delegado, `GridActions`, la barra lateral, `MediaGridView` y los módulos (`controllers/app_modules/`) (UI) no tienen autoprueba: se prueban a mano en la aplicación (qué falta por ver, en [ESTADO.md](ESTADO.md)). La ventana de opciones se puede abrir sola, sin el resto de la aplicación ni tocar `settings.json`: `python -m ui_helpers.dialogs.settings_dialog`. Lo mismo «¿Qué contiene esta carpeta?»: `python -m ui_helpers.dialogs.folder_content_dialog`. Y la ventana «Eliminar» (con una selección mixta inventada): `python -m ui_helpers.dialogs.remove_dialog`.

**Diagnóstico de metadatos** (solo lectura):

```
python -m core.metadata.inspect_cli foto.jpg                 # etiquetas clave por grupo
python -m core.metadata.inspect_cli foto.dng --todo          # todas las etiquetas
python -m core.metadata.inspect_cli foto.heic --campos       # lo que se guardaría en la BD, columna por columna
python -m core.metadata.inspect_cli foto.nef --json salida.json
python -m core.metadata.inspect_cli video.mov --todo         # todas las etiquetas de un vídeo
python -m core.metadata.inspect_cli video.mp4 --campos       # lo que se guardaría (media_items y video_details)
```

**Diagnóstico de miniaturas** (solo lectura; deja una caché de prueba en la carpeta de salida):

```
python -m core.thumbnails.inspect_cli foto.jpg foto.heic foto.dng --salida C:\Temp\prueba
python -m core.thumbnails.inspect_cli foto.dng --detalle          # qué vistas previas trae un RAW y cuál se usa
python -m core.thumbnails.inspect_cli foto.nef --tamanos 160,480
```

**Instalar ExifTool**: Windows, ejecutable de exiftool.org renombrado a `exiftool.exe` junto a su carpeta `exiftool_files` en `tools/exiftool`; macOS, `brew install exiftool`; Linux, `sudo apt install libimage-exiftool-perl`.

**Instalar `pillow-heif`** (HEIC en las miniaturas): `pip install pillow-heif` (o la versión ligera `pi-heif`).


**Consejo**: las salidas de `python -m core.metadata.inspect_cli archivo --json salida.json` de los archivos con los que se esté trabajando (cuidado: incluyen coordenadas GPS y rutas) ahorran muchas dudas sobre qué etiquetas trae cada formato.
