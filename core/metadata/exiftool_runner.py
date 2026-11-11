"""Lectura de metadatos con ExifTool: un único motor para EXIF, XMP, IPTC, RAW, HEIC...

Este módulo NO depende de Qt. Ejecuta el programa externo ExifTool por lotes de
archivos y devuelve, para cada uno, un diccionario con sus etiquetas. No decide
qué etiqueta va a qué columna de la base de datos: eso lo hará el extractor.

Por qué ExifTool: lee con la misma herramienta los EXIF, IPTC y XMP (incrustados o
en un archivo .xmp aparte) de todos los formatos (JPEG, PNG, WebP, HEIC y los RAW de
Canon, Nikon, Sony, Fujifilm, Adobe DNG...) y, más adelante, también de vídeo y
audio. Además es la herramienta que sabe ESCRIBIR XMP/IPTC, necesario para editar
los campos de Lightroom.

Cómo se invoca (una llamada por lote, no una por archivo: arrancar ExifTool tarda
unos cientos de milisegundos y miles de llamadas serían lentas):

    exiftool -j -n -G1 -a -charset utf8 -charset filename=utf8 [etiquetas] -@ lista.txt

    -j       salida en JSON.
    -n       valores "en bruto" (números, no textos): 0.0285714 en vez de "1/35",
             códigos EXIF en vez de "Matricial". Más fáciles de guardar y filtrar.
    -G1      cada etiqueta lleva el grupo delante ("IFD0:Make", "XMP-photoshop:City"),
             para poder elegir de dónde se toma cada dato.
    -a       permite etiquetas repetidas en grupos distintos (EXIF y XMP, por ejemplo).
    -charset textos y nombres de archivo en UTF-8 (imprescindible para rutas con
             acentos en Windows). La lista de archivos se pasa por un archivo temporal
             ('-@') porque la línea de comandos de Windows tiene un límite de longitud.

Dónde busca el programa ExifTool ('find_exiftool'), por orden:
    1. La variable de entorno EXIFTOOL_PATH.
    2. La carpeta 'tools/exiftool' del proyecto (o de la aplicación empaquetada).
    3. El PATH del sistema.

Prueba rápida (usa un ExifTool simulado, no necesita tener ExifTool instalado):
    python -m core.metadata.exiftool_runner
"""

__version__ = "1.1.0"
__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_SEARCH_DIRS",
    "ExifToolError",
    "ExifToolFileError",
    "ExifToolLaunchError",
    "ExifToolNotFoundError",
    "ExifToolRunner",
    "FileMetadata",
    "find_exiftool",
    "find_sidecars",
]

# Librerías estándar
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Archivos por llamada a ExifTool
DEFAULT_BATCH_SIZE = 100

# Carpeta donde se espera encontrar ExifTool dentro del proyecto. Al empaquetar con
# PyInstaller, 'tools/exiftool' se incluye como datos y queda en la misma posición
# relativa, así que esta ruta sigue valiendo.
DEFAULT_SEARCH_DIRS: tuple[Path, ...] = (
    Path(__file__).resolve().parents[2] / "tools" / "exiftool",
)

# Segundos máximos que se espera a ExifTool en cada llamada
DEFAULT_TIMEOUT_SECONDS = 120.0

# Opciones fijas de cada llamada (ver la explicación en la cabecera del módulo)
_BASE_ARGS: tuple[str, ...] = (
    "-j",
    "-n",
    "-G1",
    "-a",
    "-charset",
    "utf8",
    "-charset",
    "filename=utf8",
)

# En Windows, evita que aparezca una ventana de consola en cada llamada
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ExifToolError(Exception):
    """ExifTool falló o devolvió algo que no se puede interpretar."""


class ExifToolNotFoundError(ExifToolError):
    """No se encontró el programa ExifTool (mensaje listo para mostrar al usuario)."""


class ExifToolLaunchError(ExifToolError):
    """ExifTool no se puede ejecutar en absoluto (falta un componente, sin permisos...).

    Es un fallo GENERAL: no tiene sentido seguir intentándolo con otros archivos.
    """


class ExifToolFileError(ExifToolError):
    """ExifTool falló al leer un lote (tiempo agotado, caída, salida ilegible).

    Es un fallo que puede deberse a UN archivo concreto del lote: quien llame puede
    reintentar por partes para aislar al culpable.
    """


@dataclass(frozen=True, slots=True)
class FileMetadata:
    """Las etiquetas que ExifTool ha leído de un archivo.

    Attributes:
        path: Ruta del archivo, tal como se pidió.
        tags: Etiquetas con su grupo delante ("IFD0:Make", "XMP-dc:Title").
        error: Mensaje de ExifTool si no pudo leer el archivo; si no, None.
    """

    path: Path
    tags: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def find(self, name: str, groups: Sequence[str] = ()) -> Any | None:
        """Busca una etiqueta por su nombre, sin importar el grupo.

        Si hay varias (p. ej. 'City' en IPTC y en XMP), se devuelve la del primer
        grupo de 'groups' que la tenga; si ninguno la tiene, la de cualquier otro
        grupo. Un valor vacío cuenta como ausente.

        Args:
            name: Nombre de la etiqueta sin grupo ('City').
            groups: Grupos por orden de preferencia ('XMP-photoshop', 'IPTC'...).
                Se comparan sin distinguir mayúsculas.

        Returns:
            El valor, o None si el archivo no tiene esa etiqueta.
        """
        suffix = ":" + name
        found: dict[str, Any] = {}
        for key, value in self.tags.items():
            if value is None or value == "":
                continue
            group, separator, tag = key.rpartition(":")
            if tag == name or (not separator and key == name):
                found[group.lower()] = value
            elif key.endswith(suffix):  # por si el grupo contiene ':' (no ocurre en -G1)
                found[key[: -len(suffix)].lower()] = value
        if not found:
            return None
        for group in groups:
            if group.lower() in found:
                return found[group.lower()]
        return next(iter(found.values()))


def find_exiftool(search_dirs: Sequence[Path | str] = ()) -> list[str] | None:
    """Localiza el programa ExifTool y devuelve el comando para ejecutarlo.

    Args:
        search_dirs: Carpetas donde buscar 'exiftool' (o 'exiftool.exe' en Windows)
            antes de mirar el PATH.

    Returns:
        La lista de argumentos que lanza ExifTool (normalmente solo su ruta; en
        macOS y Linux, si el archivo es el script Perl sin permiso de ejecución,
        se lanza con 'perl'), o None si no se encuentra.
    """
    executable_name = "exiftool.exe" if sys.platform == "win32" else "exiftool"

    candidates: list[Path] = []
    from_environment = os.environ.get("EXIFTOOL_PATH")
    if from_environment:
        candidates.append(Path(from_environment))
    candidates += [Path(folder) / executable_name for folder in search_dirs]
    from_path = shutil.which("exiftool")
    if from_path:
        candidates.append(Path(from_path))

    for candidate in candidates:
        if not candidate.is_file():
            continue
        # Al empaquetar o copiar, el script de macOS/Linux puede perder el permiso de
        # ejecución: en ese caso se lanza a través de Perl
        if sys.platform != "win32" and not os.access(candidate, os.X_OK):
            perl = shutil.which("perl")
            if perl:
                return [perl, str(candidate)]
        return [str(candidate)]
    return None


def find_sidecars(path: Path | str) -> list[Path]:
    """Busca los archivos .xmp "sidecar" que acompañan a un archivo.

    Los programas guardan los metadatos que no pueden escribir dentro del original
    (RAW propietarios, HEIC...) en un .xmp aparte. Hay dos convenciones:
        IMG_0001.xmp          Adobe (Lightroom, Camera Raw, Bridge)
        IMG_0001.CR3.xmp      otros programas (darktable, digiKam...)

    Returns:
        Los que existan, con la convención de Adobe primero. Se distingue 'xmp' de
        'XMP' (importa en sistemas de archivos que distinguen mayúsculas).
    """
    original = Path(path)
    candidates = [
        original.with_suffix(".xmp"),
        original.with_suffix(".XMP"),
        original.with_name(original.name + ".xmp"),
        original.with_name(original.name + ".XMP"),
    ]
    sidecars: list[Path] = []
    for candidate in candidates:
        # En sistemas que no distinguen mayúsculas, '.xmp' y '.XMP' son el mismo archivo
        if candidate.is_file() and candidate not in sidecars:
            if not any(_same_file(candidate, known) for known in sidecars):
                sidecars.append(candidate)
    return sidecars


def _same_file(first: Path, second: Path) -> bool:
    """True si dos rutas apuntan al mismo archivo (evita duplicados por mayúsculas)."""
    try:
        return first.samefile(second)
    except OSError:
        return False


class ExifToolRunner:
    """Ejecuta ExifTool por lotes y devuelve las etiquetas de cada archivo."""

    def __init__(
        self,
        command: Sequence[str] | None = None,
        *,
        search_dirs: Sequence[Path | str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        """Prepara el lector (comprueba que ExifTool existe, pero aún no lo ejecuta).

        Args:
            command: Comando que lanza ExifTool. Si no se indica, se busca con
                'find_exiftool'.
            search_dirs: Carpetas donde buscar ExifTool antes del PATH (por defecto,
                'tools/exiftool' del proyecto; ver 'find_exiftool').
            timeout: Segundos máximos de espera por cada llamada.
            batch_size: Archivos por llamada.

        Raises:
            ExifToolNotFoundError: Si no se encuentra ExifTool.
        """
        folders = DEFAULT_SEARCH_DIRS if search_dirs is None else search_dirs
        resolved = list(command) if command else find_exiftool(folders)
        if not resolved:
            raise ExifToolNotFoundError(
                "No se encontró ExifTool, el programa que lee los metadatos de las "
                "imágenes.\n\n"
                "  - Windows: descarga el ejecutable de exiftool.org, renombra "
                "'exiftool(-k).exe' a 'exiftool.exe' y déjalo junto a su carpeta "
                "'exiftool_files' en 'tools/exiftool'.\n"
                "  - macOS: brew install exiftool\n"
                "  - Linux: sudo apt install libimage-exiftool-perl"
            )
        self._command = resolved
        self._timeout = timeout
        self._batch_size = max(1, batch_size)
        self.calls = 0  # llamadas realizadas a ExifTool (útil para pruebas y diagnóstico)

    @property
    def command(self) -> list[str]:
        """El comando que se usa para lanzar ExifTool."""
        return list(self._command)

    def version(self) -> str:
        """Devuelve la versión de ExifTool (p. ej. '12.76')."""
        try:
            completed = subprocess.run(  # comando fijo, sin shell
                [*self._command, "-ver"],
                capture_output=True,
                timeout=self._timeout,
                creationflags=_CREATE_NO_WINDOW,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExifToolLaunchError(f"No se pudo ejecutar ExifTool: {exc}") from exc
        version = completed.stdout.decode("utf-8", errors="replace").strip()
        if completed.returncode != 0 or not version:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            raise ExifToolLaunchError(f"ExifTool no responde: {stderr or completed.returncode}")
        return version

    def read(
        self,
        paths: Sequence[Path | str],
        *,
        tags: Sequence[str] = (),
        cancel_event: threading.Event | None = None,
    ) -> dict[Path, FileMetadata]:
        """Lee las etiquetas de varios archivos (en lotes de 'batch_size').

        Args:
            paths: Archivos a leer (también valen los .xmp sidecar).
            tags: Si se indican (p. ej. ['-Make', '-GPS:all']), solo se piden esas
                etiquetas; vacío = todas.
            cancel_event: Si se activa, se detiene tras el lote en curso y se
                devuelve lo ya leído.

        Returns:
            Un 'FileMetadata' por archivo leído, indexado por su ruta. Un archivo
            que ExifTool no pudo leer trae el mensaje en 'error'.

        Raises:
            ExifToolLaunchError: Si ExifTool no se puede ejecutar (fallo general).
            ExifToolFileError: Si un lote tarda demasiado, falla o devuelve algo
                ilegible (puede deberse a un solo archivo: ver su docstring).
        """
        results: dict[Path, FileMetadata] = {}
        file_list = [Path(path) for path in paths]

        for start in range(0, len(file_list), self._batch_size):
            if cancel_event is not None and cancel_event.is_set():
                break
            batch = file_list[start : start + self._batch_size]
            for metadata in self._run_batch(batch, tags):
                results[metadata.path] = metadata
        return results

    # -------------------------------------------------------------------------
    # Pasos internos
    # -------------------------------------------------------------------------

    def _run_batch(self, batch: list[Path], tags: Sequence[str]) -> list[FileMetadata]:
        """Ejecuta ExifTool sobre un lote y convierte su salida JSON."""
        # La lista de archivos va en un archivo temporal UTF-8, uno por línea
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", suffix=".txt", delete=False
        ) as list_file:
            list_file.write("\n".join(str(path) for path in batch) + "\n")
            list_name = list_file.name

        try:
            self.calls += 1
            completed = subprocess.run(  # comando fijo, sin shell
                [*self._command, *_BASE_ARGS, *tags, "-@", list_name],
                capture_output=True,
                timeout=self._timeout,
                creationflags=_CREATE_NO_WINDOW,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExifToolFileError(
                f"ExifTool tardó más de {self._timeout:.0f} s en leer {len(batch)} archivos."
            ) from exc
        except OSError as exc:
            raise ExifToolLaunchError(f"No se pudo ejecutar ExifTool: {exc}") from exc
        finally:
            Path(list_name).unlink(missing_ok=True)

        stdout = completed.stdout.decode("utf-8", errors="replace").strip()
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()

        # ExifTool devuelve un código de error si ALGÚN archivo no se pudo leer, pero
        # aun así entrega el JSON de los demás: solo es un fallo si no hay salida
        if not stdout:
            if completed.returncode != 0:
                raise ExifToolFileError(f"ExifTool falló: {stderr or completed.returncode}")
            return [FileMetadata(path, error="ExifTool no devolvió datos") for path in batch]

        try:
            entries = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ExifToolFileError(f"La salida de ExifTool no es JSON válido: {exc}") from exc
        if stderr:
            logger.debug(f"ExifTool avisa: {stderr[:300]}")

        return self._match_entries(batch, entries)

    @staticmethod
    def _match_entries(batch: list[Path], entries: list[dict[str, Any]]) -> list[FileMetadata]:
        """Asocia cada entrada del JSON con el archivo al que corresponde."""
        # ExifTool entrega una entrada por archivo y en el mismo orden en que se
        # pidieron: es lo más fiable (el nombre puede volver con otro formato, p. ej.
        # barras '/' en Windows o distinta normalización de acentos)
        if len(entries) == len(batch):
            pairs = list(zip(batch, entries, strict=True))
        else:
            # Si faltan entradas, se asocian por nombre; las que falten se marcan
            by_name = {_normalize(entry.get("SourceFile", "")): entry for entry in entries}
            pairs = [(path, by_name.get(_normalize(str(path)), {})) for path in batch]

        results: list[FileMetadata] = []
        for path, entry in pairs:
            tags = {key: value for key, value in entry.items() if key != "SourceFile"}
            error = tags.get("ExifTool:Error") or tags.get("Error")
            if not entry:
                error = "ExifTool no devolvió datos de este archivo"
            results.append(FileMetadata(path, tags, str(error) if error else None))
        return results


def _normalize(path: str) -> str:
    """Forma comparable de una ruta (ExifTool la devuelve con '/' incluso en Windows)."""
    return os.path.normcase(os.path.abspath(path))


if __name__ == "__main__":
    # Autoprueba con un ExifTool SIMULADO (un script de Python que imita su salida JSON).
    # No comprueba que las etiquetas reales coincidan: eso se verifica con
    # 'core.metadata.inspect_cli' sobre archivos de verdad.
    # Ejecutar desde la raíz del proyecto:  python -m core.metadata.exiftool_runner
    FAKE_EXIFTOOL = r'''
import json, os, sys, time
args = sys.argv[1:]
if "-ver" in args:
    print("12.99"); sys.exit(0)
files, i = [], 0
while i < len(args):
    if args[i] == "-@":
        files = open(args[i + 1], encoding="utf-8").read().splitlines(); i += 2
    elif args[i] == "-charset":
        i += 2
    else:
        i += 1
if any("lento" in f for f in files):
    time.sleep(3)
if any("roto_total" in f for f in files):
    sys.stderr.write("Error catastrófico"); sys.exit(1)
entries = []
for f in files:
    if not os.path.exists(f):
        entries.append({"SourceFile": f.replace("\\", "/"), "ExifTool:Error": "File not found"})
    elif "sin_etiquetas" in f:
        entries.append({"SourceFile": f.replace("\\", "/")})
    else:
        entries.append({"SourceFile": f.replace("\\", "/"), "IFD0:Make": "Apple", "IFD0:Model": "iPhone 17 Pro",
                        "ExifIFD:FNumber": 1.8, "XMP-photoshop:City": "Madrid", "IPTC:City": "Alcobendas",
                        "XMP-photoshop:Country": "", "Composite:GPSLatitude": 40.428, "Origen": f})
data = json.dumps(entries, ensure_ascii=False).encode("utf-8")
if len(entries) > 1 and "faltan" in files[0]:
    data = json.dumps(entries[:-1], ensure_ascii=False).encode("utf-8")   # una entrada menos
sys.stdout.buffer.write(data)
sys.exit(2 if any(not os.path.exists(f) for f in files) else 0)
'''
    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fake = base / "fake_exiftool.py"
        fake.write_text(FAKE_EXIFTOOL, encoding="utf-8")
        runner = ExifToolRunner(command=[sys.executable, str(fake)], batch_size=2, timeout=2.0)

        # 1. Versión
        assert runner.version() == "12.99"
        print("Versión:", runner.version())

        # 2. Lectura por lotes, con un nombre con acentos y un archivo inexistente
        names = ["Fotografía ñ.jpg", "b.dng", "c.heic", "d.nef", "no_existe.jpg"]
        for name in names[:-1]:
            (base / name).write_bytes(b"x")
        results = runner.read([base / name for name in names])
        assert runner.calls == 3  # 5 archivos en lotes de 2 -> 2 + 2 + 1 llamadas (la de la versión no cuenta)
        assert len(results) == 5
        accented = results[base / "Fotografía ñ.jpg"]
        assert accented.error is None and accented.tags["IFD0:Make"] == "Apple"
        assert accented.tags["Origen"] == str(base / "Fotografía ñ.jpg")  # la ruta con acentos llegó intacta
        missing = results[base / "no_existe.jpg"]
        assert missing.error == "File not found" and missing.find("Make") is None
        print("Lectura por lotes: 5 archivos en 3 llamadas; el inexistente trae su error")

        # 3. Archivo sin ninguna etiqueta y salida con una entrada de menos
        (base / "sin_etiquetas.jpg").write_bytes(b"x")
        only = runner.read([base / "sin_etiquetas.jpg"])
        assert only[base / "sin_etiquetas.jpg"].tags == {} and only[base / "sin_etiquetas.jpg"].error is None
        (base / "faltan_1.jpg").write_bytes(b"x")
        (base / "faltan_2.jpg").write_bytes(b"x")
        partial = runner.read([base / "faltan_1.jpg", base / "faltan_2.jpg"])
        assert partial[base / "faltan_1.jpg"].error is None
        assert partial[base / "faltan_2.jpg"].error is not None  # la que no vino se marca, no se pierde
        print("Salida incompleta: la entrada que falta se marca con un error")

        # 4. 'find': prefiere el grupo indicado, ignora valores vacíos y cae a cualquier grupo
        metadata = accented
        assert metadata.find("City", groups=("XMP-photoshop", "IPTC")) == "Madrid"
        assert metadata.find("City", groups=("IPTC", "XMP-photoshop")) == "Alcobendas"
        assert metadata.find("City", groups=("IFD0",)) in {"Madrid", "Alcobendas"}  # cualquier otro grupo
        assert metadata.find("Country") is None  # vacío = ausente
        assert metadata.find("GPSLatitude", groups=("Composite",)) == 40.428
        assert metadata.find("Inexistente") is None

        # 5. Cancelación: no se llama a ExifTool
        event = threading.Event()
        event.set()
        calls_before = runner.calls
        assert runner.read([base / "b.dng"], cancel_event=event) == {} and runner.calls == calls_before

        # 6. Fallos: tiempo agotado, fallo total y comando inexistente
        (base / "lento.jpg").write_bytes(b"x")
        try:
            runner.read([base / "lento.jpg"])
        except ExifToolFileError as error:  # un fallo que puede ser de un solo archivo
            print("Tiempo agotado:", error)
        else:
            raise AssertionError("Debería agotar el tiempo")
        (base / "roto_total.jpg").write_bytes(b"x")
        try:
            runner.read([base / "roto_total.jpg"])
        except ExifToolFileError as error:
            print("Caída de ExifTool:", error)
        else:
            raise AssertionError("Debería fallar")
        try:
            ExifToolRunner(command=[str(base / "no_existe_exiftool")]).read([base / "b.dng"])
        except ExifToolLaunchError as error:  # un fallo general: no se puede ejecutar
            print("Comando inexistente:", str(error)[:60])
        else:
            raise AssertionError("Debería fallar")
        try:
            ExifToolRunner(command=[sys.executable, "-c", "pass"]).version()  # no imprime versión
        except ExifToolLaunchError as error:
            print("ExifTool que no responde:", error)
        else:
            raise AssertionError("Debería detectar que no responde")

        # 7. Búsqueda de ExifTool: variable de entorno, carpetas y comando 'perl'
        saved_environment = {key: os.environ.pop(key, None) for key in ("EXIFTOOL_PATH",)}
        saved_path = os.environ["PATH"]
        os.environ["PATH"] = str(base / "vacia")  # sin ExifTool en el PATH
        try:
            tools = base / "tools"
            tools.mkdir()
            program = tools / ("exiftool.exe" if sys.platform == "win32" else "exiftool")
            assert find_exiftool([tools]) is None
            program.write_bytes(b"#!/usr/bin/perl\n")
            program.chmod(0o755)
            assert find_exiftool([tools]) == [str(program)]
            os.environ["EXIFTOOL_PATH"] = str(program)
            assert find_exiftool() == [str(program)]
            del os.environ["EXIFTOOL_PATH"]
            if sys.platform != "win32" and shutil.which("perl", path=saved_path):
                program.chmod(0o644)  # sin permiso de ejecución: se lanza con perl
                os.environ["PATH"] = saved_path
                assert find_exiftool([tools])[1:] == [str(program)]
                print("ExifTool sin permiso de ejecución: se lanza con perl")
            try:
                os.environ["PATH"] = str(base / "vacia")
                ExifToolRunner(search_dirs=[base / "nada"])
            except ExifToolNotFoundError as error:
                print("ExifTool no instalado:", str(error).splitlines()[0])
            else:
                raise AssertionError("Debería avisar de que no hay ExifTool")
        finally:
            os.environ["PATH"] = saved_path
            for key, value in saved_environment.items():
                if value is not None:
                    os.environ[key] = value

        # 8. Sidecars: convención de Adobe primero, y la de otros programas después
        photo = base / "IMG_0001.CR3"
        photo.write_bytes(b"x")
        assert find_sidecars(photo) == []
        (base / "IMG_0001.CR3.xmp").write_text("<x/>")
        assert find_sidecars(photo) == [base / "IMG_0001.CR3.xmp"]
        (base / "IMG_0001.xmp").write_text("<x/>")
        assert find_sidecars(photo) == [base / "IMG_0001.xmp", base / "IMG_0001.CR3.xmp"]
        print("Sidecars encontrados:", [path.name for path in find_sidecars(photo)])

    print("Autoprueba finalizada correctamente.")
