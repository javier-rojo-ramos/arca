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
rechazada, no disponible). Incluye lo que se dibuja ENCIMA de la imagen (insignias,
velos, el círculo de la selección rápida), que usan también la vista individual y la
imagen del arrastre.

Las marcas de clasificación (estrellas, marca, rechazo y los colores de las etiquetas)
tienen el suyo ('MarkColors'): son las mismas en la tarjeta, la barra inferior y la fila
«Atributos» de la barra de filtros.

Formato: "#rrggbb"; los translúcidos, "#aarrggbb" (el de Qt: primero la opacidad, de 00
a ff), p. ej. "#a5000000" = negro con opacidad 165.

Este módulo NO depende de Qt: solo define valores. 'ui_theme.py' los convierte en la
paleta de Qt (QPalette) y en la hoja de estilos (QSS), y da a los demás el juego activo
('COLORS', 'CARD_COLORS', 'MARK_COLORS').

1.7.0 Colores de los tracks en el mapa: 'map_track', 'map_track_active' y 'map_track_halo'.
1.6.0 Todos los colores de la interfaz, aquí (antes sueltos en el código): 'missing',
      'offline' y 'shadow' en 'ThemeColors'; lo que va encima de la imagen en 'CardColors';
      'MarkColors' nuevo (estrellas, marca, rechazo y etiquetas de color).
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

__version__ = "1.7.0"
__all__ = ["DARK", "DARK_CARDS", "DARK_MARKS", "CardColors", "MarkColors", "ThemeColors", "contrast_ratio"]

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
        missing: Archivo ausente (la unidad está y el archivo no: hay que hacer algo):
            indicador de la tarjeta, de la vista individual y de «Estado» en el inspector.
        offline: Archivo sin conexión (su disco no está conectado: volverá).
        shadow: Sombra de la paleta de Qt (relieves de Fusion).
        map_track: Línea de un track en el mapa. No es un gris ni el acento: tiene que
            verse sobre cualquier mapa (callejero, topográfico, ortofoto).
        map_track_active: Línea del track activo (el elegido), distinta de las demás.
        map_track_halo: Borde claro bajo la línea de un track, para que se lea sobre
            cualquier fondo (como lo que va encima de las fotos: en un tema claro
            seguiría igual).
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
    missing: str
    offline: str
    shadow: str
    map_track: str
    map_track_active: str
    map_track_halo: str


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
    warning="#e8b830",  # amarillo
    error="#e05050",
    missing="#e8833a",  # naranja: distinto del aviso amarillo (es un estado, no un mensaje)
    offline="#7d7d7d",
    shadow="#000000",
    map_track="#2f6fd6",  # azul: propuesta del 13/11/2026, a confirmar por el autor
    map_track_active="#e5383b",  # rojo: el track elegido
    map_track_halo="#ffffff",
)


@dataclass(frozen=True, slots=True)
class CardColors:
    """Colores de la cuadrícula y de sus tarjetas ('ThumbnailsDelegate').

    Las etiquetas de color tiñen 'bg' (el marco de la imagen); la banda inferior (nombre,
    estrellas y marca) no se tiñe, para que el texto siempre se lea.

    Lo que va ENCIMA de la imagen tiene que verse sobre cualquier foto (clara u oscura): por
    eso es blanco o negro, a veces translúcido ("#aarrggbb"), con un borde del contrario.
    Los velos son un color sin opacidad: cuánto tapan lo decide quien los dibuja
    ('REJECTED_WASH', 'UNAVAILABLE_DIM' del delegado).

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
        overlay_text: Texto y dibujos sobre la imagen (duración, «!» del ausente...).
        overlay_bg: Fondo translúcido de las insignias sobre la imagen (duración; textos de
            la vista individual).
        overlay_border: Borde fino de los círculos sobre la imagen (aviso de no disponible,
            selección rápida): se ven sobre imágenes claras.
        quick_on: Círculo de la selección rápida de lo que está dentro.
        quick_hover: Círculo de lo que no está dentro, con el ratón encima (translúcido).
        rejected_wash: Velo de una rechazada (la miniatura queda blanquecina).
        unavailable_dim: Velo de un archivo no disponible (la miniatura se oscurece).
        drag_border: Borde de la imagen que se arrastra (translúcido).
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
    overlay_text: str
    overlay_bg: str
    overlay_border: str
    quick_on: str
    quick_hover: str
    rejected_wash: str
    unavailable_dim: str
    drag_border: str


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
    # Encima de la imagen (iguales en cualquier tema: van sobre la foto, no sobre la ventana)
    overlay_text="#ffffff",
    overlay_bg="#a5000000",  # negro, opacidad 165
    overlay_border="#8c000000",  # negro, opacidad 140
    quick_on="#ffffff",
    quick_hover="#aad7d7d7",  # gris claro, opacidad 170
    rejected_wash="#ffffff",
    unavailable_dim="#000000",
    drag_border="#c8ffffff",  # blanco, opacidad 200
)


@dataclass(frozen=True, slots=True)
class MarkColors:
    """Colores de las marcas de clasificación: los mismos en la tarjeta, la barra inferior
    ('OrganizeBar') y la fila «Atributos» de la barra de filtros. Los dibuja 'card_marks.py'.

    Attributes:
        star: Estrellas rellenas.
        star_rejected: Estrellas rellenas de una rechazada (apagadas).
        star_empty: Estrellas vacías (al pasar el ratón; visibles sobre la banda gris).
        flag_picked: Recuadro de «marcada».
        flag_outline: Contorno de «sin marca» (con el ratón encima).
        reject: X de «rechazada».
        label_red, label_yellow, label_green, label_blue, label_purple: Las cinco
            etiquetas de color (parecidas a las de Lightroom Classic, ajustadas para que se
            distingan sobre el fondo oscuro). Las claves son las de 'COLOR_LABELS'.
    """

    star: str
    star_rejected: str
    star_empty: str
    flag_picked: str
    flag_outline: str
    reject: str
    label_red: str
    label_yellow: str
    label_green: str
    label_blue: str
    label_purple: str


# Marcas del tema oscuro
DARK_MARKS = MarkColors(
    star="#ffcc00",
    star_rejected="#8a7a30",
    star_empty="#9a9a9a",
    flag_picked="#ffffff",
    flag_outline="#9a9a9a",
    reject="#a0a0a0",
    label_red="#e0453f",
    label_yellow="#e8c53a",
    label_green="#4cae4f",
    label_blue="#3d8fe0",
    label_purple="#9a5fc4",
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
    # Todos los valores tienen formato "#rrggbb" o, los translúcidos, "#aarrggbb"
    translucent = {"overlay_bg", "overlay_border", "quick_hover", "drag_border"}
    for colors in (theme, DARK_CARDS, DARK_MARKS):
        for name in type(colors).__dataclass_fields__:
            value = getattr(colors, name)
            size = 9 if name in translucent else 7
            assert len(value) == size and value.startswith("#"), (name, value)
            int(value[1:], 16)
    # Estados de los archivos: se ven sobre los paneles y no se confunden con el aviso
    for name in ("missing", "offline"):
        assert contrast_ratio(getattr(theme, name), theme.bg_panel) >= 3, name
    assert theme.missing != theme.warning
    # Tracks del mapa: los dos se leen sobre su borde claro y no se confunden
    for name in ("map_track", "map_track_active"):
        assert contrast_ratio(getattr(theme, name), theme.map_track_halo) >= 3, name
    assert theme.map_track != theme.map_track_active
    # Marcas: las estrellas y la marca se ven sobre la banda de la tarjeta (WCAG, 3); las
    # cinco etiquetas, distintas entre sí
    marks = DARK_MARKS
    for name in ("star", "star_empty", "flag_picked", "flag_outline", "reject"):
        for band in (DARK_CARDS.band, DARK_CARDS.band_selected):
            assert contrast_ratio(getattr(marks, name), band) >= 3, (name, band)
    labels = [marks.label_red, marks.label_yellow, marks.label_green, marks.label_blue, marks.label_purple]
    assert len(set(labels)) == 5, labels
    print("Marcas: estrellas y marca legibles sobre la banda; cinco etiquetas distintas")
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
