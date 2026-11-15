"""El encuadre del mapa de cada módulo, recordado con lo que tenía elegido (sin Qt).

Hay un solo mapa para todos los módulos. Para que cada uno vuelva a su encuadre (al
arrancar, al volver de otro módulo), 'MapController' apunta aquí, cada vez que el mapa se
queda quieto, el centro y el zoom del módulo activo junto con el origen que se estaba
viendo (decidido por el autor el 15/11/2026):
    - Al volver a pintar ese módulo con el MISMO origen, el mapa vuelve a ese encuadre.
    - Con otro origen (se eligió otra cosa en la barra), no vale: se encuadra todo, como
      siempre. Solo se recuerda el último encuadre de cada módulo.
    - Se guarda por catálogo, al cerrar, en la entrada del catálogo del estado de los
      módulos ('ModuleHost.save_state(..., extra)'; clave 'map_framing').

El origen se compara como lo guarda 'grid_source.source_to_dict' (sin 'include_subfolders',
que decide la opción del momento): así vale igual el recordado en memoria que el leído de
settings.json.

Uso:
    framing = MapFraming.from_state(entrada.get("map_framing"))   # al abrir el catálogo
    framing.remember("tracks", origen, latitud, longitud, zoom)   # el mapa, quieto
    framing.view_for("tracks", origen)                            # (lat, lon, zoom) o None
    {"map_framing": framing.to_state()}                           # al cerrar

1.0.0 Primera versión (15/11/2026).

Prueba rápida (desde la raíz del proyecto):
    python -m controllers.map_framing
"""

__version__ = "1.0.0"
__all__ = ["FRAMING_STATE_KEY", "MapFraming"]

# Librerías estándar
from typing import Any

# Módulos del proyecto
from core.catalog.grid_source import GridSource, source_to_dict
from ui_helpers.map.map_types import is_valid_position

# Clave en la entrada de cada catálogo del estado de los módulos (settings.json)
FRAMING_STATE_KEY = "map_framing"

# Zoom que se acepta al leer lo guardado (el de los mapas de teselas)
_MIN_ZOOM, _MAX_ZOOM = 0.0, 22.0

# Un encuadre: (latitud, longitud, zoom)
View = tuple[float, float, float]


def _number(value: object) -> float | None:
    """El número que se guardó (no un booleano), o None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class MapFraming:
    """El último encuadre del mapa de cada módulo, con su origen (ver el docstring del archivo)."""

    def __init__(self) -> None:
        # módulo -> (origen en forma de diccionario, encuadre)
        self._views: dict[str, tuple[dict[str, Any], View]] = {}

    def remember(
        self, module: str, source: GridSource, latitude: float, longitude: float, zoom: float
    ) -> None:
        """Apunta el encuadre del módulo con el origen que se ve (sustituye al anterior).
        Un módulo vacío o un encuadre imposible no se apuntan."""
        if not module or not is_valid_position(latitude, longitude):
            return
        if not _MIN_ZOOM <= zoom <= _MAX_ZOOM:
            return
        view = (round(latitude, 6), round(longitude, 6), round(zoom, 2))
        self._views[module] = (source_to_dict(source), view)

    def view_for(self, module: str, source: GridSource) -> View | None:
        """El encuadre recordado del módulo, si era de ese mismo origen (si no, None)."""
        saved = self._views.get(module)
        if saved is None or saved[0] != source_to_dict(source):
            return None
        return saved[1]

    def clear(self) -> None:
        """Olvida todos los encuadres (al cerrar el catálogo, ya guardados)."""
        self._views = {}

    def to_state(self) -> dict[str, Any]:
        """Para guardarlo en JSON: {módulo: {"source": {...}, "view": [lat, lon, zoom]}}."""
        return {
            module: {"source": source, "view": list(view)}
            for module, (source, view) in self._views.items()
        }

    @classmethod
    def from_state(cls, value: object) -> "MapFraming":
        """Lo guardado con 'to_state', comprobado: lo que no se entienda se ignora."""
        framing = cls()
        if not isinstance(value, dict):
            return framing
        for module, entry in value.items():
            if not isinstance(module, str) or not module or not isinstance(entry, dict):
                continue
            source, view = entry.get("source"), entry.get("view")
            if not isinstance(source, dict) or not isinstance(view, list) or len(view) != 3:
                continue
            latitude, longitude, zoom = (_number(item) for item in view)
            if latitude is None or longitude is None or zoom is None:
                continue
            if not is_valid_position(latitude, longitude) or not _MIN_ZOOM <= zoom <= _MAX_ZOOM:
                continue
            framing._views[module] = (dict(source), (latitude, longitude, zoom))
        return framing


if __name__ == "__main__":
    # Autoprueba (sin Qt). Desde la raíz del proyecto:  python -m controllers.map_framing
    import json

    from core.catalog.grid_source import folder_source, library_source

    tracks_all = library_source("tracks")
    ordesa = folder_source(1, "rutas/ordesa")

    # 1. Recordar y pedir: con el mismo origen, el encuadre; con otro, nada
    framing = MapFraming()
    framing.remember("tracks", ordesa, 42.6512345678, -0.0412345678, 13)
    assert framing.view_for("tracks", ordesa) == (42.651235, -0.041235, 13.0)
    assert framing.view_for("tracks", tracks_all) is None  # se eligió otra cosa
    assert framing.view_for("image", ordesa) is None  # otro módulo
    # La opción de las subcarpetas no cuenta (la decide el momento)
    assert framing.view_for("tracks", folder_source(1, "rutas/ordesa", include_subfolders=False))

    # 2. Solo el último de cada módulo; cada módulo, el suyo
    framing.remember("tracks", tracks_all, 42.0, 0.5, 9)
    framing.remember("image", ordesa, 40.0, -3.0, 6.5)
    assert framing.view_for("tracks", ordesa) is None
    assert framing.view_for("tracks", tracks_all) == (42.0, 0.5, 9.0)
    assert framing.view_for("image", ordesa) == (40.0, -3.0, 6.5)

    # 3. Lo imposible no se apunta (y no borra lo que había)
    framing.remember("tracks", tracks_all, 95.0, 0.0, 9)
    framing.remember("tracks", tracks_all, 42.0, 0.5, 40)
    framing.remember("", tracks_all, 42.0, 0.5, 9)
    assert framing.view_for("tracks", tracks_all) == (42.0, 0.5, 9.0)

    # 4. A JSON y de vuelta: lo mismo (también para los orígenes)
    state = json.loads(json.dumps(framing.to_state()))
    back = MapFraming.from_state(state)
    assert back.view_for("tracks", tracks_all) == (42.0, 0.5, 9.0)
    assert back.view_for("image", ordesa) == (40.0, -3.0, 6.5)
    assert back.to_state() == framing.to_state()

    # 5. Lo guardado que no se entiende se ignora, sin fallar
    for bad in (None, [], "x", {"tracks": "x"}, {"tracks": {"source": {}, "view": [1, 2]}},
                {"tracks": {"source": {}, "view": [95, 0, 3]}},
                {"tracks": {"source": {}, "view": [42, 0, True]}},
                {"tracks": {"source": "x", "view": [42, 0, 3]}}, {"": {"source": {}, "view": [42, 0, 3]}}):  # fmt: skip
        assert MapFraming.from_state(bad).to_state() == {}, bad

    # 6. Olvidar
    framing.clear()
    assert framing.to_state() == {} and framing.view_for("image", ordesa) is None

    print("Autoprueba finalizada correctamente.")
