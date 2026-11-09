"""Ajustes personalizados de la barra de filtros: filtros guardados con un nombre.

Este módulo NO depende de Qt ni de la base de datos: describe los ajustes, los compara con
el filtro de un módulo y los guarda en una lista para settings.json.

Un ajuste ('FilterPreset') es un nombre y un 'GridFilter' con las pestañas encendidas y lo
que hay en ellas. Lo de las pestañas apagadas, las recordadas para Ctrl+L y el candado no
se guardan. Hay UNA lista para toda la aplicación (todos los módulos y catálogos), en el
orden en que se ve en el desplegable; cada módulo muestra solo los ajustes que le valen.

Qué hace cada cosa:
    - 'presets_from_config' / 'presets_to_config': leer y guardar la lista. Sin lista
      guardada (None), los ajustes de fábrica ('factory_presets'); una lista vacía es que
      el usuario los ha borrado todos.
    - 'preset_from_filter': el ajuste que guarda el filtro de un módulo («Guardar filtro
      activo como nuevo ajuste personalizado»). Si «Metadatos» aún tiene las columnas de
      partida (sin elegir), se guardan con sus campos: así el ajuste es igual en cualquier
      módulo.
    - 'with_preset_saved': la lista con el ajuste al final o, si ya hay uno con ese nombre
      ('find_preset': sin distinguir mayúsculas), en su lugar (reemplazado).
    - 'applied_preset': el filtro del módulo tras elegir un ajuste: sus pestañas y lo que
      hay en ellas. Las pestañas que el ajuste no enciende conservan lo que tenían
      (apagadas no filtran, como con «Ninguno») y el candado sigue como estaba.
    - 'reset_filter': «Restaurar filtro activo a sus valores por defecto»: vacía «Texto»,
      «Atributos» y «Metadatos» (que vuelve a las columnas de partida del módulo); las
      pestañas encendidas y el candado no cambian. 'is_reset' dice si ya está así.
    - 'matching_preset': el ajuste que coincide con el filtro (su nombre va en el botón
      del desplegable), comparando solo lo que filtra: las pestañas encendidas y lo que
      hay en ellas.
    - 'fits_module': si un ajuste vale para un módulo (las columnas de «Metadatos» y los
      tipos de «Atributos» que enciende son de los tipos del módulo). Uno con «Objetivo»
      no vale en un módulo sin fotos.
    - 'with_factory_restored': la lista con los ajustes de fábrica que falten, al final.

Las columnas de «Metadatos» VACÍAS ('MetadataFilter()') son «las de partida del módulo»:
cada módulo pone las suyas ('AppModule.filter_metadata_fields'). Por eso las funciones que
comparan reciben esos campos ('default_fields'). Así guarda sus columnas el ajuste de
fábrica «Columnas de partida»: en cada módulo, las suyas.

Ajustes de fábrica (decididos por el autor el 09/11/2026; después son como los demás: se
pueden borrar, renombrar y ordenar):
    «Columnas de partida»   «Metadatos» con las columnas de partida del módulo
    «Ubicación»             «Metadatos»: País, Región o provincia, Ciudad y Lugar
    «Datos de exposición»   «Metadatos»: Objetivo, Distancia focal, Tiempo de exposición y
                            Apertura (como el de Lightroom; solo donde hay fotos)
    «Valoradas»             «Atributos»: 1 estrella o más
    «Marcadas»              «Atributos»: marcadas (escogidas)

Uso:
    presets = presets_from_config(config.get(SETTING_FILTER_PRESETS))
    shown = [p for p in presets if fits_module(p, media_types)]
    current = matching_preset(grid_filter, presets, media_types, default_fields)
    new_filter = applied_preset(preset, grid_filter)
    preset = preset_from_filter("Bodas", grid_filter, default_fields)
    config.set(SETTING_FILTER_PRESETS, presets_to_config(with_preset_saved(presets, preset)))

1.0.0 Primera versión (paso A.3, filtros personalizados, subpaso 1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.filter_presets
"""

__version__ = "1.0.0"
__all__ = [
    "MAX_PRESET_NAME",
    "FilterPreset",
    "applied_preset",
    "clean_name",
    "factory_presets",
    "find_preset",
    "fits_module",
    "is_reset",
    "matching_preset",
    "preset_from_filter",
    "presets_from_config",
    "presets_to_config",
    "reset_filter",
    "with_factory_restored",
    "with_preset_saved",
]

# Librerías estándar
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any

# Módulos del proyecto
from core.catalog.grid_filter import (
    FILTER_ATTRIBUTES,
    FILTER_METADATA,
    FILTER_TEXT,
    NO_ATTRIBUTES,
    AttributeFilter,
    GridFilter,
    MetadataFilter,
    TextFilter,
    filter_from_dict,
    filter_to_dict,
)
from core.catalog.smart_fields import FIELDS

# Lo más largo que puede ser un nombre (cabe en el botón del desplegable sin recortarlo)
MAX_PRESET_NAME = 60

# Lo que se guarda de un filtro en un ajuste (sin 'remembered' ni 'locked')
_STORED_KEYS = ("active", "text", "attributes", "metadata")


@dataclass(frozen=True, slots=True)
class FilterPreset:
    """Un ajuste personalizado.

    Attributes:
        name: Nombre (sin espacios de sobra; único en la lista sin distinguir mayúsculas).
        grid_filter: Las pestañas encendidas y lo que hay en ellas (lo demás, con su valor
            de partida; candado abierto).
    """

    name: str
    grid_filter: GridFilter


def _factory() -> tuple[FilterPreset, ...]:
    """Los ajustes de fábrica, en su orden (ver la cabecera)."""
    metadata_on = frozenset({FILTER_METADATA})
    attributes_on = frozenset({FILTER_ATTRIBUTES})
    return (
        FilterPreset("Columnas de partida", GridFilter(active=metadata_on)),
        FilterPreset("Ubicación", GridFilter(
            active=metadata_on,
            metadata=MetadataFilter.from_fields(("country", "region", "city", "sublocation")),
        )),
        FilterPreset("Datos de exposición", GridFilter(
            active=metadata_on,
            metadata=MetadataFilter.from_fields(
                ("lens_model", "focal_length", "exposure_time", "f_number")
            ),
        )),
        FilterPreset("Valoradas", GridFilter(
            active=attributes_on, attributes=AttributeFilter(rating=1, rating_operator="gte"),
        )),
        FilterPreset("Marcadas", GridFilter(
            active=attributes_on, attributes=AttributeFilter(flags=frozenset({1})),
        )),
    )  # fmt: skip


def factory_presets() -> list[FilterPreset]:
    """Los ajustes de fábrica (los que hay mientras el usuario no cambia la lista)."""
    return list(_factory())


# -----------------------------------------------------------------------------
# Nombres
# -----------------------------------------------------------------------------


def clean_name(name: str) -> str:
    """El nombre sin espacios de sobra y como mucho de 'MAX_PRESET_NAME' caracteres.

    Raises:
        ValueError: Si queda vacío.
    """
    cleaned = " ".join(str(name).split())[:MAX_PRESET_NAME].strip()
    if not cleaned:
        raise ValueError("El ajuste necesita un nombre.")
    return cleaned


def _name_key(name: str) -> str:
    """Lo que se compara de un nombre: sin espacios de sobra ni mayúsculas."""
    return " ".join(name.split()).casefold()


def find_preset(presets: Sequence[FilterPreset], name: str) -> int | None:
    """La posición del ajuste con ese nombre (sin distinguir mayúsculas), o None."""
    key = _name_key(name)
    return next((i for i, p in enumerate(presets) if _name_key(p.name) == key), None)


# -----------------------------------------------------------------------------
# Filtros
# -----------------------------------------------------------------------------


def _resolved_metadata(metadata: MetadataFilter, default_fields: Iterable[str]) -> MetadataFilter:
    """Las columnas tal como se ven: las vacías son las de partida del módulo."""
    return metadata if metadata.columns else MetadataFilter.from_fields(default_fields)


def _stored_filter(grid_filter: GridFilter) -> GridFilter:
    """Lo que guarda un ajuste: las pestañas encendidas y lo que hay en ellas; lo demás,
    con su valor de partida (candado abierto, nada recordado para Ctrl+L)."""
    active = grid_filter.active
    return GridFilter(
        active=active,
        text=grid_filter.text if FILTER_TEXT in active else TextFilter(),
        attributes=grid_filter.attributes if FILTER_ATTRIBUTES in active else NO_ATTRIBUTES,
        metadata=grid_filter.metadata if FILTER_METADATA in active else MetadataFilter(),
    )


def _signature(grid_filter: GridFilter, default_fields: Iterable[str]) -> tuple[Any, ...]:
    """Lo que se compara para saber si un filtro coincide con un ajuste: las pestañas
    encendidas y lo que hay en ellas (lo escrito en una pestaña apagada no filtra)."""
    active = grid_filter.active
    return (
        active,
        grid_filter.text if FILTER_TEXT in active else None,
        grid_filter.attributes if FILTER_ATTRIBUTES in active else None,
        _resolved_metadata(grid_filter.metadata, default_fields)
        if FILTER_METADATA in active else None,
    )  # fmt: skip


def preset_from_filter(
    name: str, grid_filter: GridFilter, default_fields: Iterable[str]
) -> FilterPreset:
    """El ajuste que guarda el filtro de un módulo. Las columnas de partida de «Metadatos»
    (sin elegir) se guardan con los campos del módulo ('default_fields'): quien guarda
    ve esas columnas y las espera igual en cualquier otro módulo.

    Raises:
        ValueError: Si el nombre queda vacío o el filtro está en «Ninguno» (no hay nada
            que guardar).
    """
    if grid_filter.is_none:
        raise ValueError("Con «Ninguno» no hay filtro que guardar.")
    stored = _stored_filter(grid_filter)
    if FILTER_METADATA in stored.active:
        stored = replace(stored, metadata=_resolved_metadata(stored.metadata, default_fields))
    return FilterPreset(clean_name(name), stored)


def with_preset_saved(
    presets: Sequence[FilterPreset], preset: FilterPreset
) -> list[FilterPreset]:
    """La lista con el ajuste guardado: en el lugar del que tenga su nombre (reemplazado,
    con el nombre como se ha escrito ahora) o, si no hay ninguno, al final."""
    result = list(presets)
    index = find_preset(result, preset.name)
    if index is None:
        result.append(preset)
    else:
        result[index] = preset
    return result


def applied_preset(preset: FilterPreset, current: GridFilter) -> GridFilter:
    """El filtro del módulo tras elegir el ajuste: sus pestañas, encendidas, con lo que
    guarda; las demás, apagadas y con lo que tenían; el candado y lo recordado para Ctrl+L,
    como estaban."""
    stored = preset.grid_filter
    active = stored.active
    return replace(
        current,
        active=active,
        text=stored.text if FILTER_TEXT in active else current.text,
        attributes=stored.attributes if FILTER_ATTRIBUTES in active else current.attributes,
        metadata=stored.metadata if FILTER_METADATA in active else current.metadata,
    )


def reset_filter(current: GridFilter) -> GridFilter:
    """«Restaurar filtro activo a sus valores por defecto»: «Texto», «Atributos» y
    «Metadatos» vacíos (con las columnas de partida del módulo), también los de las
    pestañas apagadas. Las pestañas encendidas, lo recordado y el candado no cambian."""
    return replace(current, text=TextFilter(), attributes=NO_ATTRIBUTES, metadata=MetadataFilter())


def is_reset(current: GridFilter, default_fields: Iterable[str]) -> bool:
    """Si ya está como lo deja 'reset_filter' (no hay nada que restaurar). Unas columnas
    iguales a las de partida y sin nada elegido cuentan como las de partida."""
    fields = tuple(default_fields)
    return (
        current.text == TextFilter()
        and current.attributes == NO_ATTRIBUTES
        and _resolved_metadata(current.metadata, fields) == MetadataFilter.from_fields(fields)
    )


def fits_module(preset: FilterPreset, media_types: Iterable[str]) -> bool:
    """Si el ajuste vale para un módulo con esos tipos ('AppModule.filter_media_types'):
    los tipos que elige en «Atributos» y los campos de sus columnas de «Metadatos» (los de
    un grupo con tipos, como «Imagen») son de los del módulo."""
    types = frozenset(media_types)
    stored = preset.grid_filter
    if FILTER_ATTRIBUTES in stored.active and not stored.attributes.media_types <= types:
        return False
    if FILTER_METADATA in stored.active:
        for column in stored.metadata.columns:
            field_types = FIELDS[column.field].media_types
            if field_types and not types & set(field_types):
                return False
    return True


def matching_preset(
    grid_filter: GridFilter,
    presets: Sequence[FilterPreset],
    media_types: Iterable[str],
    default_fields: Iterable[str],
) -> FilterPreset | None:
    """El primer ajuste (de los que valen para el módulo) que coincide con el filtro, o
    None. Con «Ninguno», ninguno: un ajuste siempre enciende alguna pestaña."""
    if grid_filter.is_none:
        return None
    types, fields = tuple(media_types), tuple(default_fields)
    wanted = _signature(grid_filter, fields)
    for preset in presets:
        if fits_module(preset, types) and _signature(preset.grid_filter, fields) == wanted:
            return preset
    return None


def with_factory_restored(presets: Sequence[FilterPreset]) -> list[FilterPreset]:
    """La lista con los ajustes de fábrica que falten (por su nombre), al final. Los del
    usuario no cambian, aunque uno se llame como uno de fábrica."""
    result = list(presets)
    for preset in _factory():
        if find_preset(result, preset.name) is None:
            result.append(preset)
    return result


# -----------------------------------------------------------------------------
# Guardado (settings.json)
# -----------------------------------------------------------------------------


def presets_to_config(presets: Iterable[FilterPreset]) -> list[dict[str, Any]]:
    """La lista para settings.json: nombre y filtro de cada ajuste, en su orden."""
    result: list[dict[str, Any]] = []
    for preset in presets:
        data = filter_to_dict(preset.grid_filter)
        result.append({"name": preset.name, "filter": {k: data[k] for k in _STORED_KEYS}})
    return result


def presets_from_config(value: object) -> list[FilterPreset]:
    """Lee la lista guardada. Sin lista (None, o algo que no es una lista), los de
    fábrica. Lo que no se entienda (sin nombre, sin pestañas encendidas, un nombre
    repetido) se salta: nunca falla."""
    if not isinstance(value, list):
        return factory_presets()
    result: list[FilterPreset] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        try:
            name = clean_name(item["name"])
        except ValueError:
            continue
        stored = _stored_filter(filter_from_dict(item.get("filter")))
        if stored.is_none or find_preset(result, name) is not None:
            continue
        result.append(FilterPreset(name, stored))
    return result


if __name__ == "__main__":
    # Autoprueba (sin base de datos). Ejecutar desde la raíz:  python -m core.catalog.filter_presets
    import json

    from core.catalog.grid_filter import NO_FILTER, MetadataColumn

    CATALOG_TYPES = ("photo", "video", "audio", "track")
    IMAGE_TYPES = ("photo", "video")
    IMAGE_FIELDS = ("captured_at", "camera_model", "lens_model")

    def names(presets: Iterable[FilterPreset]) -> list[str]:
        return [p.name for p in presets]

    # 1. De fábrica: sin lista guardada; todos encienden algo y valen en el Catálogo e Imagen
    factory = presets_from_config(None)
    assert names(factory) == [
        "Columnas de partida", "Ubicación", "Datos de exposición", "Valoradas", "Marcadas",
    ], names(factory)
    assert presets_from_config("estropeado") == factory
    assert all(not p.grid_filter.is_none for p in factory)
    assert all(fits_module(p, CATALOG_TYPES) and fits_module(p, IMAGE_TYPES) for p in factory)
    # En un módulo sin fotos (un futuro Audio) no sale «Datos de exposición»
    audio = [p.name for p in factory if fits_module(p, ("audio",))]
    assert audio == ["Columnas de partida", "Ubicación", "Valoradas", "Marcadas"], audio

    # 2. Ida y vuelta por settings.json (también con JSON de verdad); el usuario los borró todos
    saved = json.loads(json.dumps(presets_to_config(factory)))
    assert presets_from_config(saved) == factory
    assert set(saved[0]["filter"]) == set(_STORED_KEYS)  # sin candado ni lo recordado
    assert presets_from_config([]) == []

    # 3. Guardar el filtro de un módulo: solo las pestañas encendidas y lo que hay en ellas
    current = GridFilter(
        active=frozenset({FILTER_ATTRIBUTES, FILTER_METADATA}),
        remembered=frozenset({FILTER_TEXT}),
        locked=True,
        text=TextFilter(text="boda"),  # «Texto» apagada: no se guarda
        attributes=AttributeFilter(rating=3),
    )  # «Metadatos» con las columnas de partida (aún sin elegir)
    mine = preset_from_filter("  Mis   bodas ", current, IMAGE_FIELDS)
    assert mine.name == "Mis bodas"
    stored = mine.grid_filter
    assert stored.active == current.active and not stored.locked and not stored.remembered
    assert stored.text == TextFilter() and stored.attributes == current.attributes
    # Las columnas de partida se guardan con sus campos: en otro módulo, las mismas
    assert [c.field for c in stored.metadata.columns] == list(IMAGE_FIELDS)
    assert len(preset_from_filter("x" * 200, current, IMAGE_FIELDS).name) == MAX_PRESET_NAME
    for bad_name, bad_filter in (("   ", current), ("Nada", NO_FILTER)):
        try:
            preset_from_filter(bad_name, bad_filter, IMAGE_FIELDS)
            raise AssertionError("debía rechazarlo")
        except ValueError:
            pass

    # 4. Guardar con un nombre que ya existe (sin distinguir mayúsculas): en su lugar
    presets = with_preset_saved(factory, mine)
    assert names(presets)[-1] == "Mis bodas" and len(presets) == 6
    assert find_preset(presets, "mis BODAS") == 5 and find_preset(presets, "Otra") is None
    other = preset_from_filter("UBICACIÓN", current, IMAGE_FIELDS)
    replaced = with_preset_saved(presets, other)
    assert len(replaced) == 6 and replaced[1] == other

    # 5. Elegir un ajuste: sus pestañas; las demás conservan lo que tenían; candado igual
    location = presets[1]
    applied = applied_preset(location, current)
    assert applied.active == {FILTER_METADATA} and applied.locked
    assert applied.text == current.text and applied.attributes == current.attributes
    assert [c.field for c in applied.metadata.columns] == [
        "country", "region", "city", "sublocation",
    ]
    assert applied.remembered == current.remembered

    # 6. Qué ajuste coincide (el nombre del botón)
    def match(grid_filter: GridFilter, fields: tuple[str, ...] = IMAGE_FIELDS) -> str | None:
        found = matching_preset(grid_filter, presets, IMAGE_TYPES, fields)
        return found.name if found else None

    assert match(applied) == "Ubicación"
    # Lo escrito en una pestaña apagada no cuenta; encenderla, sí
    assert match(replace(applied, text=TextFilter(text="otra"))) == "Ubicación"
    assert match(applied.with_panel(FILTER_TEXT, True)) is None
    # Elegir un valor en una columna: ya no coincide
    chosen = replace(applied, metadata=applied.metadata.with_values(0, ["España"]))
    assert match(chosen) is None
    # «Ninguno»: ninguno, aunque lo de dentro sea igual
    assert match(applied.cleared()) is None
    # «Columnas de partida»: las vacías o las mismas con sus campos, en cada módulo
    metadata_only = GridFilter(active=frozenset({FILTER_METADATA}))
    assert match(metadata_only) == "Columnas de partida"
    explicit = replace(metadata_only, metadata=MetadataFilter.from_fields(IMAGE_FIELDS))
    assert match(explicit) == "Columnas de partida"
    assert match(explicit, ("media_type", "captured_at", "keyword")) is None
    # El mío (guardado en Imagen) coincide con lo que guardó
    assert match(applied_preset(mine, current)) == "Mis bodas"
    # Un ajuste que no vale en el módulo no coincide
    exposure = applied_preset(presets[2], NO_FILTER)
    assert matching_preset(exposure, presets, ("audio",), ()) is None
    assert matching_preset(exposure, presets, IMAGE_TYPES, IMAGE_FIELDS) == presets[2]

    # 7. Restaurar: todo vacío (también lo de las pestañas apagadas); pestañas y candado igual
    assert not is_reset(current, IMAGE_FIELDS)
    restored = reset_filter(chosen)
    assert restored.active == chosen.active and restored.locked
    assert restored.text == TextFilter() and restored.metadata == MetadataFilter()
    assert is_reset(restored, IMAGE_FIELDS) and is_reset(explicit, IMAGE_FIELDS)
    assert not is_reset(explicit, ("media_type",))  # otras columnas que las de partida
    picked = replace(explicit, metadata=explicit.metadata.with_values(0, ["2026"]))
    assert not is_reset(picked, IMAGE_FIELDS)

    # 8. Ajustes de fábrica que falten: al final; los del usuario no cambian
    edited = [p for p in presets if p.name != "Ubicación"]
    edited = [replace(p, name="Con estrellas") if p.name == "Valoradas" else p for p in edited]
    restored_list = with_factory_restored(edited)
    assert names(restored_list) == [
        "Columnas de partida", "Datos de exposición", "Con estrellas", "Marcadas", "Mis bodas",
        "Ubicación", "Valoradas",
    ], names(restored_list)
    assert with_factory_restored(restored_list) == restored_list
    assert with_factory_restored(replaced)[1] == other  # «UBICACIÓN» (mío) se queda

    # 9. Lo estropeado de settings.json se salta sin fallar
    junk = presets_from_config([
        1, {"name": 5}, {"name": "   ", "filter": saved[0]["filter"]},
        {"name": "Sin pestañas", "filter": {"active": []}},
        {"name": "Bueno", "filter": {"active": ["text", "otra"], "locked": True,
                                     "text": {"text": "boda"}, "attributes": {"rating": 4}}},
        {"name": "BUENO", "filter": saved[1]["filter"]},
        {"name": "Columnas", "filter": {"active": ["metadata"], "metadata": {"columns": [
            {"field": "no_existe"}, {"field": "city", "values": ["Huesca", None, [1]]}]}}},
    ])  # fmt: skip
    assert names(junk) == ["Bueno", "Columnas"], names(junk)
    good = junk[0].grid_filter
    assert good.active == {FILTER_TEXT} and not good.locked and good.text.text == "boda"
    assert good.attributes == NO_ATTRIBUTES  # «Atributos» apagada: no se guarda
    city = MetadataColumn("city", frozenset({"Huesca", None}))
    assert junk[1].grid_filter.metadata.columns == (city,)

    print("Autoprueba finalizada correctamente.")
