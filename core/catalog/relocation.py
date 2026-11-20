"""«Localizar...»: decirle al catálogo dónde está ahora una ubicación (CAT 6.3).

Este módulo NO depende de Qt. Sus funciones reciben la conexión como primer parámetro, así
que se envían tal cual a 'CatalogDatabaseManager.execute_async' (el gestor hace el commit,
o el rollback si la función lanza una excepción).

Cuándo hace falta: una ubicación sale «desconectada» porque su carpeta raíz ya no está
donde estaba: un disco externo que vuelve con otra letra (E: -> F:), o la carpeta raíz
movida o renombrada fuera de la aplicación. Como todo lo de dentro (archivos, carpetas
apuntadas, «¿Qué contiene esta carpeta?», errores de lectura) guarda su ruta RELATIVA a la
ubicación, basta con cambiar la ruta de la raíz: todo conserva su 'id' y, con él, su
valoración, sus colecciones y sus miniaturas. Solo cambia el catálogo: en el disco no se
toca nada (docs/DECISIONES.md, 20/11/2026).

    plan = plan_location_relocation(conn, location_id, "F:/FOTOS")   # en segundo plano
    if plan.problem:                         -> no se puede (el texto es para el usuario)
    elif plan.total and not plan.found:      -> no está ninguno de sus archivos: no se sigue
    else:                                    -> preguntar (plan.checked, plan.found, plan.total)
        relocate_location(conn, plan)        # vuelve a comprobarlo y cambia ruta y nombre

Reglas (las de añadir una carpeta, 'storage_locations.register_folder'):
    - La carpeta nueva tiene que existir y la raíz antigua no (si está, la ubicación está
      conectada: no hay nada que localizar).
    - No puede estar dentro de otra ubicación ni contener otra (las ubicaciones nunca se
      solapan), ni estar dentro de la carpeta del propio catálogo.
    - Se mira si sus archivos están en la carpeta nueva: hasta 'SAMPLE_SIZE' (1 000),
      repartidos por toda la ubicación en el orden de sus rutas (mirar 20 000 uno a uno en
      un disco externo lento puede tardar decenas de segundos); si tiene menos, todos.
    - La ubicación pasa a llamarse como la carpeta nueva (decidido por el autor), con la
      regla de 'register_folder' (la raíz de una unidad, «F:\\», se llama así).

Después no se sincroniza nada (como en Lightroom): lo que falte se marca al verlo (o al
faltar su carpeta entera, CAT 6.2b) y lo nuevo entra al sincronizar la carpeta.

1.0.0 Primera versión (CAT 6.3): localizar una ubicación.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.relocation
"""

__version__ = "1.0.0"
__all__ = [
    "SAMPLE_SIZE",
    "LocationRelocation",
    "RelocationError",
    "plan_location_relocation",
    "relocate_location",
]

# Librerías estándar
import os
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Cuántos archivos se miran, como mucho, en la carpeta nueva
SAMPLE_SIZE = 1000


class RelocationError(Exception):
    """No se puede localizar la ubicación (el texto es para el usuario)."""


@dataclass(frozen=True, slots=True)
class LocationRelocation:
    """Lo que hay que saber antes de localizar una ubicación ('plan_location_relocation').

    Attributes:
        location_id: 'storage_locations.id'.
        name: Su nombre de ahora.
        old_path: Dónde estaba (la ruta absoluta guardada).
        new_path: Dónde está ahora (ruta absoluta); '' si la carpeta elegida no vale.
        new_name: Cómo se llamará (el nombre de la carpeta nueva).
        total: Sus archivos en el catálogo.
        checked: Cuántos se han mirado en la carpeta nueva (todos, o 'SAMPLE_SIZE').
        found: Cuántos de los mirados están.
        problem: Por qué no se puede (texto para el usuario), o None.
    """

    location_id: int
    name: str
    old_path: str
    new_path: str = ""
    new_name: str = ""
    total: int = 0
    checked: int = 0
    found: int = 0
    problem: str | None = None


def plan_location_relocation(
    conn: sqlite3.Connection,
    location_id: int,
    new_folder: str | Path,
    *,
    sample_size: int = SAMPLE_SIZE,
) -> LocationRelocation:
    """Comprueba la carpeta elegida y cuenta cuántos de sus archivos están en ella.

    Mira el disco: se llama en segundo plano ('execute_async'). No escribe nada.

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        location_id: 'storage_locations.id' de la ubicación desconectada.
        new_folder: La carpeta donde está ahora (la que ha elegido el usuario).
        sample_size: Cuántos archivos mirar, como mucho.

    Returns:
        El plan; si la carpeta no vale, con 'problem'.
    """
    row = conn.execute(
        "SELECT name, absolute_path FROM storage_locations WHERE id = ?", (location_id,)
    ).fetchone()
    if row is None:
        return LocationRelocation(location_id, "", "", problem="La ubicación ya no está en el catálogo.")
    plan = LocationRelocation(location_id, row[0], row[1])
    try:
        new_path = _checked_target(conn, plan, new_folder)
    except RelocationError as exc:
        return replace(plan, problem=str(exc))

    # En el orden de sus rutas: así la muestra se reparte por todas sus carpetas
    paths = [
        relative
        for (relative,) in conn.execute(
            "SELECT relative_path FROM media_items WHERE storage_location_id = ? "
            "ORDER BY relative_path",
            (location_id,),
        )
    ]
    sample = _spread(paths, sample_size)
    found = sum(1 for relative in sample if _is_file(new_path / relative))
    return replace(
        plan,
        new_path=str(new_path),
        new_name=_location_name(new_path),
        total=len(paths),
        checked=len(sample),
        found=found,
    )


def relocate_location(conn: sqlite3.Connection, plan: LocationRelocation) -> None:
    """Cambia la raíz de la ubicación (y su nombre) por la del plan. No hace 'commit'.

    Lo vuelve a comprobar todo antes, ya con la escritura bloqueada: el disco o el
    catálogo pueden haber cambiado desde que se calculó el plan (p. ej., el disco ha vuelto
    con su letra de siempre).

    Raises:
        RelocationError: Si el plan no vale o ya no vale (el texto es para el usuario).
    """
    if plan.problem is not None or not plan.new_path:
        raise RelocationError(plan.problem or "No se ha elegido ninguna carpeta.")
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")
    new_path = _checked_target(conn, plan, plan.new_path)
    cursor = conn.execute(
        "UPDATE storage_locations SET absolute_path = ?, name = ?, is_online = 1 WHERE id = ?",
        (str(new_path), plan.new_name, plan.location_id),
    )
    if cursor.rowcount != 1:
        raise RelocationError("La ubicación ya no está en el catálogo.")
    logger.info(
        f"Ubicación localizada: «{plan.name}» ({plan.old_path}) -> «{plan.new_name}» ({new_path})"
    )


def _checked_target(
    conn: sqlite3.Connection, plan: LocationRelocation, new_folder: str | Path
) -> Path:
    """La carpeta nueva, comprobada con las reglas de la cabecera.

    Raises:
        RelocationError: Si no vale (con el porqué, para el usuario).
    """
    if not str(new_folder).strip():
        raise RelocationError("No se ha elegido ninguna carpeta.")
    # Como 'storage_locations._normalize_folder': 'abspath' y no 'resolve', que cambiaría
    # una unidad de red mapeada (Z:\) por su ruta UNC, que el usuario no reconocería
    new_path = Path(os.path.abspath(new_folder))
    try:
        if not new_path.is_dir():
            raise RelocationError(f"{new_path} no existe o no es una carpeta.")
        if Path(plan.old_path).is_dir():
            raise RelocationError(
                f"«{plan.name}» vuelve a estar en {Path(plan.old_path)}: no hace falta "
                "localizarla."
            )
    except OSError as exc:
        raise RelocationError(f"No se pudo acceder a {new_path}: {exc}") from exc

    # Las ubicaciones nunca se solapan ('is_relative_to' compara por componentes de ruta:
    # '/Fotos2' no está dentro de '/Fotos')
    others = conn.execute(
        "SELECT name, absolute_path FROM storage_locations WHERE id != ?", (plan.location_id,)
    )
    for other_name, other_path in others:
        other = Path(other_path)
        if new_path.is_relative_to(other):
            raise RelocationError(
                f"{new_path} está dentro de otra ubicación del catálogo («{other_name}»)."
            )
        if other.is_relative_to(new_path):
            raise RelocationError(
                f"{new_path} contiene otra ubicación del catálogo («{other_name}»)."
            )
    catalog = _catalog_directory(conn)
    if catalog is not None and new_path.is_relative_to(catalog):
        raise RelocationError(f"{new_path} es la carpeta del catálogo o está dentro de ella.")
    return new_path


def _spread(paths: list[str], size: int) -> list[str]:
    """Hasta 'size' elementos repartidos por toda la lista (todos, si son menos)."""
    if len(paths) <= size:
        return paths
    return [paths[index * len(paths) // size] for index in range(size)]


def _is_file(path: Path) -> bool:
    """True si el archivo está (un error de acceso cuenta como que no)."""
    try:
        return path.is_file()
    except OSError:
        return False


def _location_name(path: Path) -> str:
    """Nombre de una ubicación: el de su carpeta (como 'register_folder'; «F:\\» en una unidad)."""
    return path.name or str(path)


def _catalog_directory(conn: sqlite3.Connection) -> Path | None:
    """Carpeta del catálogo (la que contiene el .db), o None si la base está en memoria."""
    for _sequence, schema_name, file_path in conn.execute("PRAGMA database_list;"):
        if schema_name == "main" and file_path:
            return Path(file_path).parent
    return None


if __name__ == "__main__":
    # Autoprueba con carpetas de verdad y una base de datos en un archivo (para la regla de
    # la carpeta del catálogo). Ejecutar desde la raíz del proyecto:
    #     python -m core.catalog.relocation
    import tempfile

    from core.catalog.catalog_schema import apply_migrations, configure_connection

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "Catalogo").mkdir()
        db = sqlite3.connect(base / "Catalogo" / "catalogo.db")
        configure_connection(db)
        apply_migrations(db)
        old = base / "E" / "FOTOS"  # ya no existe (el disco volvió con otra letra)
        new = base / "F" / "FOTOS2"
        (new / "sub").mkdir(parents=True)
        for relative in ("a.jpg", "sub/b.jpg"):
            (new / relative).write_bytes(b"x")
        other = base / "G" / "OTRA"
        other.mkdir(parents=True)
        db.execute(
            "INSERT INTO storage_locations(name, absolute_path, is_online) VALUES ('FOTOS', ?, 0)",
            (str(old),),
        )
        db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('OTRA', ?)", (str(other),))
        for relative in ("a.jpg", "sub/b.jpg", "sub/c.jpg"):  # c.jpg no está en la nueva
            db.execute(
                """INSERT INTO media_items(storage_location_id, relative_path, file_name,
                       media_type, mime_type, file_size, file_mtime_ns, title, rating)
                   VALUES (1, ?, ?, 'photo', 'image/jpeg', 1, 0, 'x', 3)""",
                (relative, relative.rsplit("/", 1)[-1]),
            )
        db.commit()

        # 1. La carpeta buena: 2 de 3, con el nombre nuevo
        plan = plan_location_relocation(db, 1, new)
        assert plan == LocationRelocation(1, "FOTOS", str(old), str(new), "FOTOS2", 3, 3, 2), plan
        assert plan_location_relocation(db, 1, new, sample_size=2).checked == 2  # una muestra
        assert _spread(list("abcdefghij"), 4) == list("acfh")
        print("1. Carpeta buena:", plan.found, "de", plan.total)

        # 2. Las que no valen (con su porqué)
        def problem(folder: Path | str) -> str | None:
            return plan_location_relocation(db, 1, folder).problem

        assert "no existe o no es una carpeta" in (problem(base / "Nada") or "")
        assert "está dentro de otra ubicación del catálogo («OTRA»)" in (problem(other) or "")
        (other / "dentro").mkdir()
        assert "está dentro de otra ubicación" in (problem(other / "dentro") or "")
        assert "contiene otra ubicación del catálogo («OTRA»)" in (problem(base / "G") or "")
        assert "es la carpeta del catálogo" in (problem(base / "Catalogo") or "")
        assert problem("") == "No se ha elegido ninguna carpeta."
        assert plan_location_relocation(db, 99, new).problem == "La ubicación ya no está en el catálogo."
        empty = base / "H" / "Vacía"
        empty.mkdir(parents=True)
        assert plan_location_relocation(db, 1, empty).found == 0  # no está ninguno: no se sigue
        print("2. Lo que no vale: inexistente, solapes, la del catálogo, ninguno")

        # 3. Localizar: ruta, nombre y conectada; lo de dentro, igual (mismo id y datos)
        try:
            relocate_location(db, replace(plan, problem="No"))
        except RelocationError as exc:
            assert str(exc) == "No"
        else:
            raise AssertionError("un plan con problema no se aplica")
        relocate_location(db, plan)
        db.commit()
        row = db.execute("SELECT name, absolute_path, is_online FROM storage_locations WHERE id = 1")
        assert row.fetchone() == ("FOTOS2", str(new), 1)
        items = db.execute("SELECT id, relative_path, rating FROM media_items ORDER BY id").fetchall()
        assert items == [(1, "a.jpg", 3), (2, "sub/b.jpg", 3), (3, "sub/c.jpg", 3)], items
        # Ya conectada: no hace falta localizarla
        assert "vuelve a estar en" in (problem(empty) or "")
        print("3. Localizada: ruta, nombre y conectada; los archivos, con lo suyo")

        # 4. Si el disco ha vuelto entre el plan y la orden: no se cambia nada
        db.execute(
            "UPDATE storage_locations SET absolute_path = ?, name = 'FOTOS', is_online = 0 WHERE id = 1",
            (str(old),),
        )
        db.commit()
        plan = plan_location_relocation(db, 1, new)
        old.mkdir(parents=True)  # vuelve con su letra de siempre
        try:
            relocate_location(db, plan)
        except RelocationError as exc:
            assert "vuelve a estar en" in str(exc), exc
        else:
            raise AssertionError("con la raíz de vuelta no se localiza")
        db.rollback()
        assert db.execute("SELECT absolute_path FROM storage_locations WHERE id = 1").fetchone() == (str(old),)
        # Una unidad entera se llama como la unidad
        assert _location_name(Path(os.path.abspath("/"))) == str(Path(os.path.abspath("/")))
        db.close()
        print("4. El disco ha vuelto entre medias: nada")
    print("Autoprueba finalizada correctamente.")
