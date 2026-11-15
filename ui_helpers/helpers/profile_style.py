"""Estilo del perfil de elevación: todo lo que se puede personalizar de su aspecto.

Este módulo NO depende de Qt: solo define valores. El perfil ('ElevationProfile', en
'ui_helpers/widgets/elevation_profile.py') se dibuja con un 'ProfileStyle' y se le puede
dar otro en cualquier momento ('set_style'). Así, más adelante, una página de Opciones
solo tendrá que construir un estilo con lo que elija el usuario (y guardarlo en
'settings.json'); el dibujo no cambia.

Qué lleva:
    - Los colores ('colors': un 'ProfileColors' de 'theme_colors.py'; los de partida son
      'ui_theme.PROFILE_COLORS').
    - Cómo se muestra la PENDIENTE ('slope_mode'): sin colores, coloreando el área bajo la
      curva (la línea va encima, en su color) o coloreando solo la línea. Por inclinación:
      subir o bajar un 20 % se pintan igual. Los umbrales ('slope_thresholds_pct') separan
      las franjas; hay un color más que umbrales. Con HISTÉRESIS
      ('slope_hysteresis_pct', 'slope_bands'): para cambiar de franja, la pendiente tiene
      que pasar el umbral por ese margen. Sin ella, una pendiente que ronda un umbral (4,9,
      5,1, 4,8 %...) cambia de color en cada punto y el área parece un código de barras.
    - Grosores, la rejilla, el cursor, la letra y qué partes se ven.

Uso:
    from dataclasses import replace
    from ui_helpers.helpers.profile_style import ProfileStyle, SlopeMode
    from ui_helpers.helpers.ui_theme import PROFILE_COLORS

    style = ProfileStyle(PROFILE_COLORS)
    style = replace(style, slope_mode=SlopeMode.LINE, line_width=2)
    style = replace(style, colors=replace(style.colors, background="#101010"))
    profile.set_style(style)

1.1.0 'SLOPE_MODE_TITLE' y 'SLOPE_MODE_LABELS': los textos de los modos, en un solo
      sitio (menú del perfil, Opciones > Tracks, ventana de prueba).
1.0.1 'slope_mode' admite el texto del modo ('"line"') y lo convierte en 'SlopeMode': desde
      el desplegable de la ventana de prueba llegaba como texto y el perfil salía sin
      colores en los tres modos (lo vio el autor).
1.0.0 Primera versión (15/11/2026; docs/MAPA.md, paso 5.2).

Prueba rápida (desde la raíz del proyecto):
    python -m ui_helpers.helpers.profile_style
"""

__version__ = "1.1.0"
__all__ = [
    "GRID_PATTERNS",
    "SLOPE_MODE_LABELS",
    "SLOPE_MODE_TITLE",
    "ProfileStyle",
    "SlopeMode",
    "slope_band",
    "slope_bands",
]

# Librerías estándar
import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

# Módulos del proyecto
from ui_helpers.helpers.theme_colors import ProfileColors

# Trazos de la rejilla: continua, a rayas, de puntos o sin rejilla
GRID_PATTERNS = ("solid", "dash", "dot", "none")


class SlopeMode(StrEnum):
    """Cómo se muestra la pendiente (el valor es el que se guarda en 'settings.json')."""

    OFF = "off"  # sin colores: el área y la línea en sus colores de siempre
    AREA = "area"  # el área bajo la curva, coloreada; la línea encima, en su color
    LINE = "line"  # solo la línea, coloreada (más gruesa); el área, en su color


# Textos de los modos, en el orden en que se ofrecen (el menú del perfil, Opciones >
# Tracks y la ventana de prueba del perfil dicen lo mismo)
SLOPE_MODE_TITLE = "Colores de la pendiente"
SLOPE_MODE_LABELS: dict[SlopeMode, str] = {
    SlopeMode.AREA: "En el área",
    SlopeMode.LINE: "En la línea",
    SlopeMode.OFF: "Sin colores",
}


@dataclass(frozen=True, slots=True)
class ProfileStyle:
    """El aspecto del perfil (ver el docstring del archivo).

    Attributes:
        colors: Los colores (fondo, rejilla, línea, cursor, pendiente...).
        slope_mode: Cómo se muestra la pendiente.
        slope_thresholds_pct: Umbrales de la pendiente en %, de menor a mayor: con
            (5, 10, 15, 20), las franjas son < 5, 5-10, 10-15, 15-20 y >= 20 %. Tiene que
            haber un color de la pendiente más que umbrales.
        slope_hysteresis_pct: Margen (puntos de %) que la pendiente tiene que pasar un
            umbral para cambiar de franja (0, sin histéresis). Elegido con los GPX del autor
            el 15/11/2026: con 2, las franjas siguen las rampas sin rayas sueltas.
        slope_area_opacity: Opacidad de los colores de la pendiente en el área (0 a 1):
            algo menos de 1 los suaviza sobre el fondo oscuro.
        line_width: Grosor de la línea de la curva (px).
        slope_line_width: Grosor de la línea cuando lleva los colores de la pendiente
            (más gruesa, para que se vean).
        grid_pattern: Trazo de la rejilla: uno de 'GRID_PATTERNS'.
        grid_width: Grosor de la rejilla (px).
        cursor_width: Grosor de la línea vertical del cursor (px; lleva además un borde
            oscuro de 1 px a cada lado).
        cursor_radius: Radio del círculo del cursor sobre la curva (px).
        font_point_size: Tamaño de la letra (puntos); None, el de la aplicación.
        show_header: Si se ve la línea de los totales (o del tramo elegido) arriba.
        show_segment_breaks: Si se marca con una raya dónde empieza otro segmento.
    """

    colors: ProfileColors
    slope_mode: SlopeMode = SlopeMode.AREA
    slope_thresholds_pct: tuple[float, ...] = (5.0, 10.0, 15.0, 20.0)
    slope_hysteresis_pct: float = 2.0
    slope_area_opacity: float = 0.85
    line_width: float = 1.5
    slope_line_width: float = 2.5
    grid_pattern: str = "dot"
    grid_width: float = 1.0
    cursor_width: float = 1.0
    cursor_radius: float = 4.5
    font_point_size: float | None = None
    show_header: bool = True
    show_segment_breaks: bool = True

    def __post_init__(self) -> None:
        """Comprueba que el estilo se puede dibujar (un error aquí es de programación).

        El modo de la pendiente se convierte en 'SlopeMode' aunque llegue como texto
        ('"line"'): así llega de un desplegable de Qt (un 'StrEnum' guardado con 'addItem'
        vuelve como 'str') y así llegará de 'settings.json'. Sin la conversión, el dibujo
        (que compara con 'is') no reconocería ningún modo y lo pintaría sin colores.
        """
        object.__setattr__(self, "slope_mode", SlopeMode(self.slope_mode))  # ValueError si no existe
        thresholds = self.slope_thresholds_pct
        if list(thresholds) != sorted(thresholds) or len(set(thresholds)) != len(thresholds):
            raise ValueError(f"Los umbrales de la pendiente, de menor a mayor: {thresholds}")
        if len(self.colors.slope) != len(thresholds) + 1:
            raise ValueError(
                f"Hacen falta {len(thresholds) + 1} colores de la pendiente "
                f"(uno más que umbrales); hay {len(self.colors.slope)}."
            )
        if self.grid_pattern not in GRID_PATTERNS:
            raise ValueError(f"Trazo de la rejilla desconocido: {self.grid_pattern!r}")
        if not 0 <= self.slope_area_opacity <= 1:
            raise ValueError(f"Opacidad fuera de 0-1: {self.slope_area_opacity}")
        if self.slope_hysteresis_pct < 0:
            raise ValueError(f"Histéresis negativa: {self.slope_hysteresis_pct}")


def slope_band(slope_pct: float, thresholds: Sequence[float]) -> int:
    """Franja de una pendiente (0 = la más suave), por inclinación: da igual que suba o
    que baje. -1 si no se conoce (NaN).

    Un valor justo en un umbral va a la franja de arriba: con (5, 10...), un 5 % es de la
    segunda.
    """
    if math.isnan(slope_pct):
        return -1
    steepness = abs(slope_pct)
    for band, threshold in enumerate(thresholds):
        if steepness < threshold:
            return band
    return len(thresholds)


def slope_bands(
    slopes: Sequence[float],
    segment_starts: Sequence[int],
    thresholds: Sequence[float],
    hysteresis_pct: float,
) -> list[int]:
    """La franja de cada punto de un perfil, con histéresis (-1, sin pendiente).

    Para subir de la franja b a la siguiente, la inclinación tiene que llegar a
    'thresholds[b] + hysteresis_pct'; para bajar, quedarse por debajo de
    'thresholds[b - 1] - hysteresis_pct'. Al empezar un segmento o tras un punto sin
    pendiente, la franja se decide sin histéresis. Con 'hysteresis_pct' = 0, lo mismo que
    'slope_band' punto a punto.
    """
    bands = [-1] * len(slopes)
    starts = set(segment_starts)
    top = len(thresholds)
    band = -1
    for i, value in enumerate(slopes):
        if i in starts or math.isnan(value):
            band = -1
            if math.isnan(value):
                continue
        steepness = abs(value)
        if band < 0:
            band = slope_band(value, thresholds)
        else:
            while band < top and steepness >= thresholds[band] + hysteresis_pct:
                band += 1
            while band > 0 and steepness < thresholds[band - 1] - hysteresis_pct:
                band -= 1
        bands[i] = band
    return bands


if __name__ == "__main__":
    # Autoprueba (sin Qt). Ejecutar desde la raíz:  python -m ui_helpers.helpers.profile_style
    from dataclasses import replace

    from ui_helpers.helpers.theme_colors import DARK_PROFILE

    style = ProfileStyle(DARK_PROFILE)
    assert style.slope_mode is SlopeMode.AREA and SlopeMode("line") is SlopeMode.LINE
    assert set(SLOPE_MODE_LABELS) == set(SlopeMode)  # un texto por modo
    # El modo como texto (de un desplegable de Qt o de settings.json) pasa a ser el miembro
    assert replace(style, slope_mode="line").slope_mode is SlopeMode.LINE  # type: ignore[arg-type]
    assert replace(style, slope_mode="off").slope_mode is SlopeMode.OFF  # type: ignore[arg-type]
    limits = style.slope_thresholds_pct

    # Franjas por inclinación: subir y bajar igual; el umbral, a la franja de arriba
    assert slope_band(0.0, limits) == 0 and slope_band(4.99, limits) == 0
    assert slope_band(5.0, limits) == 1 and slope_band(-7.0, limits) == 1
    assert slope_band(12.0, limits) == slope_band(-12.0, limits) == 2
    assert slope_band(19.9, limits) == 3 and slope_band(20.0, limits) == 4
    assert slope_band(-85.0, limits) == 4 and slope_band(math.nan, limits) == -1
    assert slope_band(3.0, ()) == 0  # sin umbrales, una sola franja

    # Histéresis: una pendiente que ronda el 5 % no cambia de franja; sí al pasarlo de verdad
    hovering = [4.0, 5.5, 4.8, 6.9, 4.1, 7.0, 7.5, 3.1, 2.9, 12.5, -12.0, -16.9, -17.0]
    with_margin = slope_bands(hovering, [0], limits, 2.0)
    assert with_margin == [0, 0, 0, 0, 0, 1, 1, 1, 0, 2, 2, 2, 3], with_margin
    # Sin margen, lo mismo que punto a punto
    assert slope_bands(hovering, [0], limits, 0.0) == [slope_band(s, limits) for s in hovering]
    # Un segmento nuevo o un hueco sin pendiente: la franja se decide de nuevo
    assert slope_bands([4.0, 6.0, 6.0], [0, 2], limits, 2.0) == [0, 0, 1]
    assert slope_bands([4.0, math.nan, 6.0], [0], limits, 2.0) == [0, -1, 1]
    assert slope_bands([], [], limits, 2.0) == []
    # Saltos grandes: varias franjas de una vez, en los dos sentidos
    assert slope_bands([1.0, 30.0, 1.0], [0], limits, 2.0) == [0, 4, 0]

    # Personalizar: otro modo, otro grosor, otro color
    custom = replace(style, slope_mode=SlopeMode.LINE, line_width=2.0)
    custom = replace(custom, colors=replace(custom.colors, background="#101010"))
    assert custom.colors.background == "#101010" and style.colors.background != "#101010"

    # Otros umbrales, con su número de colores
    three = replace(
        style,
        slope_thresholds_pct=(8.0, 16.0),
        colors=replace(style.colors, slope=("#00ff00", "#ffff00", "#ff0000")),
    )
    assert slope_band(10, three.slope_thresholds_pct) == 1

    # Lo que no se puede dibujar se rechaza al crearlo
    for wrong in (
        {"slope_thresholds_pct": (10.0, 5.0, 15.0, 20.0)},  # desordenados
        {"slope_thresholds_pct": (5.0, 10.0)},  # dos umbrales con cinco colores
        {"grid_pattern": "wavy"},
        {"slope_area_opacity": 1.5},
        {"slope_hysteresis_pct": -1.0},
        {"slope_mode": "zigzag"},
    ):
        try:
            replace(style, **wrong)
        except ValueError:
            pass
        else:
            raise AssertionError(wrong)

    print("Autoprueba finalizada correctamente.")
