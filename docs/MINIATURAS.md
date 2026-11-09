# Arca Media — Miniaturas

> Tamaños, reglas, orígenes por formato y caché. Detalle y recetas en [core/thumbnails/LEEME.md](../core/thumbnails/LEEME.md).
> Índice: [INDEX.md](INDEX.md).

Motor en `core/thumbnails/` (detalle y recetas en `core/thumbnails/LEEME.md`). No usa Qt; solo `job.py` toca la BD.

**Qué se genera**: hasta cuatro JPEG por archivo, medidos por su **lado largo**:

| Tamaño | Lado largo | Calidad JPEG | Uso previsto |
|---|---|---|---|
| `THUMBNAIL` | 160 px | 80 | cuadrícula densa |
| `MEDIUM` | 480 px | 85 | tarjeta de contenido |
| `PREVIEW` | 1200 px | 85 | panel de inspección rápida / vista ampliada |
| `FULLSCREEN` | 2560 px | 88 | vista individual o pantalla completa, sin abrir el original |

Reglas:

- **La escalera sale siempre completa y nunca se amplía**: todo archivo con miniaturas tiene los cuatro tamaños; si la imagen de partida es más pequeña que un tamaño, ese tamaño contiene la propia imagen, a su medida (partida de 1024 px → 160, 480, 1024 y 1024; de 100 px → 100 en los cuatro). La misma regla servirá para las carátulas de audio.
- **Una decodificación, todos los tamaños**: cada tamaño se obtiene reduciendo el anterior. Los JPEG se decodifican ya reducidos (`draft`).
- **JPEG, sRGB y derecho, sin EXIF ni perfil**: orientación y color ya aplicados (Display P3 de los iPhone, Adobe RGB y CMYK se convierten a sRGB; la transparencia se aplana sobre gris). Así la cuadrícula carga el archivo sin más.
- **Sin ediciones de Lightroom ni recorte**: la miniatura son los píxeles del archivo tal cual (ver [DECISIONES.md](DECISIONES.md)).
- **Ruta derivada del id** (no se guarda en la BD): `cache/<tipo>/<lado largo>/<id // 1000>/<id>.jpg`. Escritura atómica. `ThumbnailCache.resolve(tipo, id, tamaño)` devuelve el mayor tamaño disponible sin pasar del pedido; `smallest_covering(píxeles)` elige el tamaño según lo que se va a mostrar (píxeles físicos = lado lógico × `devicePixelRatio`).

**Orígenes** (cadena por tipo de medio y extensión; se registran en `registry.default_registry()`; se prueban en orden y se rinde cuando fallan todos):

| Origen | Extensiones | Cómo |
|---|---|---|
| `pillow` | jpg, jpeg, png, gif, bmp, tif, tiff, webp | Pillow |
| `heif` | heic, heif, hif | Pillow + `pillow-heif` o `pi-heif`; sin ellas, error con instrucciones. La rotación la aplica la librería (en un HEIC vive en `irot`) |
| `raw_preview` | dng, nef, nrw, cr2, cr3, crw, arw, orf, rw2, pef, raf... | La mayor vista previa JPEG incrustada, con **una** llamada a ExifTool por archivo (`-b -JpgFromRaw -PreviewImage -OtherImage -ThumbnailImage -Orientation`; en JSON salen en base64). Orientación: la del RAW, salvo que la vista previa traiga la suya |

**Estado y trabajo**: columnas en [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md); flujo y regeneración en [FLUJOS.md §5](FLUJOS.md). `THUMBNAIL_VERSION` (en `generator.py`) se sube cuando cambia el RESULTADO (tamaños, calidad, formato, color, elección de la imagen de partida); la autoprueba de `job.py` avisa si se cambian tamaños, calidad o formato sin subirla.

**Sin miniatura** (vídeo, audio, ebook y track, hasta el paso 4b; o una foto con error): la cuadrícula dibuja un marcador por tipo y, en vídeo y audio, la duración ([FLUJOS.md §6](FLUJOS.md)). No se guarda ningún archivo por elemento.

**Límites conocidos**: la imagen de partida de un RAW es su vista previa, normalmente menor que el sensor. El DNG de prueba (guardado por Lightroom) trae un JPEG de 1024 px y tres JPEG XL (1600, 512 y 256 px) que Pillow no abre, así que sus miniaturas llegan a 1024 px (los tamaños de 1200 y 2560 contienen esa misma imagen, sin ampliar). Lightroom re-renderiza esa vista previa con sus ediciones (probablemente incluido el recorte), de modo que la miniatura de un DNG editado puede salir recortada y la de un HEIC o JPG, no. Está prevista una opción con `rawpy` (revelado sin editar) para cuando haga falta.
