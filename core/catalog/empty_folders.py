"""Carpetas del catálogo que se han quedado vacías en el disco: cuáles son y borrarlas.

Este módulo NO depende de Qt ni de la base de datos: solo mira y toca el disco. La
papelera se recibe como función ('trash'), que la interfaz construye con Qt
('ui_file_manager.move_to_trash'), como en 'media_removal.py'.

Para qué (CAT 3; reglas en docs/DECISIONES.md, 19/11/2026): como en Lightroom Classic, al
quitar del catálogo una carpeta ('folder_removal.py'), la que está vacía en el disco se borra
también del disco. Desde CAT 5 es el único momento: una carpeta que se vacía al mover o al
eliminar sus archivos se queda, y el árbol la muestra con 0 (antes se borraba, CAT 3.3).

Cuándo una carpeta se puede borrar:
    - Es una carpeta que el catálogo CONOCÍA: la de algún archivo del catálogo o una de sus
      carpetas padre ('candidate_folders') o una apuntada en sus carpetas (CAT 5; las junta
      quien llama). Una carpeta del disco que el catálogo no conoce no se toca nunca.
    - No contiene NINGÚN archivo, salvo los que sobran ('LEFTOVER_FILE_NAMES'): el archivo
      de carpeta '.arca.json' y su copia '.arca.json.bak', y los del sistema que el escáner
      ya ignora ('Thumbs.db', 'desktop.ini', '.DS_Store', los '._*' de macOS). Cualquier
      otro archivo, oculto o no, catalogado o no, la mantiene.
    - Sus subcarpetas también se pueden borrar (se decide de abajo arriba). Una subcarpeta
      que no es del catálogo, un enlace simbólico o una unión de Windows la mantienen.
    - Nunca la raíz de una ubicación (un disco desconectado deja un punto de montaje vacío
      y legible) ni un punto de montaje. Tampoco se debe llamar con una ubicación
      desconectada o en una unidad de red (sin Papelera): eso lo comprueba quien llama.

Cómo se borra ('remove_empty_folders'), carpeta a carpeta, de la más profunda a la menos:
se vuelve a mirar la carpeta justo antes (si ha aparecido algo, se deja), lo que sobra va a
la Papelera y la carpeta se borra con 'os.rmdir', que el sistema rechaza si queda cualquier
cosa dentro. Así nunca se borra contenido, aunque aparezca un archivo entre la comprobación
y el borrado. Lo que falla (un archivo abierto, sin permisos) deja la carpeta como estaba.

El '.arca.json' guarda los datos de los archivos de SU carpeta que no son fotos (vídeo,
audio, GPX...). En una carpeta vacía, sus entradas son de archivos que ya no están: si se
movieron fuera de la aplicación, sus datos se perderían. Por eso el plan cuenta cuántos
archivos tienen datos ('folder_file_items'), para que el aviso lo diga; como va a la
Papelera, se puede recuperar.

Uso:
    candidates = candidate_folders(rutas_de_los_archivos, within="2024/Viaje")
    plan = plan_empty_folders(raiz_de_la_ubicacion, candidates)     # para el aviso
    result = remove_empty_folders(plan, move_to_trash)               # en el trabajo

    # Cómo quedarían las carpetas si se fueran unos archivos (hoy no lo usa nadie: era
    # para borrar las que se vaciaban al eliminar o mover, CAT 3.3 y 4.4b)
    plan = plan_empty_folders(raiz, candidates, ignore_files=rutas_que_se_van)

1.0.1 Cabecera al día: desde CAT 5 solo la usa «Quitar del catálogo» una carpeta.
1.0.0 Primera versión (CAT 3.1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.empty_folders
"""

__version__ = "1.0.1"
__all__ = [
    "LEFTOVER_FILE_NAMES",
    "EmptyFolder",
    "EmptyFolderPlan",
    "EmptyFolderResult",
    "candidate_folders",
    "plan_empty_folders",
    "remove_empty_folders",
]

# Librerías estándar
import os
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.scan_filter import APPLEDOUBLE_PREFIX, IGNORED_FILE_NAMES
from core.userdata.folder_file import (
    BACKUP_FILE_NAME,
    FOLDER_FILE_NAME,
    FolderFileError,
    read_folder_file,
)

# Archivos que pueden quedar en una carpeta "vacía" (en minúsculas): el archivo de carpeta
# de la aplicación y los del sistema que el escáner ignora. Además, los que empiezan por
# 'APPLEDOUBLE_PREFIX' ('._foto.jpg': metadatos de macOS de un archivo)
LEFTOVER_FILE_NAMES: frozenset[str] = frozenset(
    {FOLDER_FILE_NAME, BACKUP_FILE_NAME} | IGNORED_FILE_NAMES
)

# Envía un archivo a la papelera; lanza OSError si no puede (ver 'ui_file_manager')
TrashFunction = Callable[[Path], None]


@dataclass(frozen=True, slots=True)
class EmptyFolder:
    """Una carpeta que se puede borrar del disco.

    Attributes:
        relative_path: Carpeta, relativa a la raíz de la ubicación y con '/'.
        leftovers: Nombres de los archivos que sobran (irán a la Papelera), en el orden
            en que se envían: los del sistema primero y el '.arca.json' al final.
        folder_file_items: Archivos con datos en su '.arca.json' (que ya no están en la
            carpeta, o que se van a ir).
    """

    relative_path: str
    leftovers: tuple[str, ...] = ()
    folder_file_items: int = 0


@dataclass(frozen=True, slots=True)
class EmptyFolderPlan:
    """Qué carpetas se pueden borrar del disco (lo calcula 'plan_empty_folders').

    Attributes:
        root: Raíz de la ubicación.
        folders: Las carpetas que se pueden borrar, de la más profunda a la menos (el
            orden en que se borran).
        kept: Las que se quedan, con el motivo (para el registro de la aplicación).
    """

    root: Path
    folders: tuple[EmptyFolder, ...] = ()
    kept: tuple[tuple[str, str], ...] = ()

    @property
    def top_folders(self) -> tuple[str, ...]:
        """Las carpetas del plan que no están dentro de otra del plan (para el aviso)."""
        keys = {_key(folder.relative_path) for folder in self.folders}
        tops = [
            folder.relative_path
            for folder in self.folders
            if not any(_key(parent) in keys for parent in _parents(folder.relative_path))
        ]
        return tuple(sorted(tops))

    @property
    def folder_file_items(self) -> int:
        """Archivos con datos en los '.arca.json' que irían a la Papelera."""
        return sum(folder.folder_file_items for folder in self.folders)


@dataclass(slots=True)
class EmptyFolderResult:
    """Lo que hizo 'remove_empty_folders'.

    Attributes:
        removed: Carpetas borradas del disco (relativas a la raíz).
        kept: Carpetas del plan que se quedaron, con el motivo.
        cancelled: Si se paró antes de terminar.
    """

    removed: list[str] = field(default_factory=list)
    kept: list[tuple[str, str]] = field(default_factory=list)
    cancelled: bool = False


def _normalize(path: str) -> str:
    """Ruta relativa con '/' y sin barras en los extremos ('' = la raíz)."""
    return path.replace("\\", "/").strip("/")


def _key(relative_path: str) -> str:
    """Clave para comparar rutas: sin distinguir mayúsculas donde el sistema no lo hace."""
    return os.path.normcase(_normalize(relative_path))


def _depth(relative_path: str) -> int:
    return relative_path.count("/") + 1


def _parents(relative_path: str) -> list[str]:
    """Carpetas que contienen a esta, de la más cercana a la raíz (excluida)."""
    result = []
    parent = PurePosixPath(relative_path).parent
    while str(parent) not in ("", "."):
        result.append(str(parent))
        parent = parent.parent
    return result


def _is_leftover(name: str) -> bool:
    return name.casefold() in LEFTOVER_FILE_NAMES or name.startswith(APPLEDOUBLE_PREFIX)


def _trash_order(name: str) -> tuple[int, str]:
    """Primero los del sistema, después la copia y al final el '.arca.json'."""
    folded = name.casefold()
    rank = {BACKUP_FILE_NAME: 1, FOLDER_FILE_NAME: 2}.get(folded, 0)
    return rank, folded


def candidate_folders(file_paths: Iterable[str], *, within: str | None = None) -> set[str]:
    """Las carpetas que el catálogo conocía, a partir de las rutas de sus archivos.

    Cada archivo aporta su carpeta y las de encima, hasta la raíz (que nunca se incluye).

    Args:
        file_paths: Rutas relativas a la ubicación de archivos del catálogo.
        within: Con «Quitar del catálogo…», la carpeta que se quita: solo cuentan ella y las
            de dentro (ella siempre, aunque no tenga archivos). '' = toda la ubicación.

    Returns:
        Rutas relativas, con '/'.
    """
    limit = _normalize(within) if within is not None else None
    result: set[str] = {limit} if limit else set()
    for file_path in file_paths:
        for folder in _parents(_normalize(file_path)):
            if limit and folder != limit and not folder.startswith(limit + "/"):
                break  # por encima de la carpeta que se quita
            result.add(folder)
    return result


def _inspect(
    root: Path,
    relative_path: str,
    removable_children: set[str],
    ignored_files: set[str],
) -> EmptyFolder | str:
    """Mira si una carpeta se puede borrar.

    Returns:
        La carpeta (con lo que sobra), o el motivo por el que se queda.
    """
    path = root / relative_path
    if path.is_symlink() or path.is_junction():
        return "es un enlace"
    if not path.is_dir():
        return "ya no existe"
    if os.path.ismount(path):
        return "es un punto de montaje"

    leftovers: list[str] = []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                child = f"{relative_path}/{entry.name}"
                if entry.is_symlink() or entry.is_junction():
                    return f"contiene un enlace («{entry.name}»)"
                if entry.is_dir(follow_symlinks=False):
                    if _key(child) not in removable_children:
                        return f"contiene la carpeta «{entry.name}»"
                elif _key(child) in ignored_files:
                    continue  # se va a ir (CAT 3.3)
                elif _is_leftover(entry.name):
                    leftovers.append(entry.name)
                else:
                    return f"contiene «{entry.name}»"
    except OSError as exc:
        return f"no se pudo leer ({exc})"

    items = 0
    if any(name.casefold() in (FOLDER_FILE_NAME, BACKUP_FILE_NAME) for name in leftovers):
        try:
            data = read_folder_file(path)
        except FolderFileError as exc:
            # No se sabe qué guarda: mejor no tocarlo
            return f"no se pudo leer su {FOLDER_FILE_NAME} ({exc})"
        items = sum(
            1 for name in data.items if _key(f"{relative_path}/{name}") not in ignored_files
        )
    return EmptyFolder(relative_path, tuple(sorted(leftovers, key=_trash_order)), items)


def plan_empty_folders(
    root: str | Path,
    candidates: Iterable[str],
    *,
    ignore_files: Iterable[str] = (),
) -> EmptyFolderPlan:
    """Decide qué carpetas se pueden borrar del disco. No cambia nada.

    Lee el disco (poco: cada carpeta se deja de mirar en cuanto algo la mantiene), así que
    se llama fuera del hilo de la interfaz.

    Args:
        root: Raíz de la ubicación (conectada y que no sea de red: lo comprueba quien llama).
        candidates: Carpetas que el catálogo conocía ('candidate_folders'). La raíz ('')
            se descarta siempre.
        ignore_files: Archivos (rutas relativas) que se van a ir antes de borrar las
            carpetas (los que se envían a la Papelera, con sus '.xmp'): se cuentan como si
            ya no estuvieran. Sus entradas del '.arca.json' tampoco cuentan para el aviso.
    """
    root_path = Path(root)
    wanted = {_normalize(candidate) for candidate in candidates} - {""}
    ignored = {_key(path) for path in ignore_files}
    removable: dict[str, EmptyFolder] = {}
    kept: list[tuple[str, str]] = []
    for relative_path in sorted(wanted, key=lambda rel: (-_depth(rel), rel)):
        outcome = _inspect(root_path, relative_path, set(removable), ignored)
        if isinstance(outcome, EmptyFolder):
            removable[_key(relative_path)] = outcome
        else:
            kept.append((relative_path, outcome))
    return EmptyFolderPlan(root_path, tuple(removable.values()), tuple(kept))


def remove_empty_folders(
    plan: EmptyFolderPlan,
    trash: TrashFunction,
    *,
    cancel_event: threading.Event | None = None,
) -> EmptyFolderResult:
    """Borra del disco las carpetas del plan (lo que sobra, a la Papelera; ellas, con 'os.rmdir').

    Cada carpeta se vuelve a mirar justo antes: si ha aparecido algo (o más datos en su
    '.arca.json' de los que dijo el aviso), se deja. Un fallo deja esa carpeta (y las que
    la contienen) como estaban; no lanza excepciones.

    Args:
        plan: El de 'plan_empty_folders'.
        trash: Función que envía un archivo a la Papelera.
        cancel_event: Si se activa, se para antes de la siguiente carpeta.
    """
    result = EmptyFolderResult()
    removed: set[str] = set()
    for planned in plan.folders:
        if cancel_event is not None and cancel_event.is_set():
            result.cancelled = True
            break
        relative_path = _normalize(planned.relative_path)
        if not relative_path:
            continue  # la raíz, nunca (el plan no la incluye: es una salvaguarda más)
        current = _inspect(plan.root, relative_path, removed, set())
        if isinstance(current, str):
            result.kept.append((relative_path, current))
            continue
        if current.folder_file_items > planned.folder_file_items:
            result.kept.append((relative_path, f"su {FOLDER_FILE_NAME} tiene datos nuevos"))
            continue
        folder = plan.root / relative_path
        try:
            for name in current.leftovers:
                try:
                    trash(folder / name)
                except FileNotFoundError:
                    pass  # ya no estaba
            os.rmdir(folder)
        except OSError as exc:
            result.kept.append((relative_path, f"no se pudo borrar ({exc})"))
            continue
        removed.add(_key(relative_path))
        result.removed.append(relative_path)
        logger.info(f"Carpeta vacía borrada del disco: {folder}")
    for relative_path, reason in result.kept:
        logger.info(f"Carpeta que se queda en el disco: {plan.root / relative_path}: {reason}")
    return result


if __name__ == "__main__":
    # Autoprueba con carpetas temporales y una papelera simulada (otra carpeta temporal).
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.empty_folders
    import sys
    import tempfile

    from core.userdata.folder_file import FolderData, write_folder_file

    # ---- 1. Las carpetas que el catálogo conocía ----
    files = ["2024/Viaje/a.jpg", "2024/Viaje/sub/b.jpg", "2024b/c.jpg", "suelta.jpg"]
    assert candidate_folders(files) == {"2024", "2024/Viaje", "2024/Viaje/sub", "2024b"}
    assert candidate_folders(files, within="2024/Viaje") == {"2024/Viaje", "2024/Viaje/sub"}
    assert candidate_folders(files, within="2024") == {"2024", "2024/Viaje", "2024/Viaje/sub"}
    assert candidate_folders(files, within="") == candidate_folders(files)  # sin la raíz
    assert candidate_folders([], within="\\Vacia\\") == {"Vacia"}  # ella, aunque no tenga nada
    print("1. Carpetas candidatas: con y sin carpeta límite, nunca la raíz")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "ubicacion"
        bin_dir = Path(tmp) / "papelera"
        bin_dir.mkdir()
        trashed: list[str] = []

        def fake_trash(path: Path) -> None:
            """Papelera simulada: mueve el archivo a otra carpeta (con un número delante)."""
            if not path.exists():
                raise FileNotFoundError(path)
            path.replace(bin_dir / f"{len(trashed)}_{path.name}")
            trashed.append(path.relative_to(root).as_posix())

        def make(relative: str, content: str = "x") -> Path:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return path

        def folder_file(relative_folder: str, names: list[str]) -> None:
            folder = root / relative_folder
            folder.mkdir(parents=True, exist_ok=True)
            items = {name: {"rating": 3} for name in names}
            assert write_folder_file(FolderData(directory=folder, items=items))

        # Viaje: solo lo que sobra (su .arca.json con datos de 2 vídeos que ya no están)
        folder_file("Viaje", ["clip1.mp4", "clip2.mp4"])
        make("Viaje/Thumbs.db")
        (root / "Viaje/sub").mkdir()  # vacía y del catálogo
        make("Viaje2/foto.jpg")  # tiene una foto: se queda
        make("Mixta/.oculto")  # un archivo oculto cualquiera: se queda
        (root / "Mixta/vacia").mkdir(parents=True)  # pero su subcarpeta vacía, no
        (root / "Preparada").mkdir()  # vacía, pero el catálogo no la conocía: no se toca
        (root / "Padre/Plantilla").mkdir(parents=True)  # su subcarpeta no es del catálogo
        candidates = {"Viaje", "Viaje/sub", "Viaje2", "Mixta", "Mixta/vacia", "Padre", ""}

        # ---- 2. El plan ----
        plan = plan_empty_folders(root, candidates)
        assert [f.relative_path for f in plan.folders] == ["Mixta/vacia", "Viaje/sub", "Viaje"]
        assert plan.top_folders == ("Mixta/vacia", "Viaje"), plan.top_folders
        viaje = plan.folders[-1]
        assert viaje.leftovers == ("Thumbs.db", ".arca.json"), viaje.leftovers
        assert plan.folder_file_items == 2
        kept = dict(plan.kept)
        assert kept["Viaje2"] == "contiene «foto.jpg»"
        assert kept["Mixta"] == "contiene «.oculto»"
        assert kept["Padre"] == "contiene la carpeta «Plantilla»"
        assert "" not in kept  # la raíz ni se mira
        print("2. Plan: 3 carpetas (de abajo arriba), 2 archivos con datos en el .arca.json")

        # ---- 3. Borrar ----
        result = remove_empty_folders(plan, fake_trash)
        assert result.removed == ["Mixta/vacia", "Viaje/sub", "Viaje"], result
        assert not (root / "Viaje").exists() and not (root / "Mixta/vacia").exists()
        assert trashed == ["Viaje/Thumbs.db", "Viaje/.arca.json"], trashed
        for untouched in ("Viaje2/foto.jpg", "Mixta/.oculto", "Preparada", "Padre/Plantilla"):
            assert (root / untouched).exists(), untouched
        assert root.is_dir()
        print("3. Borradas; lo que sobra, en la papelera; lo demás, intacto")

        # ---- 4. Si aparece un archivo entre el plan y el borrado, la carpeta se queda ----
        folder_file("Carrera", ["video.mp4"])
        plan = plan_empty_folders(root, {"Carrera"})
        assert [f.relative_path for f in plan.folders] == ["Carrera"]
        make("Carrera/nueva.jpg")
        trashed.clear()
        result = remove_empty_folders(plan, fake_trash)
        assert result.removed == [] and result.kept == [("Carrera", "contiene «nueva.jpg»")]
        assert trashed == [] and (root / "Carrera/.arca.json").exists()  # su .arca.json, intacto
        print("4. Un archivo nuevo antes de borrar: la carpeta y su .arca.json se quedan")

        # ---- 5. Si la papelera falla, la carpeta se queda; la de encima, también ----
        (root / "Abierta/sub").mkdir(parents=True)
        make("Abierta/sub/desktop.ini")

        def failing_trash(path: Path) -> None:
            raise OSError(f"abierto en otro programa: {path.name}")

        plan = plan_empty_folders(root, {"Abierta", "Abierta/sub"})
        assert len(plan.folders) == 2
        result = remove_empty_folders(plan, failing_trash)
        assert result.removed == [] and [k[0] for k in result.kept] == ["Abierta/sub", "Abierta"]
        assert (root / "Abierta/sub/desktop.ini").exists()
        print("5. Papelera que falla: nada se borra")

        # ---- 6. CAT 3.3: con los archivos que se van, la carpeta quedaría vacía ----
        make("Raw/IMG_1.CR3")
        make("Raw/IMG_1.xmp")
        folder_file("Raw", ["IMG_1.CR3", "clip.mp4"])  # el clip ya no está; el CR3 se va
        going = ["Raw/IMG_1.CR3", "Raw/img_1.xmp"]  # el .xmp, en minúsculas
        plan = plan_empty_folders(root, {"Raw"}, ignore_files=going)
        if sys.platform == "win32":  # en Windows, sin distinguir mayúsculas
            assert [f.relative_path for f in plan.folders] == ["Raw"], plan
            assert plan.folder_file_items == 1  # solo el clip: la entrada del CR3 se va con él
        plan = plan_empty_folders(root, {"Raw"}, ignore_files=["Raw/IMG_1.CR3"])
        assert plan.folders == () and dict(plan.kept)["Raw"] == "contiene «IMG_1.xmp»"
        print("6. Con los archivos que se van, la carpeta quedaría vacía (con su .xmp también)")

        # ---- 7. Un .arca.json dañado: no se sabe qué guarda, la carpeta se queda ----
        make("Rota/.arca.json", "{esto no es json")
        plan = plan_empty_folders(root, {"Rota"})
        assert plan.folders == () and dict(plan.kept)["Rota"].startswith("no se pudo leer su")
        print("7. .arca.json dañado: la carpeta se queda")

        # ---- 8. Cancelar antes de empezar; carpetas que ya no existen ----
        (root / "Tarde").mkdir()
        plan = plan_empty_folders(root, {"Tarde", "NoExiste"})
        assert dict(plan.kept)["NoExiste"] == "ya no existe"
        cancel = threading.Event()
        cancel.set()
        result = remove_empty_folders(plan, fake_trash, cancel_event=cancel)
        assert result.cancelled and result.removed == [] and (root / "Tarde").exists()
        print("8. Cancelado: nada se borra; una carpeta que ya no existe se ignora")

    print("Autoprueba finalizada correctamente.")
