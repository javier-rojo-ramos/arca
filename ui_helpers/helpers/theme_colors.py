"""Colores del tema de la aplicación (los «tokens»): un único sitio para todos ellos.

Cada color tiene un NOMBRE según su función (fondo de panel, texto secundario, acento...),
no según su tono. El resto del programa usa esos nombres, nunca un "#rrggbb" suelto: así,
para retocar el aspecto basta cambiar un valor aquí, y un tema claro sería simplemente
otro 'ThemeColors' con los mismos nombres (de momento solo existe el oscuro; decidido
por el autor el 02/11/2026).

Capas, de más oscura a más clara (la profundidad se marca con escalones de gris, no con
bordes, como en LightTable o darktable):

    base     marco exterior, toolbar lateral, barra de menús
    panel    barras laterales e inspector (el "fondo" de la ventana)
    raised   cabeceras de sección, botones
    hover    elementos bajo el ratón
    input    campos de texto, listas y desplegables (un poco hundidos)

Las tarjetas de la cuadrícula tienen su propio juego ('CardColors'), porque se pintan a
mano en el delegado y necesitan más matices (reposo, ratón encima, seleccionada,
rechazada, no disponible).

Este módulo NO depende de Qt: solo define valores. 'ui_theme.py' los convierte en la
paleta de Qt (QPalette) y en la hoja de estilos (QSS).

1.2.0 Color 'success' (verde #2e7d32) y 'warning' en amarillo, para los iconos de la barra
      de estado; la autoprueba comprueba que se distinguen sobre los fondos.

Prueba rápida (contraste del texto sobre cada fondo):
    python -m ui_helpers.helpers.theme_colors
"""

__version__ = "1.2.0"
__all__ = ["DARK", "DARK_CARDS", "CardColors", "ThemeColors", "contrast_ratio"]

# Librerías estándar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeColors:
    """Juego de colores de un tema. Todos en formato "#rrggbb".

    Attributes:
        bg_base: Fondo más oscuro: marco, toolbar lateral, barra de menús.
        bg_panel: Fondo de las barras laterales, el inspector y los diálogos.
        bg_raised: Cabeceras de sección y botones.
        bg_hover: Fondo de un elemento bajo el ratón.
        bg_input: Campos de texto, listas y desplegables.
        bg_tooltip: Fondo de los textos emergentes.
        line: Separadores y bordes finos (sobre los fondos de panel).
        line_dark: Separación entre zonas grandes (paneles y cuadrícula).
        text: Texto principal (nunca blanco puro: cansa menos la vista).
        text_dim: Texto secundario: etiquetas, contadores, «Varios».
        text_disabled: Texto de lo desactivado.
        text_on_accent: Texto sobre el color de acento (fila seleccionada).
        accent: Acento ÚNICO: selección, elemento activo, iconos al pasar el ratón.
        link: Enlaces.
        success: Acciones terminadas bien (icono de la barra de estado).
        warning: Avisos (icono de la barra de estado; p. ej. archivo ausente).
        error: Errores.
    """

    bg_base: str
    bg_panel: str
    bg_raised: str
    bg_hover: str
    bg_input: str
    bg_tooltip: str
    line: str
    line_dark: str
    text: str
    text_dim: str
    text_disabled: str
    text_on_accent: str
    accent: str
    link: str
    success: str
    warning: str
    error: str


# Tema oscuro: grises grafito neutros (sin tinte azul) y un acento azul algo apagado
# (#4c8ee8, elegido por el autor el 02/11/2026)
DARK = ThemeColors(
    bg_base="#141517",
    bg_panel="#1c1d20",
    bg_raised="#26282c",
    bg_hover="#2f3237",
    bg_input="#18191b",
    bg_tooltip="#2f3237",
    line="#3a3d43",
    line_dark="#0d0e10",
    text="#d6d7da",
    text_dim="#8a8e95",
    text_disabled="#5c6067",
    text_on_accent="#ffffff",
    accent="#4c8ee8",
    link="#6ea4ef",
    success="#2e7d32",  # verde elegido por el autor (05/11/2026)
    warning="#e8b830",  # amarillo (antes naranja, #e8833a; no se usaba en ningún sitio)
    error="#e05050",
)


@dataclass(frozen=True, slots=True)
class CardColors:
    """Colores de la cuadrícula y de sus tarjetas ('ThumbnailsDelegate'). Formato "#rrggbb".

    Las etiquetas de color tiñen 'bg' (el marco de la imagen); la banda inferior (nombre,
    estrellas y marca) no se tiñe, para que el texto siempre se lea.

    Attributes:
        grid_bg: Fondo de la cuadrícula (y de la barra inferior: forman un bloque).
        bg, bg_hover, bg_selected: Fondo de la tarjeta en reposo, con el ratón y seleccionada.
        band, band_hover, band_selected: Banda inferior en esos mismos estados.
        line, line_hover, line_selected: Borde de la tarjeta en esos estados.
        placeholder_bg: Hueco de una tarjeta sin miniatura (o con el marcador de su tipo).
        placeholder_glyph: Dibujo del marcador (la línea de un GPX, la nota de un audio...).
        text, text_highlighted: Nombre en reposo y con ratón o selección.
        text_rejected, text_rejected_highlighted: Nombre de una rechazada (apagado).
        text_unavailable, text_unavailable_highlighted: Nombre de un archivo no disponible.
    """

    grid_bg: str
    bg: str
    bg_hover: str
    bg_selected: str
    band: str
    band_hover: str
    band_selected: str
    line: str
    line_hover: str
    line_selected: str
    placeholder_bg: str
    placeholder_glyph: str
    text: str
    text_highlighted: str
    text_rejected: str
    text_rejected_highlighted: str
    text_unavailable: str
    text_unavailable_highlighted: str


# Tarjetas del tema oscuro: la cuadrícula algo más hundida que los paneles y las tarjetas
# un escalón por encima (como las celdas de Lightroom), con el borde de la seleccionada en
# el acento y el de la que está bajo el ratón en gris claro
DARK_CARDS = CardColors(
    grid_bg="#18191b",
    bg="#26282c",
    bg_hover="#2c2f33",
    bg_selected="#34373c",
    band="#2c2e32",
    band_hover="#323539",
    band_selected="#3a3d42",
    line="#0d0e10",
    line_hover="#8a8e95",
    line_selected=DARK.accent,
    placeholder_bg="#34373c",
    placeholder_glyph="#70747b",
    text="#d6d7da",
    text_highlighted="#ffffff",
    text_rejected="#8a8e95",
    text_rejected_highlighted="#a9acb2",
    text_unavailable="#70747b",
    text_unavailable_highlighted="#8a8e95",
)


def _luminance(color: str) -> float:
    """Luminancia relativa de un color "#rrggbb" (fórmula de las WCAG)."""
    channels = []
    for index in (1, 3, 5):
        value = int(color[index : index + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    """Contraste entre dos colores (1 = ninguno, 21 = negro sobre blanco; WCAG pide 4,5 para texto)."""
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


if __name__ == "__main__":
    # Autoprueba: el texto se lee sobre todos los fondos y las capas van de oscura a clara.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.helpers.theme_colors
    theme = DARK
    backgrounds = {
        "bg_base": theme.bg_base,
        "bg_panel": theme.bg_panel,
        "bg_raised": theme.bg_raised,
        "bg_hover": theme.bg_hover,
        "bg_input": theme.bg_input,
    }
    for name, background in backgrounds.items():
        main = contrast_ratio(theme.text, background)
        dim = contrast_ratio(theme.text_dim, background)
        print(f"{name:10} texto {main:5.1f}   secundario {dim:4.1f}")
        assert main >= 7, (name, main)  # texto principal: nivel AAA
        assert dim >= 3.5, (name, dim)  # secundario: legible (etiquetas en gris)
    # Las capas, de más oscura a más clara (la profundidad se ve sin bordes)
    order = [theme.bg_base, theme.bg_panel, theme.bg_raised, theme.bg_hover]
    assert order == sorted(order, key=_luminance), order
    # Iconos de estado (éxito, aviso, error): se distinguen sobre la barra de estado y los
    # paneles (WCAG pide 3 para lo que no es texto)
    for name in ("success", "warning", "error"):
        for background in (theme.bg_base, theme.bg_panel):
            ratio = contrast_ratio(getattr(theme, name), background)
            assert ratio >= 3, (name, background, ratio)
    # Texto blanco sobre el acento (fila seleccionada): legible
    assert contrast_ratio(theme.text_on_accent, theme.accent) >= 3, "acento demasiado claro"
    # Todos los valores tienen formato "#rrggbb"
    for colors in (theme, DARK_CARDS):
        for name in type(colors).__dataclass_fields__:
            value = getattr(colors, name)
            assert len(value) == 7 and value.startswith("#"), (name, value)
            int(value[1:], 16)
    # Tarjetas: el nombre se lee sobre la banda en todos los estados; la tarjeta destaca
    # sobre la cuadrícula y la seleccionada sobre la de reposo
    cards = DARK_CARDS
    for band in (cards.band, cards.band_hover, cards.band_selected):
        assert contrast_ratio(cards.text, band) >= 7, band
        assert contrast_ratio(cards.text_rejected, band) >= 3, band
    assert _luminance(cards.grid_bg) < _luminance(cards.bg) < _luminance(cards.bg_hover) < _luminance(cards.bg_selected)
    print("Tarjetas: texto legible en la banda y estados de más oscuro a más claro")
    print("Autoprueba finalizada correctamente.")
