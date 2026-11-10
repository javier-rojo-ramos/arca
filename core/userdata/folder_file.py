"""El archivo de carpeta: datos del usuario de los archivos que no admiten XMP.

Este módulo NO depende de Qt ni de la base de datos: es Python puro.

Para los formatos cuyo destino es FOLDER_FILE (vídeo, audio, ebooks, GPX...; ver
'policy.py'), los datos del usuario se guardan en UN archivo oculto por carpeta,
'.arca.json', con una entrada por archivo de esa carpeta. Ventajas:
    - Nunca hay un sidecar por archivo: la carpeta sigue limpia.
    - Si se mueve o copia la carpeta con el explorador, sus datos van con ella.
    - Es JSON legible: se puede revisar o reparar a mano.

Formato (versión 1):

    {
      "format": "arca/folder-data",
      "version": 1,
      "items": {
        "Película.mkv": {"rating": 4, "flag": 1, "color_label": "red",
                         "updated_at": "2026-10-26T15:30:00Z"},
        "Canción.mp3":  {"rating": 5},
        "IMG_6264.mp4": {"keywords": [["Coche", "Opel Astra"], ["Playa"]]}
      }
    }

    - 'keywords' (desde el 03/11/2026): las palabras clave ASIGNADAS, cada una con su ruta
      de la raíz a la palabra (como 'lr:hierarchicalSubject', pero como lista). Sin
      palabras, no se escribe. Una versión anterior de la aplicación que no la conozca la
      conserva igual que cualquier clave desconocida.

    - Metadatos descriptivos editados en la aplicación (desde el 10/11/2026; las claves de
      'EDITABLE_FIELDS' en 'editable_fields.py': "title", "description", "city"...): la
      clave solo está si el campo se ha EDITADO, y entonces su valor manda siempre sobre
      lo que traiga el archivo (que la aplicación no modifica). "" = vaciado a propósito.

    - Las claves de 'items' son el NOMBRE del archivo (sin carpeta), tal como está en
      disco. En Windows y macOS (que no distinguen mayúsculas), si no hay coincidencia
      exacta se prueba sin distinguirlas; en Linux, 'A.mp4' y 'a.mp4' son dos archivos.
    - En cada entrada solo se guardan los valores distintos del valor por defecto
      (rating 0, flag 0, color_label nulo): un archivo sin datos no tiene entrada.
    - Las claves que esta versión no conoce (de una versión futura de la aplicación,
      o añadidas a mano) se CONSERVAN al reescribir: nunca se pierde lo que no se
      entiende.

Seguridad al escribir ('write_folder_file'):
    1. Se escribe un temporal en la misma carpeta y se fuerza al disco (fsync).
    2. El archivo anterior pasa a ser la copia '.arca.json.bak'.
    3. El temporal pasa a ser '.arca.json' (os.replace: atómico).
    Si la aplicación se corta a mitad, queda el archivo bueno o, como mucho, solo la
    copia: 'read_folder_file' usa la copia si el archivo principal falta o está dañado.
    Los tres archivos empiezan por punto (el escáner los ignora) y en Windows se marcan
    además como ocultos.

1.3.0 'edited_values_from_entry': lee los metadatos descriptivos editados de una entrada.

Prueba rápida (desde la raíz del proyecto):
    python -m core.userdata.folder_file
"""

__version__ = "1.3.0"
__all__ = [
    "BACKUP_FILE_NAME",
    "FOLDER_FILE_NAME",
    "USER_DEFAULTS",
    "FolderData",
    "FolderFileError",
    "KEYWORDS_KEY",
    "edited_values_from_entry",
    "find_entry_key",
    "keywords_from_entry",
    "merge_entry",
    "read_folder_file",
    "user_values_from_entry",
    "write_folder_file",
]

# Librerías estándar
import contextlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.color_labels import is_valid_color_label
from core.userdata.editable_fields import EDITABLE_FIELDS, normalize_value

# Nombres de los archivos (empiezan por punto: ocultos en macOS y Linux, y el escáner
# de carpetas los ignora)
FOLDER_FILE_NAME = ".arca.json"
BACKUP_FILE_NAME = ".arca.json.bak"
_TEMP_FILE_NAME = ".arca.json.tmp"

# Identificación del formato y versión que escribe esta aplicación. Hasta el 05/11/2026
# era "emc-manager/folder-data" (en '.emc.json'); esos archivos ya no se leen: el
# nombre cambió antes de usar la aplicación en producción.
_FORMAT_ID = "arca/folder-data"
_FORMAT_VERSION = 1

# Valores por defecto de los datos del usuario (los de la base de datos). Un valor por
# defecto no se escribe en el archivo.
USER_DEFAULTS: dict[str, Any] = {"rating": 0, "flag": 0, "color_label": None}

# Clave de las palabras clave de una entrada (lista de rutas; ver la cabecera)
KEYWORDS_KEY = "keywords"

# Atributo "oculto" de Windows (FILE_ATTRIBUTE_HIDDEN)
_WINDOWS_HIDDEN = 0x2


class FolderFileError(Exception):
    """No se pudo leer o escribir el archivo de carpeta (mensaje para el registro)."""


@dataclass(slots=True)
class FolderData:
    """Contenido del archivo de carpeta de un directorio.

    Attributes:
        directory: Carpeta a la que pertenece.
        items: Nombre de archivo -> entrada (diccionario con sus datos).
        extra: Claves de primer nivel que no son 'format', 'version' ni 'items' (se
            conservan al reescribir).
        version: Versión del formato que tenía el archivo leído (o la actual si no
            existía). Nunca se rebaja al reescribir.
        source: De dónde salió: 'file' (el archivo), 'backup' (la copia, porque el
            principal faltaba o estaba dañado) o 'none' (no había ninguno).
    """

    directory: Path
    items: dict[str, dict[str, Any]] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    version: int = _FORMAT_VERSION
    source: str = "none"

    @property
    def exists(self) -> bool:
        """True si había archivo (o copia) en disco."""
        return self.source != "none"


# -----------------------------------------------------------------------------
# Lectura
# -----------------------------------------------------------------------------


def read_folder_file(directory: str | Path) -> FolderData:
    """Lee el archivo de carpeta de un directorio.

    Args:
        directory: Carpeta.

    Returns:
        Su contenido. Si no hay archivo ni copia, un 'FolderData' vacío con
        source = 'none' (la carpeta no tiene datos: NO es un error).

    Raises:
        FolderFileError: Si existe pero no se puede leer (permisos, unidad
            desconectada...) o está dañado y la copia tampoco sirve. Quien llama NO
            debe tratar esto como "sin datos": no sabe lo que hay.
    """
    folder = Path(directory)
    main = folder / FOLDER_FILE_NAME
    backup = folder / BACKUP_FILE_NAME

    main_error: str | None = None
    try:
        return _parse(folder, main.read_bytes(), "file")
    except FileNotFoundError:
        main_error = None  # no hay archivo principal: se mira la copia
    except OSError as exc:
        # Existe pero no se puede leer: no se sabe qué contiene
        raise FolderFileError(f"No se pudo leer {main}: {exc}") from exc
    except ValueError as exc:
        main_error = str(exc)
        logger.warning(f"Archivo de carpeta dañado ({main}): {exc}. Se usa la copia.")

    try:
        data = _parse(folder, backup.read_bytes(), "backup")
    except FileNotFoundError:
        if main_error is None:
            return FolderData(folder)  # ni archivo ni copia: carpeta sin datos
        raise FolderFileError(f"{main} está dañado y no hay copia: {main_error}") from None
    except OSError as exc:
        raise FolderFileError(f"No se pudo leer {backup}: {exc}") from exc
    except ValueError as exc:
        raise FolderFileError(
            f"{main} y su copia están dañados: {main_error or 'falta'} / {exc}"
        ) from exc

    if main_error is None:
        # Faltaba el principal pero estaba la copia: la escritura se cortó entre los
        # dos cambios de nombre. La copia es la última versión buena.
        logger.warning(f"Falta {main}; se usa su copia {backup.name}")
    return data


def _parse(folder: Path, raw: bytes, source: str) -> FolderData:
    """Convierte el contenido de un archivo en 'FolderData'. ValueError si no es válido."""
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"no es JSON válido ({exc})") from exc
    if not isinstance(document, dict):
        raise ValueError("no contiene un objeto JSON")
    if document.get("format") != _FORMAT_ID:
        raise ValueError(f"formato desconocido: {document.get('format')!r}")
    items = document.get("items", {})
    if not isinstance(items, dict):
        raise ValueError("'items' no es un objeto")

    version = document.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        version = _FORMAT_VERSION
    if version > _FORMAT_VERSION:
        logger.info(
            f"{folder / FOLDER_FILE_NAME} es de una versión más nueva ({version}); se leen "
            "los campos conocidos y se conserva el resto."
        )

    # Las entradas que no son objetos se descartan (no pueden venir de la aplicación)
    clean_items = {
        str(name): dict(entry) for name, entry in items.items() if isinstance(entry, dict)
    }
    extra = {k: v for k, v in document.items() if k not in ("format", "version", "items")}
    return FolderData(folder, clean_items, extra, version, source)


def find_entry_key(
    items: dict[str, dict[str, Any]], file_name: str, *, case_sensitive: bool | None = None
) -> str | None:
    """Clave de 'items' que corresponde a un archivo, o None si no tiene entrada.

    Primero se busca el nombre exacto. Si no está y el sistema no distingue mayúsculas
    (Windows y macOS, donde 'IMG.MP4' e 'img.mp4' son el mismo archivo), se busca sin
    distinguirlas. En Linux sí se distinguen: allí son dos archivos distintos.

    Args:
        items: Entradas del archivo de carpeta.
        file_name: Nombre del archivo en disco.
        case_sensitive: Forzar el criterio (para pruebas); None = el del sistema.
    """
    if file_name in items:
        return file_name
    if case_sensitive is None:
        case_sensitive = sys.platform not in ("win32", "darwin")
    if case_sensitive:
        return None
    folded = file_name.casefold()
    for key in items:
        if key.casefold() == folded:
            return key
    return None


def user_values_from_entry(entry: dict[str, Any] | None) -> dict[str, Any]:
    """Valores de rating, flag y color_label de una entrada, ya validados.

    Lo que falta, o no es válido (el archivo se puede editar a mano), vale el valor por
    defecto. Así el resultado siempre se puede guardar tal cual en la base de datos.
    """
    values = dict(USER_DEFAULTS)
    if not entry:
        return values

    rating = entry.get("rating")
    if isinstance(rating, int) and not isinstance(rating, bool) and 0 <= rating <= 5:
        values["rating"] = rating
    flag = entry.get("flag")
    if isinstance(flag, int) and not isinstance(flag, bool) and flag in (-1, 0, 1):
        values["flag"] = flag
    color = entry.get("color_label")
    if is_valid_color_label(color):
        values["color_label"] = color
    return values


def keywords_from_entry(entry: dict[str, Any] | None) -> tuple[tuple[str, ...], ...]:
    """Palabras clave de una entrada, como rutas ya validadas (vacío si no tiene).

    Lo que no es una lista de rutas de textos no vacíos (editado a mano) se ignora.
    """
    raw = (entry or {}).get(KEYWORDS_KEY)
    if not isinstance(raw, list):
        return ()
    paths: list[tuple[str, ...]] = []
    for path in raw:
        if isinstance(path, list) and path and all(isinstance(n, str) and n.strip() for n in path):
            paths.append(tuple(name.strip() for name in path))
    return tuple(paths)


def edited_values_from_entry(entry: dict[str, Any] | None) -> dict[str, str | None]:
    """Metadatos descriptivos editados de una entrada: columna -> valor ya limpio.

    Solo los campos cuya clave está (los que se editaron en la aplicación); "" o null
    = vaciado a propósito (None). Un valor que no es texto (editado a mano) se ignora,
    como si la clave no estuviera.
    """
    if not entry:
        return {}
    values: dict[str, str | None] = {}
    for spec in EDITABLE_FIELDS:
        if spec.folder_key not in entry:
            continue
        try:
            values[spec.column] = normalize_value(spec.column, entry[spec.folder_key])
        except TypeError:
            logger.debug(f"Valor no válido en '{spec.folder_key}': {entry[spec.folder_key]!r}")
    return values


def merge_entry(
    entry: dict[str, Any] | None, values: dict[str, Any], *, now: str | None = None
) -> dict[str, Any] | None:
    """Entrada nueva de un archivo a partir de la anterior y de sus valores actuales.

    Conserva las claves desconocidas de la entrada anterior. Los valores por defecto no
    se escriben (se quitan si estaban).

    Args:
        entry: Entrada anterior (o None si no tenía).
        values: rating, flag y color_label actuales (los de la base de datos) y, si se
            quieren escribir, 'keywords' (rutas). Sin 'keywords', las que tuviera la
            entrada se conservan tal cual.
        now: Marca de tiempo ISO 8601 UTC (por defecto, la hora actual).

    Returns:
        La entrada nueva, o None si ya no hay nada que guardar (se borra la entrada).
    """
    # Se parte de las claves que no son de esta función (desconocidas o futuras)
    replaced = set(USER_DEFAULTS) | {"updated_at"} | ({KEYWORDS_KEY} if KEYWORDS_KEY in values else set())
    merged = {k: v for k, v in (entry or {}).items() if k not in replaced}
    for key, default in USER_DEFAULTS.items():
        value = values.get(key, default)
        if value != default:
            merged[key] = value
    if values.get(KEYWORDS_KEY):
        merged[KEYWORDS_KEY] = [list(path) for path in values[KEYWORDS_KEY]]

    if not merged:
        return None
    merged["updated_at"] = now or _utc_now()  # cuándo la escribió la aplicación por última vez
    return merged


def _utc_now() -> str:
    """Hora actual en ISO 8601 UTC, sin decimales ('2026-10-26T15:30:00Z')."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# -----------------------------------------------------------------------------
# Escritura
# -----------------------------------------------------------------------------


def write_folder_file(data: FolderData) -> bool:
    """Guarda el archivo de carpeta de forma atómica, dejando la versión anterior como copia.

    Si ya no queda nada que guardar (ninguna entrada ni clave desconocida), se borran el
    archivo y su copia: la carpeta queda como estaba.

    Args:
        data: Contenido completo a guardar (normalmente, lo leído con
            'read_folder_file' y modificado).

    Returns:
        True si el archivo queda en disco; False si se ha borrado (estaba vacío).

    Raises:
        FolderFileError: Si no se pudo escribir (el archivo anterior sigue intacto).
    """
    folder = data.directory
    main = folder / FOLDER_FILE_NAME
    backup = folder / BACKUP_FILE_NAME
    temp = folder / _TEMP_FILE_NAME

    if not data.items and not data.extra:
        try:
            main.unlink(missing_ok=True)
            backup.unlink(missing_ok=True)
        except OSError as exc:
            raise FolderFileError(f"No se pudo borrar {main}: {exc}") from exc
        return False

    document = {
        "format": _FORMAT_ID,
        "version": max(data.version, _FORMAT_VERSION),
        **data.extra,
        "items": {name: data.items[name] for name in sorted(data.items, key=str.casefold)},
    }
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"

    try:
        # 1. Temporal en la misma carpeta (así os.replace no cruza unidades) y al disco
        with open(temp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        # 2. El archivo anterior pasa a ser la copia (se borra antes la copia vieja: en
        #    Windows, sustituir un archivo oculto puede fallar)
        if main.exists():
            backup.unlink(missing_ok=True)
            os.replace(main, backup)
            _hide(backup)

        # 3. El temporal pasa a ser el archivo bueno
        os.replace(temp, main)
        _hide(main)
    except OSError as exc:
        with contextlib.suppress(OSError):
            temp.unlink(missing_ok=True)
        raise FolderFileError(f"No se pudo escribir {main}: {exc}") from exc
    return True


def _hide(path: Path) -> None:
    """En Windows, marca un archivo como oculto (en macOS y Linux ya lo es por el punto)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        attributes = kernel32.GetFileAttributesW(str(path))
        if attributes != -1 and not attributes & _WINDOWS_HIDDEN:
            kernel32.SetFileAttributesW(str(path), attributes | _WINDOWS_HIDDEN)
    except Exception as exc:  # noqa: BLE001 - ocultarlo es cosmético: nunca debe fallar
        logger.debug(f"No se pudo ocultar {path}: {exc}")


if __name__ == "__main__":
    # Autoprueba en una carpeta temporal.
    # Ejecutar desde la raíz del proyecto:  python -m core.userdata.folder_file
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)

        # 1. Carpeta sin archivo: sin datos y sin error
        empty = read_folder_file(folder)
        assert empty.items == {} and empty.source == "none" and not empty.exists

        # 2. Escribir, leer y conservar claves desconocidas
        data = FolderData(folder, extra={"future": {"x": 1}})
        data.items["Peli.mkv"] = merge_entry(
            None, {"rating": 4, "flag": 1, "color_label": "red"}, now="T1"
        )
        data.items["Canción.mp3"] = {"rating": 5, "lyrics_checked": True}
        assert write_folder_file(data)
        again = read_folder_file(folder)
        assert again.source == "file" and again.extra == {"future": {"x": 1}}
        assert again.items["Peli.mkv"] == {
            "rating": 4, "flag": 1, "color_label": "red", "updated_at": "T1"
        }  # fmt: skip
        assert user_values_from_entry(again.items["Canción.mp3"]) == {
            "rating": 5, "flag": 0, "color_label": None
        }  # fmt: skip
        assert not (folder / BACKUP_FILE_NAME).exists()  # primera escritura: no hay copia

        # 3. Segunda escritura: la anterior queda como copia
        again.items["Peli.mkv"] = merge_entry(
            again.items["Peli.mkv"], {"rating": 2, "flag": 0, "color_label": None}, now="T2"
        )
        assert again.items["Peli.mkv"] == {"rating": 2, "updated_at": "T2"}
        write_folder_file(again)
        assert (folder / BACKUP_FILE_NAME).exists()
        assert read_folder_file(folder).items["Peli.mkv"]["rating"] == 2

        # 4. Quitar todos los datos de un archivo: desaparece su entrada, pero la clave
        #    desconocida de la otra entrada se conserva
        assert merge_entry({"rating": 3, "updated_at": "x"}, dict(USER_DEFAULTS)) is None
        kept = merge_entry({"rating": 3, "lyrics_checked": True}, dict(USER_DEFAULTS), now="T3")
        assert kept == {"lyrics_checked": True, "updated_at": "T3"}

        # 4b. Metadatos editados: solo las claves que están; "" y null = vaciado; lo que
        #     no es texto se ignora. 'merge_entry' los conserva al reescribir lo demás
        #     (va antes del 5, que en Windows falla: sobrescribe un archivo oculto)
        edited = {"title": " Atardecer ", "description": "", "city": None, "country": 34,
                  "region": "Línea 1\r\nLínea 2", "rating": 2}  # fmt: skip
        assert edited_values_from_entry(edited) == {
            "title": "Atardecer", "description": None, "region": "Línea 1 Línea 2", "city": None,
        }  # fmt: skip
        assert edited_values_from_entry({"rating": 2}) == {}
        assert edited_values_from_entry(None) == {}
        assert merge_entry(edited, {"rating": 4}, now="T")["title"] == " Atardecer "
        print("Metadatos editados: leídos de la entrada")

        # 5. Archivo principal dañado: se usa la copia
        (folder / FOLDER_FILE_NAME).write_text("{ esto no es json", encoding="utf-8")
        recovered = read_folder_file(folder)
        assert recovered.source == "backup" and recovered.items["Peli.mkv"]["rating"] == 4

        # 6. Falta el principal (corte entre los dos cambios de nombre): se usa la copia
        (folder / FOLDER_FILE_NAME).unlink()
        assert read_folder_file(folder).source == "backup"

        # 7. Los dos dañados: error (no "sin datos")
        (folder / FOLDER_FILE_NAME).write_text("[]", encoding="utf-8")
        (folder / BACKUP_FILE_NAME).write_text("nope", encoding="utf-8")
        try:
            read_folder_file(folder)
        except FolderFileError as error:
            print("Ambos dañados ->", error)
        else:
            raise AssertionError("debería fallar")

        # 8. Búsqueda sin distinguir mayúsculas y valores no válidos (editados a mano)
        items = {"VIDEO.MP4": {"rating": 9, "flag": True, "color_label": "orange"}}
        assert find_entry_key(items, "video.mp4", case_sensitive=False) == "VIDEO.MP4"
        assert find_entry_key(items, "video.mp4", case_sensitive=True) is None
        assert find_entry_key(items, "otro.mp4", case_sensitive=False) is None
        assert user_values_from_entry(items["VIDEO.MP4"]) == USER_DEFAULTS

        # Palabras clave: se escriben como rutas; sin 'keywords' en los valores se conservan
        tagged = merge_entry({"rating": 2}, {"rating": 2, "keywords": (("Coche", "Opel Astra"),)}, now="T")
        assert tagged == {"rating": 2, "keywords": [["Coche", "Opel Astra"]], "updated_at": "T"}, tagged
        assert keywords_from_entry(tagged) == (("Coche", "Opel Astra"),)
        assert merge_entry(tagged, {"rating": 3}, now="T")["keywords"] == [["Coche", "Opel Astra"]]
        assert merge_entry(tagged, {"rating": 0, "keywords": ()}, now="T") is None  # nada que guardar
        assert keywords_from_entry({"keywords": [["ok"], "mal", [], [""], [1]]}) == (("ok",),)

        # 9. Nada que guardar: se borran el archivo y la copia
        assert write_folder_file(FolderData(folder)) is False
        assert not (folder / FOLDER_FILE_NAME).exists()
        assert not (folder / BACKUP_FILE_NAME).exists()
        assert not (folder / _TEMP_FILE_NAME).exists()

        # 10. Una versión futura del formato no se rebaja al reescribir
        future = {"format": _FORMAT_ID, "version": 7, "items": {"a.mp3": {"rating": 1}}}
        (folder / FOLDER_FILE_NAME).write_text(json.dumps(future), encoding="utf-8")
        loaded = read_folder_file(folder)
        assert loaded.version == 7
        write_folder_file(loaded)
        assert json.loads((folder / FOLDER_FILE_NAME).read_text("utf-8"))["version"] == 7

    print("Autoprueba finalizada correctamente.")
