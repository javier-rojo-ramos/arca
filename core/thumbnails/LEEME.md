# Miniaturas: cómo está organizado

Todo lo que genera y guarda las miniaturas está en `core/thumbnails/`. Ningún módulo de
aquí usa Qt. Solo `job.py` toca la base de datos (recibe la conexión como primer parámetro, como el resto de `core/`).

## Mapa

```
core/thumbnails/
├── sizes.py               Los 4 tamaños (160 / 480 / 1200 / 2560) y su calidad JPEG
├── cache.py               Dónde se guarda cada miniatura (ruta derivada del id), escritura atómica
├── imaging.py             Lo común a todo: orientación, modos de color, sRGB, escalera sin ampliar
├── generator.py           generate_thumbnails(): UN archivo -> todos sus tamaños en la caché; THUMBNAIL_VERSION;
│                          load_source_image() (prueba los orígenes en orden)
├── full_image.py          load_full_image(): el original a tamaño completo, con el color de la caché (vista 1:1)
├── job.py                 Trabajo en segundo plano (miniaturas pendientes) e invalidate_thumbnails() para regenerar
├── registry.py          ► AQUÍ se registra qué origen lee cada tipo de medio y extensión
├── sources/
│   ├── base.py            Contrato de un origen + ThumbnailRequest, LoadedImage, errores
│   ├── pillow_source.py   JPG, PNG, WebP, GIF, BMP, TIFF   (+ load_pillow_image, compartido)
│   ├── heif_source.py     HEIC / HEIF   (necesita pillow-heif o pi-heif)
│   └── raw_preview_source.py  DNG, NEF, CR2, CR3, ARW... (vista previa incrustada, vía ExifTool)
├── inspect_cli.py         Diagnóstico: genera miniaturas de archivos reales y las cuenta
└── _testing.py            Solo para las autopruebas
```

## Cómo fluye (para UN archivo)

```
ThumbnailRequest(id, tipo, ruta)
        │
 registry.chain_for(tipo, extensión)  →  [origen 1, origen 2...]   (se prueban en orden)
        │
 origen.load()  →  LoadedImage: imagen YA DERECHA + perfil de color
        │          (JPEG: se decodifica reducido; RAW: se extrae la vista previa mayor)
        ▼
 to_working_mode → plan_sizes (sin ampliar) → reducir al mayor → to_srgb → build_ladder
        │
 ThumbnailCache.store()  →  cache/photo/160/12/12345.jpg, .../480/..., .../1200/..., .../2560/...
```

Generar y regenerar son LA MISMA operación: `generate_thumbnails` sobrescribe lo que hubiera
y sustituye todos los tamaños. Es seguro repetirla y llamarla desde varios hilos.

## Cómo fluye (todo el catálogo)

```
add_folder → process_pending_metadata → generate_pending_thumbnails     (encadenados en el controlador)
                                              │  lotes de 48 · grupo de hasta 4 hilos · un commit por lote
                                              ▼
                          media_items: thumbnail_status (0 pendiente · 1 lista · 2 error),
                          thumbnail_mtime_ns, thumbnail_version, thumbnail_source;  scan_errors (fase 'thumbnail')
```

Un archivo está **pendiente** si `thumbnail_status = 0`, si su `thumbnail_version` es menor que `THUMBNAIL_VERSION`
o si `thumbnail_mtime_ns` no coincide con `file_mtime_ns`. `add_folder` ya deja en 0 los archivos modificados.

## Regenerar a demanda

Regenerar es **marcar como pendiente y lanzar el mismo trabajo**: no hay un segundo camino de código.

```python
controller.regenerate_thumbnails([12, 15, 40])        # esos archivos
controller.regenerate_thumbnails(only_errors=True)    # solo los que fallaron (p. ej. tras instalar pillow-heif)
controller.regenerate_thumbnails()                    # todo el catálogo
```

Por dentro: `invalidate_thumbnails(conn, ids, only_errors=...)` hace `UPDATE thumbnail_status = 0` (no borra la caché: se
sigue viendo la miniatura antigua hasta que se sustituye) y después se lanza `generate_pending_thumbnails`. Solo se
tocan las columnas de estado de miniatura y `scan_errors`; los metadatos, no. Si lo que ha cambiado es el ORIGINAL,
lo correcto es volver a añadir su carpeta (reescaneo): `add_folder` deja pendientes a la vez metadatos y miniatura.

**Cuándo subir `THUMBNAIL_VERSION`** (en `generator.py`): cada vez que cambie el RESULTADO: tamaños o calidad
(`sizes.py`), formato o distribución de la caché (`cache.py`), tratamiento del color o la orientación (`imaging.py`) o la
elección de la imagen de partida (`sources/`). Al subirla se regeneran todas, también las que fallaron. La
autoprueba de `job.py` falla si se cambian tamaños, calidad o formato sin subirla.

## Reglas que conviene recordar

- **La escalera sale siempre completa y nunca se amplía.** Todo archivo con miniaturas tiene los cuatro
  tamaños; si la imagen de partida es más pequeña que un tamaño, ese tamaño contiene la propia imagen, a su
  medida. Ejemplos: partida de 6000 px → 160, 480, 1200, 2560; de 1024 px → 160, 480, 1024, 1024; de 100 px →
  100, 100, 100, 100. Así quien necesite un tamaño lo encuentra siempre en su carpeta y comprobar la caché es
  trivial. El coste es repetir imágenes que ya son pequeñas. `ThumbnailCache.resolve()` sigue sirviendo para
  los archivos aún sin procesar (devuelve el mayor tamaño disponible sin pasar del pedido).
- **La imagen de partida manda, no el original.** Un RAW cuya vista previa incrustada mide 1024 px
  da miniaturas de hasta 1024 px aunque el sensor tenga 6000.
- **Todo sale en JPEG, sRGB y derecho**, sin EXIF ni perfil. La orientación y el color ya están
  aplicados, así que la cuadrícula puede cargar el archivo sin más.
- **La ruta no se guarda en la base de datos**: se calcula con `ThumbnailCache.path_for()`.
- **Las miniaturas son los píxeles del archivo, sin ediciones ni recorte de Lightroom** (decisión tomada: su motor no
  se puede reproducir). Un DNG guardado por Lightroom trae una vista previa re-renderizada por él, que sí las lleva.
- **Un archivo que falla no para nada**: `generate_thumbnails` lanza `ThumbnailError` (dañado) o
  `UnsupportedSourceError` (falta una librería) con un mensaje corto en español, listo para `scan_errors`.
- **Un fallo de la caché sí detiene el trabajo**: `ThumbnailStorageError` (disco lleno, sin permisos) no es culpa del
  archivo, así que el trabajo se aborta sin marcar nada como fallido.

## Receta 1: soportar un formato de imagen nuevo (p. ej. PSD, AVIF)

1. Escribir su origen en `sources/`: una clase que herede de `ThumbnailSource` (o de `PillowSource`
   si Pillow ya puede abrirlo) con `name`, `media_type`, `extensions` y `load()`. `load()` solo
   tiene que devolver una `LoadedImage` derecha; la reducción, el color y el guardado son comunes.
2. Registrarla en `registry.default_registry()`: `registry.register(MiOrigen())`.
3. Si es un formato de un tipo ya existente, asegurarse de que `media_detector.py` reconoce su
   extensión (`DEFAULT_EXTENSION_TO_TYPE`); si no, el archivo ni siquiera llega al catálogo.

Un formato puede tener VARIOS orígenes (uno rápido y uno de respaldo): se prueban en el orden en
que se registraron, y solo se rinde cuando fallan todos. Ejemplo previsto: para los RAW, primero
la vista previa incrustada y después un origen que revele el RAW con LibRaw (rawpy).

## Receta 2: soportar un tipo de medio nuevo (audio, vídeo)

Igual que la anterior, con dos diferencias: el origen declara `media_type = MediaType.AUDIO` (o
`VIDEO`) y `extensions = None` si no depende de la extensión; y la caché ya sabe guardarlo, porque
`cache/<tipo>/` se crea para cada `CACHEABLE_MEDIA_TYPES`. El origen de audio extraerá la carátula
incrustada (ExifTool: `-b -Picture -CoverArt`, el mismo mecanismo que el RAW) y el de vídeo buscará
el póster en `media_assets/posters/`. Los marcadores de posición (póster 2:3, cuadrado) son el
paso 4.

## Receta 3: cambiar tamaños o calidad

Editar `ThumbnailSize` en `sizes.py` y **subir `THUMBNAIL_VERSION`**. Las carpetas de la caché llevan el lado largo
en el nombre, así que un tamaño nuevo usa carpeta nueva (las antiguas quedan huérfanas: limpieza prevista). Para que `DEFAULT_SIZES` no incluya algún tamaño (p. ej.
generar el de 2560 solo a demanda), quitarlo de esa tupla.

## Dependencias

| Qué | Para qué | Instalar |
|---|---|---|
| Pillow | Todo lo anterior | ya instalada |
| pillow-heif **o** pi-heif | HEIC / HEIF. `pi-heif` es la versión solo-decodificar con licencia más permisiva | `pip install pillow-heif` |
| ExifTool | Vista previa de los RAW | ya instalado (`tools/exiftool`) |

Sin pillow-heif, los HEIC fallan con un mensaje que lo explica y se generan solos cuando se
instale. Sin ExifTool pasa lo mismo con los RAW. Al empaquetar con PyInstaller hay que incluir
los datos de pillow-heif (`--collect-all pillow_heif`).

## Diagnóstico

```
python -m core.thumbnails.inspect_cli foto.jpg foto.heic foto.dng
python -m core.thumbnails.inspect_cli foto.nef --salida C:\Temp\prueba --tamanos 160,480
```

Con `--detalle` muestra además, para un RAW, qué vistas previas trae y cuál se usa. Muestra qué origen se usó, los
tamaños escritos y deja la caché de prueba en la carpeta de salida para revisarla a ojo (¿está girada bien una foto vertical? ¿se ven bien los colores del iPhone?).
