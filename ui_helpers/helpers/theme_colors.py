"""Colores del tema de la aplicación (los «tokens»): un único sitio para todos ellos.

Cada color tiene un NOMBRE según su función (fondo de panel, texto secundario, acento...),
no según su tono. El resto del programa usa esos nombres, nunca un "#rrggbb" suelto: así,
para retocar el aspecto basta cambiar un valor aquí, y un tema claro sería simplemente
otro 'ThemeColors' con los mismos nombres (de momento solo existe el oscuro; decidido
por el autor el 02/11/2026).

Capas, de más oscura a más clara (la profundidad se marca con escalones de gris, no con
bordes, como en LightTable o darktable):

    base     toolbar lateral, barra de menús
    panel    barras laterales e inspector (el "fondo" de la ventana)
    raised   cabeceras de sección, botones
    hover    elementos bajo el ratón
    input    campos de texto, listas y desplegables (un poco hundidos)

Las zonas (toolbar, barras laterales, zona central) van pegadas, separadas por una raya
de 1 px ('divider'), algo MÁS CLARA que los paneles (como en LightTable).

Las tarjetas de la cuadrícula tienen su propio juego ('CardColors'), porque se pintan a
mano en el delegado y necesitan más matices (reposo, ratón encima, seleccionada,
rechazada, no disponible).

Este módulo NO depende de Qt: solo define valores. 'ui_theme.py' los convierte en la
paleta de Qt (QPalette) y en la hoja de estilos (QSS).

1.5.0 Tarjetas y cuadrícula también en grises neutros (cuadrícula #161616, más hundida que
      la toolbar y los paneles); decidido por el autor el 07/11/2026.
1.4.0 Acento ámbar #eca531 (antes azul #4c8ee8; el autor, 07/11/2026) y texto OSCURO sobre
      él ('text_on_accent'): el blanco sobre ámbar no se lee (contraste 2:1).
1.3.0 Grises neutros como los de LightTable (toolbar #1a1a1a, paneles #222222), sin el
      leve tinte azul de antes; color nuevo 'divider' (raya de 1 px entre zonas). Las
      tarjetas no cambian. Decidido por el autor el 07/11/2026.
1.2.0 Color 'success' (verde #2e7d32) y 'warning' en amarillo, para los iconos de la barra
      de estado; la autoprueba comprueba que se distinguen sobre los fondos.

Prueba rápida (contraste del texto sobre cada fondo):
    python -m ui_helpers.helpers.theme_colors
"""

__version__ = "1.5.0"
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
        line_dark: Raya oscura (bordes hundidos, sombra).
        divider: Raya de 1 px entre zonas (toolbar, barras laterales, zona central).
        text: Texto principal (nunca blanco puro: cansa menos la vista).
        text_dim: Texto secundario: etiquetas, contadores, «Varios».
        text_disabled: Texto de lo desactivado.
        text_on_accent: Texto y marcas sobre el color de acento (fila seleccionada, casilla
            marcada). Oscuro: el acento es claro.
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
    divider: str
    text: str
    text_dim: str
    text_disabled: str
    text_on_accent: str
    accent: str
    link: str
    success: str
    warning: str
    error: str


# Tema oscuro: grises neutros (R = G = B), tomados de LightTable, y un acento ámbar
# (#eca531); los dos, elegidos por el autor el 07/11/2026 (antes, acento azul #4c8ee8)
DARK = ThemeColors(
    bg_base="#1a1a1a",
    bg_panel="#222222",
    bg_raised="#2a2a2a",
    bg_hover="#333333",
    bg_input="#1c1c1c",
    bg_tooltip="#333333",
    line="#3a3a3a",
    line_dark="#0e0e0e",
    divider="#2e2e2e",
    text="#d8d8d8",
    text_dim="#8c8c8c",
    text_disabled="#5e5e5e",
    text_on_accent="#1a1a1a",
    accent="#eca531",
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


# Tarjetas del tema oscuro, en los mismos grises neutros que el resto: la cuadrícula más
# hundida que la toolbar y los paneles (como el centro de LightTable) y las tarjetas un
# escalón por encima (como las celdas de Lightroom), con el borde de la seleccionada en el
# acento y el de la que está bajo el ratón en gris claro
DARK_CARDS = CardColors(
    grid_bg="#161616",
    bg="#262626",
    bg_hover="#2c2c2c",
    bg_selected="#333333",
    band="#2a2a2a",
    band_hover="#303030",
    band_selected="#383838",
    line=DARK.line_dark,
    line_hover=DARK.text_dim,
    line_selected=DARK.accent,
    placeholder_bg="#333333",
    placeholder_glyph="#707070",
    text=DARK.text,
    text_highlighted="#ffffff",
    text_rejected=DARK.text_dim,
    text_rejected_highlighted="#aaaaaa",
    text_unavailable="#707070",
    text_unavailable_highlighted=DARK.text_dim,
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
    # La raya entre zonas, algo más clara que los paneles que separa
    assert _luminance(theme.divider) > _luminance(theme.bg_panel) > _luminance(theme.bg_base)
    # Iconos de estado (éxito, aviso, error): se distinguen sobre la barra de estado y los
    # paneles (WCAG pide 3 para lo que no es texto)
    for name in ("success", "warning", "error"):
        for background in (theme.bg_base, theme.bg_panel):
            ratio = contrast_ratio(getattr(theme, name), background)
            assert ratio >= 3, (name, background, ratio)
    # Texto sobre el acento (fila seleccionada): legible como texto normal (WCAG, 4,5)
    assert contrast_ratio(theme.text_on_accent, theme.accent) >= 4.5, "texto sobre el acento"
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
    # La cuadrícula, más hundida que la toolbar y los paneles que la rodean
    assert _luminance(cards.grid_bg) < _luminance(theme.bg_base) < _luminance(theme.bg_panel)
    print("Tarjetas: texto legible en la banda y estados de más oscuro a más claro")
    print("Autoprueba finalizada correctamente.")
