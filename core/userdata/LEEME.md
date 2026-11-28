# Datos del usuario fuera del catálogo: cómo está organizado

La valoración, la marca (aceptada/rechazada), la etiqueta de color, las palabras clave y
los metadatos descriptivos editados en la aplicación (título, pie, ubicación...) se guardan
en la base de datos **y también fuera de ella**, para que sobrevivan a recrear el catálogo:
basta con volver a añadir las carpetas. Todo lo de aquí es Python puro (sin Qt).

## Mapa

```
core/userdata/
├── policy.py        ► AQUÍ se decide el destino de cada formato (una línea por extensión)
├── editable_fields.py ► Metadatos descriptivos editables (título, pie, ubicación, GPS...): una línea por
│                      campo. Se editan en el inspector («Metadatos» de Imagen)
├── folder_file.py     El archivo de carpeta '.arca.json' (leer, escribir de forma atómica, copia .bak)
├── xmp_writer.py      Escritura en XMP con ExifTool (incrustado o sidecar), con comprobación
├── writers.py       ► AQUÍ se añade un ESCRITOR nuevo: la interfaz ('UserDataWriter'), el del
│                      '.arca.json' y el de XMP; 'split_items' reparte un archivo entre el
│                      escritor de su formato y el '.arca.json'
├── audio_writer.py    El escritor de las etiquetas de las canciones (hoy, MP3), con el motor de
│                      'core/audio/tag_writer.py' (MUS 6.2b)
├── audio_fields.py    Qué columnas de una canción van a sus etiquetas y a qué campo (la tabla del
│                      escritor de audio; lo demás, al '.arca.json')
└── sync.py            Une catálogo y archivos: el trabajo de escritura (qué hay pendiente, repartirlo
                       entre los escritores y anotar el resultado) y la lectura al importar
```

## Un destino por formato (`policy.py`)

| Destino | Formatos | Dónde |
|---|---|---|
| `XMP_EMBEDDED` | JPEG, TIFF, PNG, WebP, GIF, PSD, DNG, HEIC/HEIF/AVIF | Dentro del propio archivo (como Lightroom) |
| `XMP_SIDECAR` | RAW propietarios: CR2, CR3, NEF, ARW, ORF, RW2, RAF, PEF... | `IMG_0001.xmp` junto al original (se reutiliza `IMG_0001.CR3.xmp` si ya existe) |
| `FOLDER_FILE` | Todo lo demás: vídeo, audio (salvo MP3), ebooks, GPX, BMP, JPEG XL... | Un `.arca.json` oculto por carpeta, con una entrada por archivo |
| `AUDIO_TAGS` | MP3 (desde `MUS 6.2b`), FLAC, Ogg y Opus (desde `MUS 6.3b`) y M4A (desde `MUS 6.4`) | **Partido**: lo editado de sus etiquetas (título, artista, comentario, álbum, artista del álbum, pista, disco, género, compositor; `audio_fields.py`), en el propio archivo; la valoración, la marca, el color, las palabras clave y lo demás, en su entrada del `.arca.json` |

Un solo destino por formato, a propósito: si el mismo dato viviera en dos sitios podrían
acabar distintos sin saber cuál vale (en uno partido, cada dato sigue teniendo un sitio). Lo que no está en ninguna lista va a `FOLDER_FILE`,
que nunca modifica el original.

**Las preguntas a un destino** (separadas el 28/11/2026, `MUS 6.2a`, para el primer formato
partido, el MP3): no se pregunta «¿es `FOLDER_FILE`?», sino lo que se quiere saber:

| Pregunta (`policy.py`) | Para qué | Hoy |
|---|---|---|
| `uses_xmp` | El extractor lee del archivo la valoración, la marca, el color y las palabras clave | XMP incrustado y sidecar |
| `has_folder_entry` | Tiene entrada en el `.arca.json`: va con el archivo al renombrarlo o moverlo y se borra al eliminarlo | `FOLDER_FILE` y `AUDIO_TAGS` |
| `folder_file_fields` | Qué datos guarda esa entrada (lo demás sale del archivo): la lectura al añadir una carpeta (`apply_folder_files`) y al releer (`folder_file_edits`) | `FOLDER_FILE`, todos; `AUDIO_TAGS`, todos menos los de sus etiquetas |
| `waits_for_first_read` | Su destino lo lee el extractor: no se escribe hasta la primera lectura | XMP incrustado, sidecar y `AUDIO_TAGS` |

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
- **La primera lectura no borra nada del archivo** (18/11/2026, `GEN 20`): un archivo con
  XMP que no se ha leído nunca (`last_scanned_at` vacío: solo lo pone la lectura de
  metadatos, también si falla) **no se escribe**; lo pendiente espera a esa lectura. En
  ella, las palabras clave asignadas antes **se suman** a las del archivo (el usuario aún
  no las había visto: no ha podido quitar ninguna); la valoración, la marca, el color y
  los metadatos editados, como siempre, mandan los pendientes. Antes, asignar una palabra
  a una foto sin leer (mientras se leían los metadatos, o con la lectura cancelada)
  dejaba en el archivo solo esa.
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

## Receta: un escritor nuevo (etiquetas de audio, el OPF de un EPUB...)

Desde el 16/11/2026 (`GEN 14`), el trabajo de escritura (`sync.write_pending_user_data`) no sabe cómo escribe cada formato: reparte los archivos pendientes entre los escritores de `writers.py`. Para uno nuevo, **`sync.py` no se toca**:

1. Una clase que herede de `UserDataWriter` (en su archivo, si es larga). Su `write(items, cancel_event)` recibe los `WriteItem` de un lote; de cada uno escribe **solo** `item.wanted` (los campos pendientes, con su valor) y apunta en él cómo ha ido: `ok`, `written`, `message`, `deferred` (no se intentó: falta la herramienta), `db_updates` (el tamaño y la fecha nuevos del archivo) y `rescan` (había cambiado fuera). No lanza excepciones por un archivo ni por su herramienta; si esta no está, pone `unavailable`.
2. Su destino en `policy.py` (`UserDataDestination` y las extensiones que lo usan), con sus respuestas a las preguntas de arriba (`_XMP_DESTINATIONS`, `_FOLDER_FILE_FIELDS` y `_FIRST_READ_DESTINATIONS`; la autoprueba exige que diga qué guarda el `.arca.json`), y su línea en `default_writers` (`writers.py`).
3. Si no sabe guardar todos los campos (unas etiquetas de audio no tienen dónde poner el color), `fields_for(item)` devuelve los que sí. **Lo demás va solo al `.arca.json`** (`split_items`): el archivo se parte en dos `WriteItem`, y cada parte quita sus marcas de pendiente por separado (si una falla, solo esa sigue pendiente). Hoy ningún formato se parte: XMP sabe guardar todo lo de las fotos.
4. Las reglas de siempre (ver «Archivos del usuario» en `CLAUDE.md`): solo lo pedido, conservar lo que no se conoce, escribir en un temporal que sustituye al original una vez comprobado, y no tocar el contenido.
5. **La lectura de un formato partido** (preparada en `MUS 6.2a`): lo que guarda su entrada del `.arca.json` lo dice `folder_file_fields`, y `apply_folder_files` (al añadir una carpeta) y `folder_file_edits` (al releer) solo aplican eso; lo demás sale del archivo, con el extractor. El primero es el MP3 (`MUS 6.2b`; su escritor, `audio_writer.py`, y su autoprueba de ida y vuelta, la sección 11 de la de `sync.py`).

Para probarlo sin tocar originales: `write_pending_user_data(conn, writers={...})` admite los escritores (ver el escritor de mentira del final de la autoprueba de `sync.py`).

## Receta: un dato del usuario nuevo (notas, colecciones...)

- En el archivo de carpeta: `merge_entry` ya conserva las claves que no conoce; se añade la
  clave a `USER_DEFAULTS` (`folder_file.py`) y a la lectura (`user_values_from_entry`).
- En XMP: etiqueta a escribir en `xmp_writer.py` y a leer en `IMAGE_USER_FIELDS`
  (`core/metadata/image/fields.py`).
- En la BD: un bit nuevo en `USER_FIELD_BITS` (`media_queries.py`) y ampliar el `CHECK` de
  `user_data_pending` con una migración.

## Receta: un metadato descriptivo editable nuevo

**Un campo, varios escritores** (14/11/2026): el campo se declara una vez en `EDITABLE_FIELDS` y cada escritor dice qué campos sabe guardar. Un campo puede **no tener etiqueta XMP** (`xmp_tag` vacío: el escritor de XMP no lo conoce y va al `.arca.json`), estar en una **tabla de detalles** (`table`: se lee con `read_sql`, se protege con `unless_pending_sql` o, en el guardado del procesador, con `upsert_sql`) y ser **solo de algunos tipos de archivo** (`media_types`: en los demás ni se guarda ni queda pendiente, `applies_sql`). El primero así es la actividad de un track (`activity_type`, en `track_details`). Un campo de `media_items` también puede ser solo de algunos tipos: el año de las canciones (`content_created_at`, `MUS 7.1a`), que en las fotos es su fecha de captura; todo lo que guarda un campo editable mira a qué tipos se aplica (`applies_sql`, `applies_to`). Su precisión y su origen van con él (`LINKED_COLUMNS`, `linked_values`: se guardan al editarlo y se protegen igual), y en el `.arca.json` va como número (`folder_value`: `"year": 1999`). Un escritor nuevo (ID3, `.nfo`...) lleva su propia tabla campo → etiqueta (las de XMP se quedan aquí, en `xmp_tag` y `legacy_tags`: decidido el 16/11/2026) y su destino en `policy.py`: receta de arriba.

Una línea en `EDITABLE_FIELDS` (`editable_fields.py`) con el siguiente bit libre, su
etiqueta XMP, sus etiquetas antiguas (las mismas, y en el mismo orden, que las de lectura en
`IMAGE_FIELDS`: la autoprueba lo comprueba) y su clave del `.arca.json`. La columna tiene
que existir en `media_items`. Escritura, relectura y marca de pendiente salen solas.
Reglas de escritura (XMP siempre, antiguas solo si existen, resumen IPTC, `#[CSTR]`): en la
cabecera de `xmp_writer.py` y en «Escritura de los metadatos descriptivos» de
`docs/METADATOS.md`.

Un campo NUMÉRICO (como los del GPS): `kind=NUMBER` y, si hace falta, `limits` y `circular`.
Se guarda como número en la columna y en el `.arca.json`; dos columnas que no tienen sentido
por separado (latitud y longitud) van en `PAIRED_COLUMNS`. El GPS se escribe en el XMP o el
EXIF con su propia regla (docs/DECISIONES.md, 11/11/2026), no con la de los textos.

## Pruebas

```
python -m core.userdata.policy
python -m core.userdata.folder_file
python -m core.userdata.xmp_writer      # necesita ExifTool
python -m core.userdata.sync            # ida y vuelta completa: catálogo -> archivos -> catálogo nuevo
```
