# Arca Media — Módulo Ebooks (Libros): arquitectura y plan

> Documento del módulo Ebooks (biblioteca `ebook`, «Libros» en la interfaz; el módulo aún no existe). Tiene dos partes: **I, arquitectura** y **II, planificación** (fases y pasos, con el código `EBK`).
> **Estado (16/11/2026): diseño acordado con el autor como punto de partida (propuesta del asistente, aprobada); sin implementar.** Todo lo de la parte I que no esté en «Punto de partida» es lo PREVISTO. Lo marcado «a comprobar» no se ha probado con archivos reales (en el catálogo del autor no hay ningún libro todavía): las decisiones del final se confirman o se corrigen al llegar a su paso. Si el código y este documento no coinciden, manda el código.
> Índice: [INDEX.md](INDEX.md). Decisiones: [DECISIONES.md](DECISIONES.md) (16/11/2026).

## Resumen

**Objetivo** (el autor, 16/11/2026): lo mismo que en los demás módulos, para los libros electrónicos: cargarlos, ver sus datos y su portada, editar los metadatos básicos y clasificarlos (valoración, marca, color, palabras clave).

**Las ideas del diseño**:

1. **El EPUB es el formato central.** Es un estándar abierto, sus metadatos se leen y se escriben con lo que el proyecto ya tiene (sin dependencias nuevas) y es lo que usa casi todo el mundo fuera de Amazon. Los demás formatos se leen; escribir en ellos, solo donde es seguro.
2. **Se reutiliza lo que ya hay**: las columnas comunes (`title`, `creator`...), el extractor con su tabla de detalles, el mecanismo de edición «un campo, varios escritores», la tarjeta 2:3 de los carteles, la vista de lista de Música y, para un libro en varios formatos, la tarjeta agrupada de Vídeo.
3. **Lo editado se guarda en el propio archivo** cuando el formato lo permite sin riesgo (EPUB y PDF), con archivo temporal y comprobación (regla del 16/11/2026); en los demás, y en cualquier libro con protección (DRM), en el `.arca.json` de la carpeta.
4. **Convive con Calibre**, que es el programa de referencia: si una carpeta viene de una biblioteca de Calibre, sus `metadata.opf` y `cover.jpg` se leen; no se escriben.
5. **Primero útil sin internet** y sin escribir nada: módulo, lectura, portadas y navegación. Después, la escritura y la edición; al final, la descarga de datos por ISBN.
6. **No es un lector ni un conversor**: abrir un libro lo hace el programa del sistema, y convertir entre formatos, Calibre.

---

# Parte I — Arquitectura

## 1. Lo básico de los libros electrónicos

Para orientarse; es lo que condiciona todo el diseño.

| Formato | Qué es | Metadatos | Portada | ¿Se puede escribir? |
|---|---|---|---|---|
| **EPUB** (`.epub`) | Un ZIP con páginas HTML y un archivo «OPF» que describe el libro. Estándar abierto | En el OPF, como XML (Dublin Core): título, autores, idioma, editorial, fecha, identificador (ISBN), descripción, materias y, por convenio, la serie | Una imagen del propio ZIP, señalada en el OPF | **Sí**: se reescribe el OPF dentro del ZIP. Es lo que hacen Calibre y Sigil |
| **PDF** (`.pdf`) | Páginas fijas (libros maquetados, manuales, escaneos) | Pocos y a menudo vacíos o erróneos (título, autor, palabras clave) y, a veces, XMP. Sí da el número de páginas | No tiene: se usa la primera página, que hay que dibujar | **Sí**, con ExifTool (a comprobar), que ya escribe XMP en otros formatos |
| **MOBI / AZW3** (`.mobi`, `.azw3`, `.azw`) | Los formatos de Kindle (Amazon). Binarios | Una cabecera con título, autor, editorial, identificador de Amazon | Una imagen interna | **No se propone**: formato cerrado y sin una biblioteca fiable; lo editado, al `.arca.json` |
| **FB2** (`.fb2`) | XML, habitual en Rusia y en algunas bibliotecas | En el propio XML | Dentro, en base64 | No de partida |
| **CBZ / CBR** (`.cbz`, `.cbr`) | Cómics: un ZIP o un RAR de imágenes | Un `ComicInfo.xml` opcional | La primera imagen | Fuera de la primera versión (E2) |

Tres cosas más:

- **DRM (protección anticopia)**: muchos libros comprados (Amazon, y los EPUB con Adobe DRM) llevan el contenido cifrado. Sus metadatos suelen poder leerse, pero **no se debe escribir en ellos**: puede dejar el libro ilegible en su lector. La aplicación lo detecta, lo indica y no los toca.
- **Calibre**: organiza cada libro en una carpeta `Autor/Título (id)/` con el libro en uno o varios formatos, un `metadata.opf` (el mismo formato OPF del EPUB) y un `cover.jpg`. Leer esos dos archivos da datos buenos sin abrir el libro.
- **Un libro, varios archivos**: es normal tener el mismo libro en EPUB, MOBI y PDF. Es el mismo problema que una película en dos partes ([MOD_VIDEO.md](MOD_VIDEO.md) §10): una tarjeta por libro.

## 2. Punto de partida (lo que ya existe)

- **Detección**: `core/catalog/media_detector.py` reconoce como `MediaType.EBOOK` los `.epub`, `.mobi`, `.azw3` y `.fb2`. **No** los `.pdf`, `.azw`, `.cbz` ni `.cbr`.
- **Biblioteca**: `Library.EBOOK` («Libros»); una carpeta se puede declarar de libros en «¿Qué contiene esta carpeta?» y entonces solo se catalogan ebooks. En una carpeta automática, un ebook va a esa biblioteca.
- **Nada más**: no hay módulo, ni botón en la toolbar, ni extractor (no se lee ningún metadato), ni miniatura (la tarjeta dibuja el marcador). El icono `resources/images/library_books.svg` existe, sin registrar. El grupo «Libros electrónicos» de las colecciones inteligentes existe vacío (`core/catalog/smart_fields.py`).
- **Datos del usuario**: valoración, marca, color y palabras clave, en el `.arca.json` de la carpeta, como todo lo que no es foto.
- **En el catálogo del autor** (16/11/2026): ningún libro.

## 3. Dónde vivirá cada cosa

| Qué | Dónde | Notas |
|---|---|---|
| Leer y escribir el OPF; abrir un EPUB (metadatos, portada, DRM) | `core/ebooks/` (nuevo; sin Qt ni BD): `opf.py`, `epub.py` | Con `zipfile` y `defusedxml`, que ya es dependencia. El lector de OPF sirve también para el `metadata.opf` de Calibre |
| Extractor | `core/metadata/ebook/` (nuevo): `extractor.py`, `fields.py`, `inspect_cli.py` | `MetadataExtractor` con `details_table = "ebook_details"`; reparte por formato (EPUB propio; PDF y Kindle, con ExifTool) |
| Tabla de detalles | `core/catalog/catalog_schema.py`, una migración | §4 |
| Portada como miniatura | `core/thumbnails/sources/ebook_cover_source.py` (nuevo) | §6 |
| Campos editables y escritor | `core/userdata/editable_fields.py`, `core/userdata/ebook_writer.py` (nuevo) | Declara qué campos sabe guardar en cada formato |
| Módulo y barra | `controllers/app_modules/ebook_module.py` (nuevo, sobre `LibraryModule`); `ui/main_window.ui` (el botón) | Como `VideoModule` y `AudioModule` |
| Inspector | `ui_helpers/inspector/ebook_section.py` (nuevo) | Sección «Libro» |
| Consultas | `core/catalog/` | Datos de la sección, valores de las secciones de la barra |
| Descarga de datos | `core/ebooks/providers/` (nuevo) | Como los proveedores de Vídeo |

## 4. Datos (a cerrar en `EBK 2.2`)

**Columnas comunes** (`media_items`), para que el filtro de texto, el orden y «Fechas» sirvan sin nada nuevo:

| Dato | Columna |
|---|---|
| Título | `title` (si el libro no lo trae, el nombre del archivo) |
| Autor o autores | `creator` |
| Descripción (sinopsis) | `description` (sin las etiquetas HTML que suele traer) |
| Fecha de publicación | `content_created_at`, con su precisión (casi siempre, el año) |

**`ebook_details`** (una fila por libro):

| Columna | Qué es |
|---|---|
| `author_sort` | Autor para ordenar («García Márquez, Gabriel») |
| `series`, `series_index` | Serie y número dentro de ella |
| `publisher` | Editorial |
| `language` | Idioma (clave de dos letras, como en el archivo; se muestra con su nombre) |
| `isbn`, `identifiers` | ISBN, y los demás identificadores tal cual (Amazon, Google, UUID) |
| `subjects` | Materias o géneros, como texto (E6) |
| `page_count` | Páginas (solo PDF; un EPUB no tiene páginas fijas) |
| `book_format` | `epub`, `pdf`, `mobi`, `azw3`, `fb2` |
| `has_cover` | Tiene portada |
| `drm` | Está protegido: no se escribe en él |
| `metadata_source` | De dónde salieron los datos: el propio archivo o el `metadata.opf` de Calibre |
| `read`, `read_at` | Leído / no leído y cuándo (dato del usuario) |

**Versión**: `EBOOK_FIELDS_VERSION` (nueva; en `media_items.scan_version`): al subirla, los libros se releen solos. Va a la tabla de versiones de [INDEX.md](INDEX.md) y a la lista de [CLAUDE.md](../CLAUDE.md).

## 5. Lectura

- **EPUB**: se abre el ZIP, `META-INF/container.xml` dice dónde está el OPF, y de él salen los campos. La serie no es parte del estándar antiguo: se lee de los dos convenios que existen (el de Calibre, `calibre:series`, y el de EPUB 3, `belongs-to-collection`). Si existe `META-INF/encryption.xml` con el contenido cifrado, el libro tiene DRM.
- **`metadata.opf` de Calibre**: si está junto al libro, manda sobre lo que trae el archivo (Calibre no siempre actualiza el archivo; su OPF es lo que el usuario corrigió allí). Vale para cualquier formato.
- **PDF**: título, autor, palabras clave y número de páginas con ExifTool, que el proyecto ya usa. Los títulos de los PDF son poco fiables: si viene vacío o es un nombre de archivo temporal, se queda el nombre del archivo.
- **MOBI / AZW3**: con ExifTool, **a comprobar** con archivos reales en `EBK 2.5`; si no basta, un lector propio de su cabecera.
- Un libro sin metadatos no es un error. Uno dañado, a `scan_errors`, como los demás. **Un extractor nunca escribe datos del usuario.**
- Diagnóstico: `python -m core.metadata.ebook.inspect_cli archivo`, para comparar con Calibre.

## 6. Portadas

Orden de búsqueda (la tarjeta 2:3 de los carteles ya existe):

1. `cover.jpg` de Calibre, si está junto al libro.
2. La portada interna del EPUB (la que señala el OPF; si no señala ninguna, la primera imagen razonable).
3. La portada interna de MOBI / AZW3 (a comprobar).
4. La primera página del PDF, dibujada. **Necesita una dependencia nueva** para dibujar PDF sin Qt (E4).
5. Si no hay ninguna, el marcador.

Con la escalera de tamaños de siempre, sin ampliar por encima del original.

## 7. Escritura

Regla del 16/11/2026: lo editado se guarda en el propio archivo, sin generar copias, con archivo temporal, comprobación y sustitución.

| Formato | Dónde va lo editado | Cómo |
|---|---|---|
| EPUB sin DRM | En el propio EPUB | Se copia el ZIP a un temporal cambiando solo el OPF; se comprueba que se lee y que **todas las demás entradas son idénticas** (mismo contenido); se sustituye. El archivo `mimetype` debe seguir siendo el primero y sin comprimir |
| PDF | En el propio PDF (E5) | Con ExifTool, como el XMP de las fotos; a comprobar que Acrobat y los lectores lo ven |
| MOBI, AZW3, FB2 | `.arca.json` de la carpeta | El archivo no se toca |
| Cualquiera con DRM | `.arca.json` de la carpeta | Nunca se escribe en un libro protegido |
| `metadata.opf` de Calibre | No se escribe (E7) | Es de Calibre: escribirlo sin que Calibre lo sepa desajusta su base de datos |

- Por la cola de siempre: editar cambia el catálogo y marca el campo como pendiente; el trabajo de `sync.py` lo escribe en segundo plano. Solo se cambia lo editado y se conserva lo que la aplicación no conoce.
- Valoración, marca, color, palabras clave y leído / no leído: en el `.arca.json`, como hoy (un solo destino por dato).
- **El escritor va antes que la edición**, como en Música: si se editara sin él, lo editado iría al `.arca.json` y habría que migrarlo.

## 8. Interfaz

- **Toolbar**: un botón más, «Libros», con su icono.
- **Barra izquierda**: «Biblioteca - Libros» (todos, «No leídos», «Selección rápida»), «Carpetas», «Autores» (autor ▸ serie), «Series», «Materias», «Idiomas» y «Años». Dadas de alta en `section_registry.py`.
- **Centro**: la cuadrícula de portadas y la vista de lista (`GEN 18`). Doble clic abre el libro con el programa del sistema (E8).
- **Inspector**: sección «Libro» (título, autor, serie, editorial, idioma, año, ISBN, materias, páginas, formato, protegido; la sinopsis, plegable), primero de solo lectura; después, editable, también con varios libros («Varios»).
- **Orden, filtros y colecciones inteligentes** (grupo «Libros electrónicos»): autor, título, serie y número, año, editorial, idioma, formato, leído, protegido.

## 9. Riesgos

1. **Escribir en un EPUB**: un ZIP mal reescrito es un libro que no abre. Por eso el escritor se hace sin interfaz, con copias, comprobando entrada por entrada y abriendo el resultado en Calibre, en un lector de escritorio y en un lector de tinta electrónica.
2. **DRM**: hay que detectarlo bien; ante la duda, no escribir.
3. **Metadatos pobres**: los PDF y muchos libros descargados traen datos vacíos o falsos. El módulo debe ser cómodo para corregirlos a mano y por lotes (nombre del archivo → título y autor), y de ahí la descarga por ISBN.
4. **Dependencia nueva para la portada de los PDF** (E4); la instala el autor.
5. **Sin archivos de prueba**: no hay libros en el catálogo. Antes de `EBK 2` hace falta una carpeta de prueba con EPUB, PDF y algún libro de Kindle, mejor si parte viene de Calibre.

---

# Parte II — Planificación

Cada paso deja la aplicación funcionando. Hasta `EBK 6` no se escribe en ningún libro; hasta `EBK 10` no hace falta internet.

### Fase EBK 1 — El módulo

| Paso | Objetivo | Aceptación |
|---|---|---|
| **EBK 1.1** Botón y módulo | `EbookModule` sobre `LibraryModule` (biblioteca, carpetas y fechas), el botón en la toolbar (`main_window.ui`) y el icono registrado | El módulo lista los libros catalogados, con el marcador; los demás módulos, igual |
| **EBK 1.2** Formatos | Los que se catalogan (E1, E2): añadir `.azw` y, si se decide, `.pdf` solo en carpetas declaradas de libros | Una carpeta de libros con PDF los cataloga; una carpeta automática, no |

### Fase EBK 2 — Leer los metadatos

| Paso | Objetivo | Aceptación |
|---|---|---|
| **EBK 2.1** Lector de OPF y de EPUB | `core/ebooks/`: campos, portada y DRM, sin BD | Autoprueba con un EPUB generado; `inspect_cli` con libros reales, comparado con Calibre |
| **EBK 2.2** Tabla de detalles | `ebook_details` (una migración) | Un catálogo existente pasa solo al esquema nuevo |
| **EBK 2.3** Extractor, con EPUB | `EbookExtractor` y `EBOOK_FIELDS_VERSION` | Al abrir el catálogo, los EPUB se leen solos |
| **EBK 2.4** `metadata.opf` de Calibre | Si está junto al libro, manda | Una carpeta de Calibre sale con los datos de Calibre |
| **EBK 2.5** PDF y Kindle | Con ExifTool; se comprueba qué da con archivos reales | Título, autor y páginas de un PDF; título y autor de un MOBI |

### Fase EBK 3 — Verlos

- **EBK 3.1** Sección «Libro» del inspector, de solo lectura.
- **EBK 3.2** Orden propio: autor, título, serie y número, año.
- **EBK 3.3** Campos del grupo «Libros electrónicos» en filtros y colecciones inteligentes.

### Fase EBK 4 — Portadas como miniatura

- **EBK 4.1** La portada del EPUB y el `cover.jpg` de Calibre.
- **EBK 4.2** La de MOBI / AZW3 (a comprobar).
- **EBK 4.3** La primera página del PDF (con la dependencia de E4).

### Fase EBK 5 — Navegar

- **EBK 5.1** «Autores» (autor ▸ serie) y «Series».
- **EBK 5.2** «Materias», «Idiomas» y «Años».
- **EBK 5.3** La vista de lista (`GEN 18`) y las listas que se recorren con las flechas (lo de `MUS 4.3`).

### Fase EBK 6 — Leído / no leído y abrir

- **EBK 6.1** Leído / no leído: menú, atajo, filtro en «Atributos», «No leídos» en la barra; en el `.arca.json`.
- **EBK 6.2** Abrir el libro con el programa del sistema.

### Fase EBK 7 — Escribir en los archivos

Sin interfaz: se prueba con copias. El escritor es una clase de `core/userdata/writers.py` (`GEN 14`, hecho el 16/11/2026): se registra sin tocar `sync.py`, y lo que no sabe guardar va solo al `.arca.json`.

- **EBK 7.1** Escritor de EPUB (el OPF dentro del ZIP), con las comprobaciones de §7.
- **EBK 7.2** En la cola de escritura: los campos en `editable_fields.py` y el escritor en `sync.py`; lo que no sabe guardar, y los libros con DRM, al `.arca.json`.
- **EBK 7.3** PDF con ExifTool (si se decide, E5).

### Fase EBK 8 — Editar

- **EBK 8.1** Edición en la sección «Libro», de un libro y de varios.
- **EBK 8.2** Cambiar la portada de un EPUB (arrastrar, «Elegir…», pegar).
- **EBK 8.3** Por lotes, en una ventana: nombre del archivo → título y autor, con un patrón; mayúsculas y minúsculas; buscar y reemplazar.

### Fase EBK 9 — Un libro, varios formatos

Una tarjeta por libro cuando hay varios archivos del mismo (EPUB, MOBI, PDF): mismo nombre en la misma carpeta, o la carpeta de Calibre. Con la tarjeta agrupada común (`GEN 17`), la misma de Vídeo.

### Fase EBK 10 — Internet

Datos y portada por ISBN, o por título y autor, de un servicio abierto (E9). Lo descargado entra como una edición más: misma cola, misma marca de pendiente, mismo escritor.

### Fase EBK 11 — Extras (sin orden)

Cómics (CBZ y CBR, con `ComicInfo.xml`); FB2 completo; exportar un `metadata.opf` para Calibre.

### Decisiones

Aceptadas por el autor el 16/11/2026 **como punto de partida**: valen mientras los archivos reales no digan otra cosa, y cada una se confirma en su paso.

| | Para | Qué | Punto de partida acordado |
|---|---|---|---|
| **E1** | `EBK 1.2` | ¿Los PDF son libros? | Sí, pero **solo en carpetas declaradas de libros**: en una carpeta automática un PDF puede ser una factura o un manual, y no debe entrar solo |
| **E2** | `EBK 1.2` | ¿Cómics (CBZ, CBR)? | No en la primera versión (`EBK 11`); si interesan, como un tipo más |
| **E3** | `EBK 2.5` | Kindle (MOBI, AZW3): hasta dónde | Leer metadatos y portada; no escribir |
| **E4** | `EBK 4.3` | Biblioteca para dibujar la primera página de un PDF | Una pequeña y de licencia permisiva (candidata: `pypdfium2`; a comprobar al llegar); la alternativa, dejar los PDF con el marcador |
| **E5** | `EBK 7.3` | Lo editado en un PDF: en el archivo o en el `.arca.json` | En el archivo, con ExifTool, si la prueba con lectores reales sale bien; si no, `.arca.json` |
| **E6** | `EBK 2.2` | Las materias (géneros): texto o tablas propias; ¿se convierten en palabras clave? | Texto de partida, como las listas de Música; no mezclarlas con las palabras clave del usuario |
| **E7** | `EBK 2.4` | Carpetas de Calibre: ¿leer su `metadata.opf`? ¿escribirlo? | Leerlo, sí; escribirlo, no |
| **E8** | `EBK 6.2` | Abrir un libro | Con el programa del sistema; un lector propio, no previsto |
| **E9** | `EBK 10` | El servicio web | Open Library (abierto, sin clave) y, si no basta, otro; como proveedor intercambiable, comprobando sus condiciones al llegar |
| **E10** | Cada paso | Los textos («Libros», «Libro», «Leído», «Materias», «Protegido») | Se proponen en cada paso |
