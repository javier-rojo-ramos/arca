"""El aspecto de los tracks que elige el usuario: colores del mapa y la pendiente del perfil.

Se elige en Opciones > Tracks (y la pendiente, también con el botón derecho sobre el
perfil) y se guarda en settings.json. Este módulo lee lo guardado y lo valida: lo que
falte o no valga (un color mal escrito, un modo que no existe) se cambia por lo de
partida, los colores del tema ('COLORS.map_track_active' y 'COLORS.map_track'), la
pendiente en el área y el texto de los waypoints al recorrer el perfil, activado. Lo usan
el controlador del mapa (los colores), la banda del perfil (la pendiente y los waypoints)
y la página de Opciones.

    track_colors(config)          -> TrackColors("#e5383b", "#2f6fd6")
    track_colors_to_settings(...) -> {} (si son los del tema) o {"active": ..., "track": ...}
    slope_mode(config)            -> SlopeMode.AREA
    profile_waypoint_tips(config) -> True

1.1.0 'profile_waypoint_tips': el texto de los waypoints también al recorrer el perfil
      (22/11/2026).
1.0.0 Primera versión (15/11/2026; Opciones > Tracks, tras el paso 5.3b).

Prueba rápida (desde la raíz del proyecto):
    python -m ui_helpers.helpers.track_appearance
"""

__version__ = "1.1.0"
__all__ = [
    "TrackColors",
    "default_track_colors",
    "is_hex_color",
    "profile_waypoint_tips",
    "slope_mode",
    "track_colors",
    "track_colors_to_settings",
]

# Librerías estándar
import re
from dataclasses import dataclass
from typing import Any

# Módulos del proyecto
from config.app_constants import (
    SETTING_MAP_TRACK_COLORS,
    SETTING_PROFILE_SLOPE_MODE,
    SETTING_PROFILE_WAYPOINT_TIPS,
)
from ui_helpers.helpers.profile_style import SlopeMode
from ui_helpers.helpers.ui_theme import COLORS

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


@dataclass(frozen=True, slots=True)
class TrackColors:
    """Colores de los tracks en el mapa ("#rrggbb").

    Attributes:
        active: El track elegido (el activo).
        track: Los demás tracks.
    """

    active: str
    track: str


def is_hex_color(value: object) -> bool:
    """True si es un color "#rrggbb" (opaco: los tracks no se guardan translúcidos)."""
    return isinstance(value, str) and _HEX_COLOR.fullmatch(value) is not None


def default_track_colors() -> TrackColors:
    """Los colores de partida: los del tema."""
    return TrackColors(COLORS.map_track_active, COLORS.map_track)


def track_colors(config: Any) -> TrackColors:
    """Los colores de los tracks guardados (los del tema, para lo que falte o no valga)."""
    saved = config.get(SETTING_MAP_TRACK_COLORS)
    saved = saved if isinstance(saved, dict) else {}
    default = default_track_colors()
    active, track = saved.get("active"), saved.get("track")
    return TrackColors(
        active.lower() if is_hex_color(active) else default.active,
        track.lower() if is_hex_color(track) else default.track,
    )


def track_colors_to_settings(colors: TrackColors) -> dict[str, str]:
    """Lo que se guarda: solo los colores que no son los del tema (vacío = los del tema;
    así, si un día cambia el tema, lo no elegido lo sigue)."""
    default = default_track_colors()
    saved: dict[str, str] = {}
    if colors.active.lower() != default.active.lower():
        saved["active"] = colors.active.lower()
    if colors.track.lower() != default.track.lower():
        saved["track"] = colors.track.lower()
    return saved


def slope_mode(config: Any) -> SlopeMode:
    """Cómo se ve la pendiente en el perfil (en el área, si no hay nada o no vale)."""
    try:
        return SlopeMode(config.get(SETTING_PROFILE_SLOPE_MODE))
    except ValueError:
        return SlopeMode.AREA


def profile_waypoint_tips(config: Any) -> bool:
    """Si, al recorrer el perfil con el ratón, sale en el mapa el texto del waypoint por el
    que pasa el punto ámbar (sí, si no hay nada guardado o no es un sí o un no)."""
    value = config.get(SETTING_PROFILE_WAYPOINT_TIPS)
    return value if isinstance(value, bool) else True


if __name__ == "__main__":
    # Autoprueba (sin ventanas). Ejecutar desde la raíz:
    #   python -m ui_helpers.helpers.track_appearance

    class _Config(dict):
        def set(self, key: str, value: Any) -> None:
            self[key] = value

    default = default_track_colors()
    assert is_hex_color(default.active) and is_hex_color(default.track)
    assert default.active != default.track

    # Sin nada guardado, o con algo que no vale: los del tema
    assert track_colors(_Config()) == default
    assert track_colors(_Config({SETTING_MAP_TRACK_COLORS: "rojo"})) == default
    bad = {"active": "red", "track": "#12345", "otra": "#000000"}
    assert track_colors(_Config({SETTING_MAP_TRACK_COLORS: bad})) == default
    # Uno elegido y el otro no
    chosen = track_colors(_Config({SETTING_MAP_TRACK_COLORS: {"active": "#00AA55"}}))
    assert chosen == TrackColors("#00aa55", default.track)
    # Lo que se guarda: solo lo que no es del tema
    assert track_colors_to_settings(default) == {}
    assert track_colors_to_settings(chosen) == {"active": "#00aa55"}
    assert track_colors_to_settings(TrackColors(default.active.upper(), "#FFFFFF")) == {
        "track": "#ffffff"
    }
    for value in ("#a1b2c3", "#A1B2C3"):
        assert is_hex_color(value)
    for value in ("a1b2c3", "#a1b2c", "#a1b2c3ff", "#gggggg", None, 123):
        assert not is_hex_color(value), value

    # La pendiente
    assert slope_mode(_Config()) is SlopeMode.AREA
    assert slope_mode(_Config({SETTING_PROFILE_SLOPE_MODE: "line"})) is SlopeMode.LINE
    assert slope_mode(_Config({SETTING_PROFILE_SLOPE_MODE: "zigzag"})) is SlopeMode.AREA

    # El texto de los waypoints al recorrer el perfil: sí, salvo un no guardado
    assert profile_waypoint_tips(_Config()) is True
    assert profile_waypoint_tips(_Config({SETTING_PROFILE_WAYPOINT_TIPS: False})) is False
    assert profile_waypoint_tips(_Config({SETTING_PROFILE_WAYPOINT_TIPS: True})) is True
    for value in (0, "no", None, []):
        assert profile_waypoint_tips(_Config({SETTING_PROFILE_WAYPOINT_TIPS: value})) is True
    print("Autoprueba finalizada correctamente.")
