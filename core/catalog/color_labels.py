"""Etiquetas de color del catálogo y su equivalencia con las de Lightroom Classic.

Este módulo NO depende de Qt: es Python puro.

La base de datos guarda SIEMPRE el nombre canónico en inglés y en minúsculas
('red', 'yellow', 'green', 'blue', 'purple') en 'media_items.color_label'; NULL = sin
etiqueta. Es el mismo vocabulario que usa Lightroom en 'photoshop:LabelColor', así que
la conversión a XMP (paso posterior) es directa.

Lightroom Classic tiene cinco etiquetas de color. Además de 'photoshop:LabelColor' (en
inglés), escribe 'xmp:Label' con el TEXTO de la etiqueta, que puede estar traducido al
idioma del programa ("Azul", "Rouge", "Blau"...) o ser un nombre personalizado.
'color_label_from_xmp' reconoce ambos campos (ver su docstring).

Los colores con los que se PINTAN las etiquetas (QColor) no están aquí: son cosa de la
interfaz (ui_helpers/helpers/ui_color_labels.py).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.color_labels
"""

__version__ = "1.1.0"
# ruff: noqa: RUF022
__all__ = [
    "COLOR_LABELS",
    "XMP_LABEL_TEXTS",
    "color_label_from_xmp",
    "is_valid_color_label",
    "normalize_color_label",
]

# Nombres canónicos, en el orden en que Lightroom los muestra en su menú
COLOR_LABELS: tuple[str, ...] = ("red", "yellow", "green", "blue", "purple")

# Texto que la aplicación ESCRIBE en 'xmp:Label' (además de 'photoshop:LabelColor').
# Lightroom Classic asocia el color por el TEXTO de 'xmp:Label' según su juego de
# etiquetas: si el texto no coincide, muestra una etiqueta "personalizada" en blanco.
# Son los nombres del juego de etiquetas de Lightroom Classic en español. Comprobados con
# archivos reales: "Roja" y "Azul". Los demás, pendientes de comprobar.
# Si el archivo ya tiene en 'xmp:Label' un texto que corresponde al mismo color, se
# conserva el suyo (ver 'core/userdata/xmp_writer.py').
XMP_LABEL_TEXTS: dict[str, str] = {
    "red": "Roja",
    "yellow": "Amarilla",
    "green": "Verde",
    "blue": "Azul",
    "purple": "Púrpura",
}

# Textos que Lightroom puede escribir en 'xmp:Label' según el idioma de la interfaz
# (minúsculas, sin acentos). Si el usuario renombró sus etiquetas en Lightroom, su texto
# no está aquí y no se puede deducir el color a partir de él.
_LABEL_TEXT_TO_COLOR: dict[str, str] = {
    # inglés
    "red": "red", "yellow": "yellow", "green": "green", "blue": "blue", "purple": "purple",
    # español
    "rojo": "red", "roja": "red", "amarillo": "yellow", "amarilla": "yellow",
    "verde": "green", "azul": "blue", "morado": "purple", "morada": "purple",
    "purpura": "purple",
    # francés
    "rouge": "red", "jaune": "yellow", "vert": "green", "bleu": "blue", "violet": "purple",
    # alemán
    "rot": "red", "gelb": "yellow", "grun": "green", "blau": "blue", "lila": "purple",
    # italiano
    "rosso": "red", "giallo": "yellow", "blu": "blue", "viola": "purple",
    # portugués
    "vermelho": "red", "amarelo": "yellow", "roxo": "purple",
}  # fmt: skip


assert set(XMP_LABEL_TEXTS) == set(COLOR_LABELS)  # no puede desincronizarse


def _fold(text: str) -> str:
    """Minúsculas, sin espacios en los extremos y sin acentos ('Púrpura' -> 'purpura')."""
    import unicodedata

    decomposed = unicodedata.normalize("NFD", text.strip().lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def is_valid_color_label(value: object) -> bool:
    """True si 'value' es un nombre canónico de etiqueta (NO acepta None)."""
    return isinstance(value, str) and value in COLOR_LABELS


def normalize_color_label(value: object) -> str | None:
    """Convierte lo que venga a un nombre canónico, o None si no es una etiqueta conocida.

    Acepta el nombre canónico en cualquier combinación de mayúsculas ('Red') y los textos
    traducidos que escribe Lightroom ('Azul'). None, '' o un texto desconocido dan None.
    """
    if not isinstance(value, str):
        return None
    return _LABEL_TEXT_TO_COLOR.get(_fold(value))


def color_label_from_xmp(label: str | None, label_color: str | None = None) -> str | None:
    """Deduce la etiqueta de color a partir de los campos XMP de Lightroom.

    Se mira primero 'photoshop:LabelColor' (nombre en inglés, no depende del idioma) y,
    si falta o no se reconoce, 'xmp:Label' (texto que puede estar traducido).

    Args:
        label: Valor de 'XMP-xmp:Label' (p. ej. "Azul").
        label_color: Valor de 'XMP-photoshop:LabelColor' (p. ej. "blue").

    Returns:
        El nombre canónico, o None si no hay etiqueta o no se reconoce.
    """
    return normalize_color_label(label_color) or normalize_color_label(label)


if __name__ == "__main__":
    # Autoprueba. Ejecutar desde la raíz del proyecto:  python -m core.catalog.color_labels
    assert COLOR_LABELS == ("red", "yellow", "green", "blue", "purple")
    assert all(is_valid_color_label(c) for c in COLOR_LABELS)
    assert not is_valid_color_label(None) and not is_valid_color_label("Red")
    assert not is_valid_color_label("orange")

    assert normalize_color_label("Red") == "red"
    assert normalize_color_label(" Azul ") == "blue"
    assert normalize_color_label("Púrpura") == "purple"
    assert normalize_color_label("Grün") == "green"
    assert normalize_color_label("Rouge") == "red"
    assert normalize_color_label("") is None
    assert normalize_color_label(None) is None
    assert normalize_color_label("Revisar") is None  # etiqueta renombrada por el usuario

    # photoshop:LabelColor manda sobre xmp:Label
    assert color_label_from_xmp("Azul", "blue") == "blue"
    assert color_label_from_xmp("Revisar", "green") == "green"
    assert color_label_from_xmp("Roja", None) == "red"
    assert color_label_from_xmp(None, None) is None
    assert color_label_from_xmp("Revisar", None) is None
    print("Autoprueba finalizada correctamente.")
