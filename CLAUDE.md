# CLAUDE.md — Arca Media

Catalogador multimedia (tipo DAM) de escritorio, multiplataforma: Python 3.14 + PySide6 (vía `qtpy`), SQLite y ExifTool. Lo desarrolla una sola persona, para uso interno de su empresa, a largo plazo. Se trabaja sobre todo en **Windows**.

Este archivo dice **cómo trabajar** en el proyecto. **Qué es y en qué punto está** se cuenta en `docs/INDEX.md`, que se carga aquí mismo con cada sesión (es corto):

@docs/INDEX.md

## Cómo leer el proyecto (sin leerlo entero)

1. Al empezar una sesión, lee [docs/ESTADO.md](docs/ESTADO.md) (qué falta por verificar y los últimos cambios) y, si vas a seguir el plan, [docs/PENDIENTE.md](docs/PENDIENTE.md). `INDEX.md` ya está cargado.
2. Lee **solo** el documento del tema que vas a tocar (la tabla de `INDEX.md` dice cuál) y, si existe, el `LEEME.md` de su carpeta (`core/metadata/`, `core/thumbnails/`, `core/userdata/`).
3. Para saber **dónde** está algo: el mapa de [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) y la tabla de [docs/COMO_AMPLIAR.md](docs/COMO_AMPLIAR.md). Después, busca (`grep`) el nombre concreto en lugar de abrir carpetas enteras.
4. Cada `.py` explica en su **cabecera** qué hace, cómo se usa y su historial: léela antes que el resto del archivo.
5. Archivos grandes: abre solo los métodos que necesites. Los más grandes son `controllers/main_window_controller.py` (~1 900 líneas), `ui_helpers/sidebars/catalog_sidebar.py` (~1 200), `core/catalog/keywords.py` (~1 200), `core/userdata/sync.py` (~1 250) y `core/metadata/processor.py` (~1 080).
6. **No leas** `ui/main_window.py`: se genera desde `ui/main_window.ui` con `build_ui.py`. Para el nombre de un widget, búscalo con `grep`.
7. Si el código y la documentación no coinciden, **manda el código**: corrige la documentación y avisa.

## Cómo trabajar

- **Paso a paso**: haz cambios pequeños y comprobables, uno cada vez. Si un cambio toca varios archivos o hay que decidir algo, explica antes el plan y espera el visto bueno. No mezcles una refactorización con una funcionalidad nueva.
- **Edita solo lo afectado**: cambia el método o la sección que haga falta. No reescribas archivos enteros ni reordenes código que no tiene que ver con el cambio.
- **Pregunta antes de decidir** lo que es del autor: comportamiento visible, textos de la interfaz, qué se guarda en los archivos del usuario y qué se borra.
- **Git**: no hagas commits ni `push` salvo que te lo pida el autor. Antes de un cambio que toque varios archivos, recuérdale que haga un commit, para poder deshacerlo.
- **No borres ni muevas archivos** del proyecto sin preguntar.
- **Si algo falla y no es por tu cambio** (una autoprueba que ya fallaba, un aviso de ruff antiguo), dilo, pero no lo arregles de paso.
- **Al terminar**: resume qué has cambiado y qué tiene que comprobar el autor en la aplicación. La interfaz no tiene pruebas automáticas.

## Convenciones del código

- **Idioma**: nombres (variables, constantes, funciones, clases) en **inglés**; **docstrings y comentarios en español**, como el resto del proyecto. Textos de la interfaz en español. En el chat, en español. Excepción: `main.py` y `controllers/main_window_controller.py` conservan nombres antiguos en español (`iniciar`, `_conectar_senales`, `mosaico_model`...); no los renombres de paso (se hará más adelante), pero lo nuevo va en inglés.
- **Comentarios**: código bien comentado. Explica el **porqué** y lo que no es evidente, no lo que ya dice el código.
- **Estilo**: PEP 8, comprobado con **ruff** (`ruff check <archivos tocados>`; configuración en `ruff.toml`). Líneas de hasta unos 100 caracteres, como el resto del código (es una costumbre: ruff no comprueba la longitud).
- **Tipado**: *type hints* en todas las firmas (`def update_status(self, message: str) -> None:`).
- **Cada módulo** lleva:
  - una cabecera con qué hace, cómo se usa y el historial de versiones (`1.2.0 Qué cambió.`, la más reciente arriba);
  - `__version__`: súbela al cambiar el módulo;
  - `__all__`;
  - una **autoprueba** en `if __name__ == "__main__":` que termina imprimiendo «Autoprueba finalizada correctamente.», **solo si es un módulo nuevo con lógica comprobable sin ventana**. Muchos módulos existentes no la tienen (sobre todo de interfaz): no se la añadas de paso.

  `controllers/main_window_controller.py` no tiene cabecera, `__version__` ni `__all__`: es una excepción conocida; no se los añadas de paso.
- **Importaciones** agrupadas con estos comentarios: `# Librerías estándar`, `# Librerías de terceros`, `# Librerías de terceros (Qt)`, `# Módulos del proyecto`.
- **Qt** siempre a través de `qtpy`, nunca de `PySide6` directamente (salvo el `.py` generado).

## Reglas de arquitectura (no romper)

- `core/` **no usa Qt**, salvo `core/database/db_manager.py` y `core/workers/`. Lo que necesite Qt (papelera, diálogos...) se le pasa como función desde `ui_helpers/`.
- La interfaz **nunca** accede a la base de datos ni hace trabajo largo en el hilo principal:
  - consultas: `self.db.execute_async(funcion, ...)`;
  - trabajos largos: `JobManager.start(nombre, trabajo)`.
- Toda función que accede a la base de datos recibe la **conexión (`conn`) como primer parámetro** y **no hace `commit`**. La excepción son los trabajos largos, que hacen `commit` por lotes y obedecen su `cancel_event`.
- En las respuestas asíncronas, comprueba que el catálogo sigue abierto (`if self.db is None: return`): puede haberse cerrado mientras tanto.
- **Qt y memoria**: crea cada widget o `QObject` con su `parent` correcto, o mételo en un layout que lo tenga. Usa `deleteLater()` para los que se descartan. Así se evitan fugas y cierres con *Segmentation Fault*.
- **Base de datos**:
  - las migraciones solo se **añaden al final** de `MIGRATIONS` (`core/catalog/catalog_schema.py`); nunca se edita una existente (la 1 es el esquema consolidado el 05/11/2026);
  - el esquema está en [docs/MODELO_DE_DATOS.md](docs/MODELO_DE_DATOS.md), con los bloques de columnas y quién escribe cada uno;
  - un extractor nunca escribe datos del usuario.
- **Versiones que obligan a reprocesar**: sube `IMAGE_FIELDS_VERSION` o `VIDEO_FIELDS_VERSION` si cambian los campos o sus reglas, `TRACK_EXTRACTOR_VERSION` si cambia la lectura de los GPX y `THUMBNAIL_VERSION` si cambia el resultado de las miniaturas.
- **Archivos del usuario**: los originales no se mueven ni se modifican. La única excepción es escribir valoración, marca, color, palabras clave y los metadatos descriptivos editados en la aplicación (título, pie de ilustración, creador, copyright y ubicación) con las reglas de `core/userdata/` (ver su `LEEME.md`), y la papelera cuando el usuario la pide.
- **Interfaz**: no edites `ui/main_window.py`. Cambia `ui/main_window.ui` y ejecuta `python scripts/build_ui.py` (desde la raíz). Los nombres de las bibliotecas salen siempre de `LIBRARY_NAMES`.
- **Colores**: ningún color suelto en la interfaz (ni `"#rrggbb"`, ni `QColor(r, g, b)`, ni nombres como `"white"`), salvo en las autopruebas. Salen de `ui_helpers/helpers/theme_colors.py` (por su nombre de función; en el código, `COLORS`, `CARD_COLORS` y `MARK_COLORS` de `ui_theme.py`) o de la paleta de Qt (`palette(...)` en QSS); los estilos, en `ui_theme.py`. Los botones de opción y las casillas los dibuja `theme_style.py`: el QSS no puede tener reglas `::indicator`.
- **Tamaño**: si una clase de interfaz pasa de unas **400 líneas**, propón dividirla en componentes, widgets propios o helpers. Vale para lo nuevo: no propongas dividir de paso los archivos grandes que ya existen. `main_window_controller.py` ya es demasiado grande: no le añadas lógica nueva. Ponla en su propio módulo (como `controllers/collection_actions.py` o `controllers/inspector_controller.py`) y deja en el controlador solo la conexión.

## Comandos (desde la raíz, en Windows)

- Arrancar la aplicación (solo el autor: abre una ventana): `.venv\Scripts\python.exe main.py`.
- Regenerar la interfaz tras cambiar el `.ui` o el `.qrc`: `.venv\Scripts\python.exe scripts/build_ui.py`.
- Dependencias: `requirements.txt` (UTF-8). Instalarlas o regenerar el archivo lo hace el autor; las órdenes, en [docs/PRUEBAS.md](docs/PRUEBAS.md).
- **No hay empaquetado todavía** (ni `.spec` ni script de PyInstaller: [docs/PENDIENTE.md](docs/PENDIENTE.md), C.9) **ni pruebas automáticas** aparte de las autopruebas (no existe `tests/`).

## Cómo comprobar un cambio

- **Usa siempre el Python del entorno virtual `.venv`** (es el que tiene PySide6 y el resto de dependencias), no el del sistema: en Windows, `.venv\Scripts\python.exe` (en la terminal Bash, `.venv/Scripts/python`); en macOS y Linux, `.venv/bin/python`. Ruff NO está en `.venv` (está instalado aparte): se ejecuta directamente, `ruff check ...`. Si `.venv` no existe o le falta un paquete, díselo al autor en vez de instalar nada.
- La autoprueba de cada módulo tocado, desde la raíz: `python -m paquete.modulo` (con el `python` de `.venv`). La lista completa está en [docs/PRUEBAS.md](docs/PRUEBAS.md).
- **No ejecutes nada que abra una ventana y espere**: la aplicación (`main.py`) ni las pruebas que abren ventanas (en `PRUEBAS.md`, las que dicen «una ventana», como `theme_style` y `organize_bar`, y los diálogos que se abren solos: `settings_dialog`, `folder_content_dialog`, `remove_dialog`...). Se quedan esperando a que alguien las cierre. Pásaselas al autor en la lista de comprobaciones.
- `ruff check` de los archivos tocados.
- Si una autoprueba depende de lo que haya instalado (ExifTool, `pillow-heif`), pásale un registro explícito.
- Lo que no se puede probar sin la aplicación, díselo al autor como lista de comprobaciones.

## Al terminar cada paso: actualizar la documentación

| Si... | Actualiza |
|---|---|
| Siempre | [docs/ESTADO.md](docs/ESTADO.md): la entrega en «Pendiente de verificar» y una línea en «Últimos cambios» (se guardan 10; la que sobra pasa a [docs/HISTORIAL.md](docs/HISTORIAL.md)) |
| Avanza o cambia el plan | [docs/PENDIENTE.md](docs/PENDIENTE.md) |
| El autor confirma que algo funciona | Pásalo a «Verificado» en `ESTADO.md` |
| Cambia el esquema | [docs/MODELO_DE_DATOS.md](docs/MODELO_DE_DATOS.md) y la tabla de versiones de [docs/INDEX.md](docs/INDEX.md) |
| Cambia una versión (campos, miniaturas, GPX) | La tabla de versiones de `INDEX.md` |
| Cambia cómo funciona una operación | [docs/FLUJOS.md](docs/FLUJOS.md) |
| Archivo o módulo nuevo | El mapa de [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) y, si es un punto de ampliación, [docs/COMO_AMPLIAR.md](docs/COMO_AMPLIAR.md) |
| Se decide algo de diseño | [docs/DECISIONES.md](docs/DECISIONES.md): al final, con fecha y el porqué; si sustituye a otra, borra o reescribe la antigua (solo queda lo vigente) |
| Se termina un paso de [docs/PENDIENTE.md](docs/PENDIENTE.md) | Sácalo de `PENDIENTE.md` (su detalle ya está en `HISTORIAL.md`); mientras dura, sus subpasos se pueden tachar |
| Aparece una limitación o un error fácil de cometer | [docs/TRAMPAS.md](docs/TRAMPAS.md) |
| Autoprueba o herramienta nueva | [docs/PRUEBAS.md](docs/PRUEBAS.md) |

Escribe la documentación en español, breve y concreta. Enlaza a otros documentos en vez de repetir su contenido.
