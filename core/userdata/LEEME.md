# Datos del usuario fuera del catálogo: cómo está organizado

La valoración, la marca (aceptada/rechazada), la etiqueta de color, las palabras clave y
los metadatos descriptivos editados en la aplicación (título, pie, ubicación...) se guardan
en la base de datos **y también fuera de ella**, para que sobrevivan a recrear el catálogo:
basta con volver a añadir las carpetas. Todo lo de aquí es Python puro (sin Qt).

## Mapa

```
core/userdata/
├── policy.py        ► AQUÍ se decide el destino de cada formato (una línea por extensión)
├── editable_fields.py ► Metadatos descriptivos editables (título, pie, ubicación...): una línea por
│                      campo. Se leen y se escriben; falta editarlos en el inspector (C.5)
├── folder_file.py     El archivo de carpeta '.arca.json' (leer, escribir de forma atómica, copia .bak)
├── xmp_writer.py      Escritura en XMP con ExifTool (incrustado o sidecar), con comprobación
└── sync.py            Une catálogo y archivos: el trabajo de escritura y la lectura al importar
```

## Un destino por formato (`policy.py`)

| Destino | Formatos | Dónde |
|---|---|---|
| `XMP_EMBEDDED` | JPEG, TIFF, PNG, WebP, GIF, PSD, DNG, HEIC/HEIF/AVIF | Dentro del propio archivo (como Lightroom) |
| `XMP_SIDECAR` | RAW propietarios: CR2, CR3, NEF, ARW, ORF, RW2, RAF, PEF... | `IMG_0001.xmp` junto al original (se reutiliza `IMG_0001.CR3.xmp` si ya existe) |
| `FOLDER_FILE` | Todo lo demás: vídeo, audio, ebooks, GPX, BMP, JPEG XL... | Un `.arca.json` oculto por carpeta, con una entrada por archivo |

Un solo destino por formato, a propósito: si el mismo dato viviera en dos sitios podrían
acabar distintos sin saber cuál vale. Lo que no está en ninguna lista va a `FOLDER_FILE`,
que nunca modifica el original.

## Cómo fluye

```
Clic en la cuadrícula ──► update_user_field ──► BD (+ bit de pendiente del campo cambiado)
                                                      │  (2 s sin más clics)
                                                      ▼
                         write_pending_user_data (trabajo en segundo plano)
             ┌────────────────────────┼─────────────────────────┐
     XMP incrustado              sidecar .xmp              .arca.json de la carpeta
     (ExifTool, solo             (ExifTool; se crea         (lectura + escritura atómica
      los campos pendientes)      si no existe)              una vez por carpeta)
             └────────────────────────┼─────────────────────────┘
                                      ▼
              se comprueba releyendo ──► se quitan los bits de pendiente
              y se anotan tamaño y fecha nuevos del archivo (sin regenerar miniaturas)

Reconstruir / reescanear:
   add_folder ──► apply_folder_files   (vídeo, audio... desde su .arca.json)
   process_pending_metadata ──► extractor ──► user_data ──► apply_file_user_data (fotos)
                            └─► metadatos editados: no pisa lo pendiente; sin XMP,
                                folder_file_edits (lo editado en el .arca.json manda)
```

## Reglas que conviene recordar

- **Pendiente por campo**: `media_items.user_data_pending` tiene un bit por campo
  (1 = rating, 2 = flag, 4 = color_label). Las **palabras clave** van aparte, en
  `keywords_pending` (0/1): se escriben EXACTAMENTE las del catálogo (XMP:
  `lr:hierarchicalSubject` con las rutas y `dc:subject` con cada palabra y sus padres, como
  Lightroom; `IPTC:Keywords` solo si el archivo ya lo tenía. `.arca.json`: clave `keywords`
  con las rutas). Al releer, lo pendiente no se pisa (`apply_file_keywords`).
  Al escribir solo se tocan los campos pendientes:
  si en la aplicación solo se cambió el color, la valoración que otro programa haya puesto
  en el archivo no se toca.
- **Al releer, manda el archivo**, campo a campo, salvo en los campos pendientes (el cambio
  del usuario es más nuevo). Un campo que el XMP no trae (etiqueta ausente) no toca el
  catálogo; por eso la aplicación escribe el 0 explícito (`xmp:Rating = 0`,
  `xmpDM:Pick = 0`) en lugar de borrar la etiqueta.
- **Nada a medias**: si la lectura se cancela o un sidecar no se puede leer, el extractor
  no entrega datos del usuario y el catálogo no se toca. Una carpeta sin `.arca.json`, o
  con un `.arca.json` dañado (y su copia también), tampoco.
- **RAW**: los datos se leen del sidecar si existe (no del XMP que la cámara guardó dentro
  del RAW). Al quitar las estrellas de un RAW sin sidecar, se crea el sidecar con
  `Rating = 0`.
- **JPEG de una pareja RAW + JPEG**: sus datos se leen solo de su XMP interno, nunca del
  sidecar del RAW (Lightroom hace lo mismo).
- **Archivos tocados fuera** (Lightroom): si al ir a escribir el archivo ha cambiado desde
  el último escaneo, se escribe lo pendiente y se deja el archivo para releer sus
  metadatos (y regenerar su miniatura). La lectura y la escritura nunca van a la vez: el
  controlador las encadena por turnos.
- **Opción "Escribir los cambios en los archivos"** (Opciones > Metadatos; clave
  `write_user_data_to_files` de settings.json, activada por defecto). Si se desactiva, los
  cambios quedan pendientes en el catálogo y se escriben al volver a activarla.
- **Tandas grandes**: al abrir un catálogo con 100 o más elementos pendientes (la primera
  vez tras actualizar la aplicación, p. ej.), se pregunta antes de escribir. Con "Más
  tarde" no se toca ningún archivo en esa sesión.

## Receta: un formato nuevo

1. Si ExifTool sabe escribir XMP dentro de él y otros programas lo leen de ahí: añadir su
   extensión a `_EMBEDDED_EXTENSIONS` (`policy.py`). Comprobarlo antes con una copia:
   `exiftool -XMP-xmp:Rating=3 copia.ext` y releerlo.
2. Si es un RAW propietario: añadirla a `_SIDECAR_EXTENSIONS`.
3. Si no: nada (va a `FOLDER_FILE`).

Cambiar el destino de una extensión que ya tiene datos escritos no los mueve: se leerían
del destino nuevo (vacío). Si algún día hiciera falta, habría que migrarlos.

## Receta: un dato del usuario nuevo (notas, colecciones...)

- En el archivo de carpeta: `merge_entry` ya conserva las claves que no conoce; se añade la
  clave a `USER_DEFAULTS` (`folder_file.py`) y a la lectura (`user_values_from_entry`).
- En XMP: etiqueta a escribir en `xmp_writer.py` y a leer en `IMAGE_USER_FIELDS`
  (`core/metadata/image/fields.py`).
- En la BD: un bit nuevo en `USER_FIELD_BITS` (`media_queries.py`) y ampliar el `CHECK` de
  `user_data_pending` con una migración.

## Receta: un metadato descriptivo editable nuevo

Una línea en `EDITABLE_FIELDS` (`editable_fields.py`) con el siguiente bit libre, su
etiqueta XMP, sus etiquetas antiguas (las mismas, y en el mismo orden, que las de lectura en
`IMAGE_FIELDS`: la autoprueba lo comprueba) y su clave del `.arca.json`. La columna tiene
que existir en `media_items`. Escritura, relectura y marca de pendiente salen solas.
Reglas de escritura (XMP siempre, antiguas solo si existen, resumen IPTC, `#[CSTR]`): en la
cabecera de `xmp_writer.py` y en «Escritura de los metadatos descriptivos» de
`docs/METADATOS.md`.

## Pruebas

```
python -m core.userdata.policy
python -m core.userdata.folder_file
python -m core.userdata.xmp_writer      # necesita ExifTool
python -m core.userdata.sync            # ida y vuelta completa: catálogo -> archivos -> catálogo nuevo
```
