"""«Localizar...» de una ubicación desconectada, pedido desde la barra del Catálogo (CAT 6.3).

    CatalogSidebar.locate_folder_requested(ubicación, carpeta, nombre, ruta de antes)
        └─► LocateActions.request_locate: ¿algo en marcha? → elegir dónde está ahora (el
                selector se abre en lo más cercano que exista de la ruta de antes) →
                comprobarlo en segundo plano ('plan_location_relocation') → un aviso si no
                vale, o la pregunta con lo que se ha encontrado → 'relocate_location' →
                la barra de estado lo dice y se recargan la cuadrícula y la barra lateral

Solo cambia el catálogo (la ruta y el nombre de la ubicación): en el disco no se toca
nada. Las reglas, en 'core/catalog/relocation.py'. «Localizar...» de una carpeta que falta
será el CAT 6.4: hoy la barra solo lo ofrece en la raíz de una ubicación desconectada, y
una petición con carpeta no hace nada.

Los textos los aprobó el autor el 20/11/2026 ('question_text', 'not_found_text').

El controlador principal solo lo crea:
    self._locate_actions = LocateActions(
        self, self.widget_catalog_sidebar, self.message_box, get_db=lambda: self.db,
        busy_reason=self.remove_actions.busy_reason, reload_grid=self.mosaico_model.reload,
    )

1.0.0 Primera versión (CAT 6.3).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.locate_actions
"""

__version__ = "1.0.0"
__all__ = ["LocateActions", "not_found_text", "question_text"]

# Librerías estándar
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject
from qtpy.QtWidgets import QWidget

# Módulos del proyecto
from config.app_constants import AppIcons
from core.catalog.relocation import (
    LocationRelocation,
    RelocationError,
    plan_location_relocation,
    relocate_location,
)
from ui_helpers.helpers.ui_file_dialogs import select_folder
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.helpers.ui_status import message_bar
from ui_helpers.inspector.formatting import format_count
from ui_helpers.sidebars.catalog_sidebar import CatalogSidebar

LOCATE_BUTTON_TEXT = "Localizar"
CANCEL_BUTTON_TEXT = "Cancelar"


def question_text(plan: LocationRelocation) -> str:
    """La pregunta antes de localizar: dónde estaba, dónde está y cuántos se encuentran."""
    if plan.total > plan.checked:
        found = (
            f"Se han comprobado {format_count(plan.checked)} de sus {format_count(plan.total)} "
            f"archivos: se encuentran {format_count(plan.found)}."
        )
    elif plan.total == 1:
        found = "Se encuentra su único archivo."
    elif plan.total:
        found = (
            f"Se encuentran {format_count(plan.found)} de sus {format_count(plan.total)} "
            "archivos."
        )
    else:
        found = "No tiene archivos en el catálogo que comprobar."
    last = "¿Cambiar su ubicación en el catálogo? En el disco no se toca nada."
    if plan.new_name != plan.name:
        last += f" Pasará a llamarse «{plan.new_name}»."
    return (
        f"«{plan.name}» estaba en {Path(plan.old_path)} y ahora está en {plan.new_path}.\n\n"
        f"{found}\n\n{last}"
    )


def not_found_text(plan: LocationRelocation) -> str:
    """El aviso cuando en la carpeta elegida no está ninguno de sus archivos."""
    return (
        f"En {plan.new_path} no está ninguno de los archivos de «{plan.name}» (se han "
        f"comprobado {format_count(plan.checked)}). Elige la carpeta que contiene sus carpetas "
        "y archivos."
    )


def _nearest_existing(path: str) -> str | None:
    """Lo más cercano que exista de la ruta de antes (la unidad, si sigue ahí), o None."""
    if not path:
        return None
    folder = Path(path)
    for candidate in (folder, *folder.parents):
        try:
            if candidate.is_dir():
                return str(candidate)
        except OSError:
            continue
    return None


class LocateActions(QObject):
    """Atiende «Localizar...» del menú de las carpetas de la barra del Catálogo."""

    def __init__(
        self,
        window: QWidget,
        sidebar: CatalogSidebar,
        message_box: MessageBoxHelper,
        *,
        get_db: Callable[[], Any],
        busy_reason: Callable[[], str | None],
        reload_grid: Callable[[], None],
        choose_folder: Callable[..., str | None] = select_folder,
    ) -> None:
        """Conecta la señal de la barra lateral.

        Args:
            window: Ventana principal (padre de este objeto y del selector).
            sidebar: Barra lateral del catálogo.
            message_box: Ayudante de mensajes de la ventana.
            get_db: Devuelve el gestor de la base de datos del catálogo abierto, o None.
            busy_reason: Por qué ahora no se puede (algo en marcha), o None.
            reload_grid: Recarga la cuadrícula (y, al terminar, la barra lateral).
            choose_folder: El selector de carpetas (otro, en la autoprueba).
        """
        super().__init__(window)
        self._window = window
        self._message_box = message_box
        self._get_db = get_db
        self._busy_reason = busy_reason
        self._reload_grid = reload_grid
        self._choose_folder = choose_folder
        sidebar.locate_folder_requested.connect(self.request_locate)

    def request_locate(self, location_id: int, folder: str, name: str, path: str) -> None:
        """Menú de una ubicación desconectada > «Localizar...»: elegir y comprobar."""
        db = self._get_db()
        if db is None or folder:  # una carpeta que falta: CAT 6.4
            return
        busy = self._busy_reason()
        if busy:
            # Mientras corre un trabajo, no: podría estar usando la ruta de la ubicación
            self._message_box.info(f"{busy}\n\nEspera a que termine para localizar una ubicación.")
            return
        chosen = self._choose_folder(
            self._window, f"Localizar «{name}»", _nearest_existing(path), force_dialog=True
        )
        db = self._get_db()
        if not chosen or db is None:
            return
        db.execute_async(
            plan_location_relocation,
            location_id,
            chosen,
            on_result=self._confirm,
            on_error=lambda error: self._message_box.critical(
                f"No se pudo comprobar la carpeta.\n\nDetalle: {error}"
            ),
        )

    def _confirm(self, plan: LocationRelocation) -> None:
        """Un aviso si la carpeta no vale; si vale, pregunta y localiza."""
        if self._get_db() is None:
            return  # el catálogo se ha cerrado mientras tanto
        if plan.problem:
            self._message_box.warning(plan.problem)
            return
        if plan.total and not plan.found:
            self._message_box.warning(not_found_text(plan))
            return
        answer = self._message_box.question(
            question_text(plan), buttons=[LOCATE_BUTTON_TEXT, CANCEL_BUTTON_TEXT]
        )
        db = self._get_db()
        if answer != LOCATE_BUTTON_TEXT or db is None:
            return
        db.execute_async(
            relocate_location,
            plan,
            on_result=lambda _result: self._on_relocated(plan),
            on_error=self._on_relocate_error,
        )

    def _on_relocated(self, plan: LocationRelocation) -> None:
        """Localizada: la barra de estado lo dice y se recargan la cuadrícula y la barra."""
        if self._get_db() is None:
            return
        message_bar(
            self._window,
            f"Ubicación localizada: «{plan.new_name}» ({plan.new_path}).",
            AppIcons.CHECK_CIRCLE,
        )
        # Al recargar, la barra lateral se pone al día sola (la ubicación, conectada y con
        # su nombre nuevo) y las tarjetas dejan de verse sin conexión
        self._reload_grid()

    def _on_relocate_error(self, error: Exception) -> None:
        """Algo ha cambiado desde la pregunta (el aviso lo explica), u otro error."""
        if isinstance(error, RelocationError):
            self._message_box.warning(str(error))
        else:
            self._message_box.critical(f"No se pudo localizar la ubicación.\n\nDetalle: {error}")


if __name__ == "__main__":
    # Autoprueba sin ventana: los mensajes y el selector son de mentira; la base de datos
    # (en memoria) y las carpetas, de verdad. Ejecutar desde la raíz del proyecto:
    #     python -m controllers.locate_actions
    import os
    import sqlite3
    import sys
    import tempfile

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtCore import Signal
    from qtpy.QtWidgets import QApplication, QMainWindow

    from core.catalog.catalog_schema import apply_migrations, configure_connection

    app = QApplication.instance() or QApplication(sys.argv)

    class FakeDb:
        """'execute_async' que ejecuta al momento sobre una base de datos de verdad, con el
        commit o el rollback del gestor."""

        def __init__(self, conn: sqlite3.Connection) -> None:
            self.conn = conn

        def execute_async(
            self, function: Any, *args: Any, on_result: Any = None, on_error: Any = None
        ) -> None:
            try:
                result = function(self.conn, *args)
                self.conn.commit()
            except Exception as error:  # noqa: BLE001 - como el gestor: va a 'on_error'
                self.conn.rollback()
                if on_error is not None:
                    on_error(error)
            else:
                if on_result is not None:
                    on_result(result)

    class FakeBox:
        """Apunta los mensajes; responde lo que diga 'answer'."""

        def __init__(self) -> None:
            self.answer = LOCATE_BUTTON_TEXT
            self.log: list[tuple[str, str]] = []

        def info(self, text: str, **_kwargs: object) -> None:
            self.log.append(("info", text))

        def warning(self, text: str, **_kwargs: object) -> None:
            self.log.append(("warning", text))

        def critical(self, text: str, **_kwargs: object) -> None:
            self.log.append(("critical", text))

        def question(self, text: str, **_kwargs: object) -> str:
            self.log.append(("question", text))
            return self.answer

    class FakeSidebar(QObject):
        locate_folder_requested = Signal(int, str, str, str)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        old, new = base / "E" / "FOTOS", base / "F" / "FOTOS"
        (new / "sub").mkdir(parents=True)
        for relative in ("a.jpg", "sub/b.jpg"):
            (new / relative).write_bytes(b"x")
        (base / "Vacía").mkdir()
        conn = sqlite3.connect(":memory:")
        configure_connection(conn)
        apply_migrations(conn)
        conn.execute(
            "INSERT INTO storage_locations(name, absolute_path, is_online) VALUES ('FOTOS', ?, 0)",
            (str(old),),
        )
        for relative in ("a.jpg", "sub/b.jpg", "sub/c.jpg"):
            conn.execute(
                """INSERT INTO media_items(storage_location_id, relative_path, file_name,
                       media_type, mime_type, file_size, file_mtime_ns, title)
                   VALUES (1, ?, ?, 'photo', 'image/jpeg', 1, 0, 'x')""",
                (relative, relative.rsplit("/", 1)[-1]),
            )
        conn.commit()

        window = QMainWindow()
        sidebar = FakeSidebar()
        box = FakeBox()
        db = FakeDb(conn)
        state = {"busy": None, "pick": str(new), "reloads": 0, "asked": []}

        def pick(_parent: object, title: str, start: str | None, **kwargs: object) -> str | None:
            state["asked"].append((title, start, kwargs.get("force_dialog")))
            return state["pick"]

        actions = LocateActions(
            window, sidebar, box,  # type: ignore[arg-type]
            get_db=lambda: db,
            busy_reason=lambda: state["busy"],
            reload_grid=lambda: state.update(reloads=state["reloads"] + 1),
            choose_folder=pick,
        )  # fmt: skip

        def location() -> tuple:
            row = conn.execute("SELECT name, absolute_path, is_online FROM storage_locations")
            return row.fetchone()

        # 1. Algo en marcha: un aviso y no se abre el selector
        state["busy"] = "Se están leyendo los metadatos."
        sidebar.locate_folder_requested.emit(1, "", "FOTOS", str(old))
        assert box.log == [("info", (
            "Se están leyendo los metadatos.\n\nEspera a que termine para localizar una ubicación."
        ))] and not state["asked"]  # fmt: skip
        state["busy"] = None
        # Una carpeta (CAT 6.4, todavía no): nada
        sidebar.locate_folder_requested.emit(1, "sub", "sub", str(old / "sub"))
        assert not state["asked"]
        print("1. Algo en marcha, o una carpeta: nada")

        # 2. Cancelar en el selector o en la pregunta: nada cambia
        state["pick"] = None
        sidebar.locate_folder_requested.emit(1, "", "FOTOS", str(old))
        title, start, forced = state["asked"][-1]
        assert title == "Localizar «FOTOS»" and forced is True
        assert start == str(base), start  # lo más cercano que existe de E/FOTOS
        state["pick"], box.answer = str(new), CANCEL_BUTTON_TEXT
        box.log.clear()
        sidebar.locate_folder_requested.emit(1, "", "FOTOS", str(old))
        assert box.log == [("question", (
            f"«FOTOS» estaba en {old} y ahora está en {new}.\n\n"
            "Se encuentran 2 de sus 3 archivos.\n\n"
            "¿Cambiar su ubicación en el catálogo? En el disco no se toca nada."
        ))], box.log  # fmt: skip
        assert location() == ("FOTOS", str(old), 0) and state["reloads"] == 0
        print("2. Cancelar: nada")

        # 3. Ninguno de sus archivos, o una carpeta que no vale: un aviso
        box.log.clear()
        state["pick"] = str(base / "Vacía")
        sidebar.locate_folder_requested.emit(1, "", "FOTOS", str(old))
        assert box.log == [("warning", (
            f"En {base / 'Vacía'} no está ninguno de los archivos de «FOTOS» (se han comprobado "
            "3). Elige la carpeta que contiene sus carpetas y archivos."
        ))], box.log  # fmt: skip
        state["pick"] = str(base / "No existe")
        sidebar.locate_folder_requested.emit(1, "", "FOTOS", str(old))
        assert box.log[-1] == ("warning", f"{base / 'No existe'} no existe o no es una carpeta.")
        print("3. Ninguno, o no existe: un aviso")

        # 4. Localizar: ruta, nombre y conectada; la cuadrícula se recarga
        box.log.clear()
        renamed = base / "F" / "FOTOS 2024"
        new.rename(renamed)
        state["pick"], box.answer = str(renamed), LOCATE_BUTTON_TEXT
        sidebar.locate_folder_requested.emit(1, "", "FOTOS", str(old))
        assert box.log[0][1].endswith("En el disco no se toca nada. Pasará a llamarse «FOTOS 2024»."), box.log
        assert location() == ("FOTOS 2024", str(renamed), 1) and state["reloads"] == 1
        print("4. Localizada:", location()[:2])

        # 5. El disco vuelve entre la pregunta y la orden: el aviso, y nada cambia
        conn.execute(
            "UPDATE storage_locations SET name = 'FOTOS', absolute_path = ?, is_online = 0",
            (str(old),),
        )
        conn.commit()

        def answer_and_reconnect(text: str, **_kwargs: object) -> str:
            box.log.append(("question", text))
            old.mkdir(parents=True)  # mientras se piensa la respuesta
            return LOCATE_BUTTON_TEXT

        box.question = answer_and_reconnect  # type: ignore[method-assign]
        sidebar.locate_folder_requested.emit(1, "", "FOTOS", str(old))
        assert box.log[-1] == ("warning", f"«FOTOS» vuelve a estar en {old}: no hace falta localizarla.")
        assert location() == ("FOTOS", str(old), 0) and state["reloads"] == 1
        print("5. El disco ha vuelto entre medias: el aviso, y nada")

        # 6. Los textos con muchos archivos (con punto de miles) y con uno
        many = LocationRelocation(1, "A", str(old), str(new), "A", 22607, 1000, 998)
        assert "Se han comprobado 1.000 de sus 22.607 archivos: se encuentran 998." in question_text(many)
        one = LocationRelocation(1, "A", str(old), str(new), "A", 1, 1, 1)
        assert "Se encuentra su único archivo." in question_text(one)
        print(f"\n--- Ejemplo ---\n{question_text(many)}\n---")
        conn.close()
    window.deleteLater()
    app.processEvents()
    print("Autoprueba finalizada correctamente.")
