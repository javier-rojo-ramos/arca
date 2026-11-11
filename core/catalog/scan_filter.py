"""Filtro previo al escaneo: decide qué archivos y carpetas NO merece la pena mirar.

Este módulo NO depende de Qt: es Python puro, así que se puede probar desde la
consola y ejecutar en un hilo secundario.

Es la FASE 1 del embudo de importación (antes de la detección de tipo de medio):

    1. ScanFilter          -> descarta ruido (este módulo)
    2. MediaTypeDetector   -> clasifica lo que queda (media_detector.py)
    3. Manejador por tipo  -> lee metadatos / crea miniatura (si falla, es un error)

Solo mira el NOMBRE y los atributos que el sistema ya entrega al listar una
carpeta con 'os.scandir()'; no abre ningún archivo. Por eso es muy barato y debe
ejecutarse ANTES de cualquier otra cosa: así un '.part' o un '._foto.jpg' nunca
llegan a leerse.

Importante: el filtro NO decide si un archivo es un medio soportado (un '.txt' lo
deja pasar: eso lo decide el detector) y se aplica solo a lo que hay DENTRO de la
carpeta elegida por el usuario, nunca a la propia carpeta raíz elegida.

Cada descarte devuelve un 'SkipReason', de modo que el escáner pueda contar cuántos
archivos se ignoraron y por qué. Un archivo ignorado NO es un error.

Para ampliar las reglas, basta con editar las constantes del principio del módulo.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.scan_filter
"""

__version__ = "1.0.1"
__all__ = ["ScanFilter", "SkipReason"]

# Librerías estándar
import os
import stat
import sys
from enum import StrEnum

# Verdadero solo en Windows: los atributos 'oculto' y 'sistema' solo existen allí
_IS_WINDOWS: bool = sys.platform == "win32"

# Archivos basura que crean los sistemas operativos y los NAS (en minúsculas: la
# comparación no distingue mayúsculas, como en Windows y en macOS por defecto)
IGNORED_FILE_NAMES: frozenset[str] = frozenset(
    {
        ".ds_store",  # macOS: ajustes de vista de carpeta
        "thumbs.db",  # Windows: caché de miniaturas
        "ehthumbs.db",  # Windows: caché de miniaturas (variante Media Center)
        "desktop.ini",  # Windows: personalización de carpeta
    }
)

# Prefijo de los archivos "AppleDouble" de macOS: metadatos de un archivo que se
# crean al copiar a discos FAT/exFAT o a recursos de red. Tienen la MISMA extensión
# que el original ('._foto.jpg'), por lo que el detector los confundiría con fotos
APPLEDOUBLE_PREFIX = "._"

# Extensiones de archivos temporales o descargas a medias. Tienen una cabecera
# válida (un vídeo a medio descargar se parece a un vídeo), pero no están completos
TEMPORARY_EXTENSIONS: frozenset[str] = frozenset(
    {".part", ".crdownload", ".download", ".partial", ".opdownload", ".tmp", ".temp"}
)

# Carpetas del sistema o de servicios que nunca se recorren (en minúsculas)
IGNORED_DIRECTORY_NAMES: frozenset[str] = frozenset(
    {
        "$recycle.bin",  # Windows: papelera
        "system volume information",  # Windows: puntos de restauración
        "@eadir",  # NAS Synology: miniaturas propias (llenarían el catálogo de duplicados)
        "#recycle",  # NAS Synology: papelera
        ".trashes",  # macOS: papelera de discos externos
        ".trash",  # Linux: papelera
        ".spotlight-v100",  # macOS: índice de búsqueda
        ".fseventsd",  # macOS: registro de cambios del sistema de archivos
        ".temporaryitems",  # macOS: temporales del sistema
        "__macosx",  # Restos de comprimir con el Finder de macOS
        "lost+found",  # Linux: archivos recuperados por fsck
    }
)


class SkipReason(StrEnum):
    """Motivo por el que un archivo o carpeta se descarta.

    Al ser un 'StrEnum', cada miembro también es un 'str': se puede usar como clave
    de un diccionario de contadores o escribir directamente en el log.
    """

    HIDDEN = "hidden"  # Oculto (empieza por punto, o atributo 'oculto' de Windows)
    SYSTEM = "system"  # Atributo 'sistema' de Windows
    JUNK_NAME = "junk_name"  # Nombre de archivo basura conocido (.DS_Store, ._x...)
    TEMPORARY = "temporary"  # Temporal o descarga incompleta (.part, .tmp...)
    EXCLUDED_DIRECTORY = "excluded_directory"  # Carpeta del sistema (papelera...)
    SYMLINK = "symlink"  # Enlace simbólico o unión de Windows (no se siguen)


class ScanFilter:
    """Decide si una entrada de carpeta ('os.DirEntry') debe ignorarse.

    No guarda estado entre entradas, así que una sola instancia se puede reutilizar
    para recorrer miles de archivos. Los métodos devuelven el motivo del descarte
    ('SkipReason') o 'None' si la entrada debe seguir adelante.

    Los métodos no lanzan excepciones por problemas de disco: si no se pueden leer
    los atributos de una entrada, se deja pasar y ya fallará (y se anotará como
    error) en la fase que intente leerla de verdad.
    """

    def __init__(
        self, *, skip_hidden: bool = True, follow_symlinks: bool = False
    ) -> None:
        """Configura el filtro.

        Args:
            skip_hidden: Si es True, se ignoran los archivos y carpetas ocultos
                (nombre que empieza por '.' o atributo 'oculto' de Windows).
                Los archivos basura ('.DS_Store', '._foto.jpg') se ignoran siempre.
            follow_symlinks: Si es False (recomendado), se ignoran los enlaces
                simbólicos y las uniones de Windows. Seguirlos puede provocar
                bucles infinitos o catalogar dos veces el mismo archivo. Si se
                pone en True, el escáner debe protegerse contra los bucles.
        """
        self.skip_hidden = skip_hidden
        self.follow_symlinks = follow_symlinks

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def check_file(self, entry: os.DirEntry[str]) -> SkipReason | None:
        """Indica por qué se ignora un archivo, o 'None' si debe procesarse."""
        if not self.follow_symlinks and entry.is_symlink():
            return SkipReason.SYMLINK

        name = entry.name.lower()

        # Archivos basura: se descartan siempre, aunque 'skip_hidden' sea False
        if name in IGNORED_FILE_NAMES or name.startswith(APPLEDOUBLE_PREFIX):
            return SkipReason.JUNK_NAME

        # Temporales y descargas a medias (se compara solo la última extensión)
        if os.path.splitext(name)[1] in TEMPORARY_EXTENSIONS:
            return SkipReason.TEMPORARY

        return self._check_hidden_and_system(entry, name)

    def check_directory(self, entry: os.DirEntry[str]) -> SkipReason | None:
        """Indica por qué NO se debe entrar en una carpeta, o 'None' si se recorre."""
        # Una unión de Windows ('junction') no cuenta como enlace simbólico para
        # 'is_symlink()', por eso se comprueba aparte
        if not self.follow_symlinks and (entry.is_symlink() or entry.is_junction()):
            return SkipReason.SYMLINK

        name = entry.name.lower()

        if name in IGNORED_DIRECTORY_NAMES:
            return SkipReason.EXCLUDED_DIRECTORY

        return self._check_hidden_and_system(entry, name)

    # -------------------------------------------------------------------------
    # Pasos internos
    # -------------------------------------------------------------------------

    def _check_hidden_and_system(
        self, entry: os.DirEntry[str], lower_name: str
    ) -> SkipReason | None:
        """Comprueba 'oculto' y 'sistema' (común a archivos y carpetas)."""
        # Oculto al estilo Unix/macOS: el nombre empieza por punto
        if self.skip_hidden and lower_name.startswith("."):
            return SkipReason.HIDDEN

        # Atributos de Windows. 'DirEntry.stat()' en Windows no cuesta una llamada
        # extra al disco (el sistema ya los entrega al listar la carpeta); en
        # macOS/Linux sí costaría, por eso solo se consulta en Windows.
        attributes = self._windows_attributes(entry)

        if attributes & stat.FILE_ATTRIBUTE_SYSTEM:
            return SkipReason.SYSTEM
        if self.skip_hidden and attributes & stat.FILE_ATTRIBUTE_HIDDEN:
            return SkipReason.HIDDEN

        return None

    @staticmethod
    def _windows_attributes(entry: os.DirEntry[str]) -> int:
        """Devuelve los atributos de Windows de la entrada (0 si no aplica o falla)."""
        if not _IS_WINDOWS:
            return 0
        try:
            return getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
        except OSError:
            # No se pueden leer los atributos: se deja pasar (ver docstring de la clase)
            return 0


if __name__ == "__main__":
    # Autoprueba: crea una estructura de carpetas falsa y comprueba cada regla.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.scan_filter
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        # --- Archivos: nombre -> motivo esperado (None = debe pasar) ---
        archivos: dict[str, SkipReason | None] = {
            "foto.jpg": None,
            "notas.txt": None,  # el filtro no juzga el tipo: eso es del detector
            "FOTO.JPG": None,
            ".oculto.jpg": SkipReason.HIDDEN,
            "._foto.jpg": SkipReason.JUNK_NAME,  # AppleDouble
            ".DS_Store": SkipReason.JUNK_NAME,
            "Thumbs.db": SkipReason.JUNK_NAME,
            "THUMBS.DB": SkipReason.JUNK_NAME,  # mayúsculas
            "desktop.ini": SkipReason.JUNK_NAME,
            "pelicula.mkv.part": SkipReason.TEMPORARY,
            "descarga.CRDOWNLOAD": SkipReason.TEMPORARY,
            "datos.tmp": SkipReason.TEMPORARY,
        }
        for nombre in archivos:
            (base / nombre).write_bytes(b"x")

        # --- Carpetas: nombre -> motivo esperado ---
        carpetas: dict[str, SkipReason | None] = {
            "Vacaciones": None,
            "$RECYCLE.BIN": SkipReason.EXCLUDED_DIRECTORY,
            "@eaDir": SkipReason.EXCLUDED_DIRECTORY,
            "__MACOSX": SkipReason.EXCLUDED_DIRECTORY,
            ".git": SkipReason.HIDDEN,
        }
        for nombre in carpetas:
            (base / nombre).mkdir()

        # --- Enlaces simbólicos (en Windows exigen permisos: si falla, se omite) ---
        try:
            os.symlink(base / "foto.jpg", base / "enlace.jpg")
            os.symlink(
                base / "Vacaciones", base / "enlace_carpeta", target_is_directory=True
            )
            archivos["enlace.jpg"] = SkipReason.SYMLINK
            carpetas["enlace_carpeta"] = SkipReason.SYMLINK
        except (OSError, NotImplementedError):
            print("(Se omite la prueba de enlaces simbólicos: no hay permisos)")

        def comprobar(filtro: ScanFilter, titulo: str, esperado_f, esperado_d) -> None:
            """Recorre la carpeta de prueba y compara cada entrada con lo esperado."""
            print(f"--- {titulo} ---")
            with os.scandir(base) as entradas:
                for entrada in entradas:
                    if entrada.is_dir(follow_symlinks=False) or (
                        entrada.is_symlink() and entrada.name in esperado_d
                    ):
                        obtenido = filtro.check_directory(entrada)
                        esperado = esperado_d[entrada.name]
                    else:
                        obtenido = filtro.check_file(entrada)
                        esperado = esperado_f[entrada.name]
                    estado = "OK " if obtenido == esperado else "MAL"
                    print(f"[{estado}] {entrada.name:<22} -> {obtenido}")
                    assert obtenido == esperado, (
                        f"{entrada.name}: {esperado} != {obtenido}"
                    )

        # 1) Configuración por defecto
        comprobar(ScanFilter(), "Por defecto", archivos, carpetas)

        # 2) Sin ocultar archivos ocultos: los basura y temporales se siguen ignorando
        archivos_2 = {**archivos, ".oculto.jpg": None}
        carpetas_2 = {**carpetas, ".git": None}
        comprobar(
            ScanFilter(skip_hidden=False), "skip_hidden=False", archivos_2, carpetas_2
        )

        # 3) Siguiendo enlaces simbólicos: ya no se descartan
        if "enlace.jpg" in archivos:
            archivos_3 = {**archivos, "enlace.jpg": None}
            carpetas_3 = {**carpetas, "enlace_carpeta": None}
            comprobar(
                ScanFilter(follow_symlinks=True),
                "follow_symlinks=True",
                archivos_3,
                carpetas_3,
            )

        # --- Atributos de Windows: se simulan para poder probarlos en cualquier SO ---
        class FakeStat:
            def __init__(self, atributos: int) -> None:
                self.st_file_attributes = atributos

        class FakeEntry:
            """Imita lo mínimo de os.DirEntry que usa el filtro."""

            def __init__(self, name: str, atributos: int) -> None:
                self.name = name
                self._atributos = atributos

            def is_symlink(self) -> bool:
                return False

            def is_junction(self) -> bool:
                return False

            def stat(self, follow_symlinks: bool = True) -> FakeStat:
                return FakeStat(self._atributos)

        _IS_WINDOWS_REAL = _IS_WINDOWS
        _IS_WINDOWS = True  # Se activa la rama de Windows solo durante esta prueba
        try:
            filtro = ScanFilter()
            oculto = FakeEntry("foto.jpg", stat.FILE_ATTRIBUTE_HIDDEN)
            sistema = FakeEntry("foto.jpg", stat.FILE_ATTRIBUTE_SYSTEM)
            normal = FakeEntry("foto.jpg", stat.FILE_ATTRIBUTE_ARCHIVE)

            assert filtro.check_file(oculto) == SkipReason.HIDDEN
            assert filtro.check_file(sistema) == SkipReason.SYSTEM
            assert filtro.check_file(normal) is None
            # 'sistema' se ignora siempre; 'oculto' solo si skip_hidden es True
            assert (
                ScanFilter(skip_hidden=False).check_file(sistema) == SkipReason.SYSTEM
            )
            assert ScanFilter(skip_hidden=False).check_file(oculto) is None
            print("[OK ] Atributos 'oculto' y 'sistema' de Windows (simulados)")
        finally:
            _IS_WINDOWS = _IS_WINDOWS_REAL

        print("Autoprueba finalizada correctamente.")
