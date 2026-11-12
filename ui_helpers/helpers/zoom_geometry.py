"""Cuentas del zoom 1:1 de la vista individual: tamaño, posición y desplazamiento.

Este módulo NO depende de Qt: solo números (tuplas), para poder probarlo sin ventana. Lo
usa 'ui_helpers/widgets/single_media_view.py', que se ocupa del ratón y del dibujo.

Medidas en píxeles LÓGICOS del widget (los de Qt); 'ratio' es la escala de la pantalla
('devicePixelRatio': 1,25 con el escalado de Windows al 125 %). «1:1» es un píxel de la
imagen en un píxel FÍSICO de la pantalla, así que la imagen ampliada mide, en píxeles
lógicos, su tamaño en píxeles dividido por 'ratio' ('zoomed_size').

    Rect  = (x, y, ancho, alto)   un rectángulo
    Size  = (ancho, alto)
    Point = (x, y)
    'offset' = esquina superior izquierda de la imagen ampliada, en el widget.

Uso:
    zoomed = zoomed_size((6000, 4000), ratio)        # la imagen a 1:1, en px lógicos
    if can_zoom(shown_size, zoomed): ...             # cursor de lupa
    # Clic: el punto pulsado de la imagen se queda bajo el ratón
    offset = offset_keeping(relative_point(shown_rect, click), click, zoomed, area, ratio)
    # Arrastrar
    offset = clamp_offset((offset[0] + dx, offset[1] + dy), zoomed, area, ratio)
    # Cambia el espacio (ventana) o el tamaño de la imagen (llega el original): el punto de
    # la imagen que estaba en el centro sigue en el centro
    rel = relative_point((*offset, *zoomed), center_of(old_area))
    offset = offset_keeping(rel, center_of(new_area), new_zoomed, new_area, ratio)

Reglas ('clamp_offset'):
    - Si la imagen ampliada es mayor que el espacio en una dirección, no se puede sacar de
      él: no queda hueco entre su borde y el del espacio.
    - Si es menor (p. ej. una panorámica, en vertical), se centra en esa dirección.
    - La esquina cae siempre en un píxel físico entero ('snap'): entre dos, Qt suavizaría
      la imagen y el 1:1 dejaría de ser nítido.

1.0.0 Primera versión (vista individual a 1:1, paso 2).

Prueba rápida (desde la raíz del proyecto):
    python -m ui_helpers.helpers.zoom_geometry
"""

__version__ = "1.0.0"
__all__ = [
    "Point",
    "Rect",
    "Size",
    "can_zoom",
    "center_of",
    "clamp_offset",
    "offset_keeping",
    "relative_point",
    "snap",
    "zoomed_size",
]

Rect = tuple[float, float, float, float]  # x, y, ancho, alto
Size = tuple[float, float]  # ancho, alto
Point = tuple[float, float]  # x, y

# Cuánto (px lógicos) tiene que ganar la imagen al ampliarla para que valga la pena: con
# menos de medio píxel, el 1:1 se vería igual que la vista ajustada
_MIN_GAIN = 0.5


def zoomed_size(pixels: tuple[int, int], ratio: float) -> Size:
    """Tamaño (px lógicos) de una imagen de 'pixels' (ancho, alto) mostrada a 1:1."""
    width, height = pixels
    return width / ratio, height / ratio


def can_zoom(shown: Size, zoomed: Size) -> bool:
    """Si ampliar a 1:1 muestra la imagen más grande que ahora (cursor de lupa).

    Args:
        shown: Tamaño con el que se ve ahora (vista ajustada).
        zoomed: Tamaño a 1:1 ('zoomed_size').
    """
    return zoomed[0] > shown[0] + _MIN_GAIN or zoomed[1] > shown[1] + _MIN_GAIN


def snap(value: float, ratio: float) -> float:
    """El píxel físico entero más cercano a 'value' (px lógicos)."""
    return round(value * ratio) / ratio


def center_of(rect: Rect) -> Point:
    """El centro de un rectángulo."""
    x, y, width, height = rect
    return x + width / 2, y + height / 2


def relative_point(rect: Rect, point: Point) -> Point:
    """Dónde cae 'point' dentro de 'rect', de 0 a 1 en cada dirección (fuera, al borde).

    Sirve para saber qué punto de la IMAGEN hay bajo el ratón (o en el centro): es el
    mismo en la vista ajustada y a 1:1, aunque las dos midan distinto.
    """
    x, y, width, height = rect
    u = (point[0] - x) / width if width > 0 else 0.5
    v = (point[1] - y) / height if height > 0 else 0.5
    return min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0)


def clamp_offset(offset: Point, zoomed: Size, area: Rect, ratio: float) -> Point:
    """Coloca la imagen ampliada dentro del espacio (ver las reglas en el docstring).

    Args:
        offset: Esquina superior izquierda deseada.
        zoomed: Tamaño de la imagen ampliada.
        area: Espacio donde se ve.
        ratio: Escala de la pantalla.
    """
    return (
        snap(_clamp_axis(offset[0], zoomed[0], area[0], area[2]), ratio),
        snap(_clamp_axis(offset[1], zoomed[1], area[1], area[3]), ratio),
    )


def _clamp_axis(start: float, length: float, area_start: float, area_length: float) -> float:
    """Una dirección de 'clamp_offset'."""
    if length <= area_length:
        return area_start + (area_length - length) / 2  # cabe: centrada
    return min(max(start, area_start + area_length - length), area_start)


def offset_keeping(relative: Point, anchor: Point, zoomed: Size, area: Rect, ratio: float) -> Point:
    """La posición de la imagen ampliada que deja su punto 'relative' (de 0 a 1) en 'anchor'
    (p. ej. bajo el ratón), sin sacarla del espacio ('clamp_offset').

    Args:
        relative: Punto de la imagen ('relative_point').
        anchor: Dónde se quiere ese punto (px lógicos del widget).
        zoomed: Tamaño de la imagen ampliada.
        area: Espacio donde se ve.
        ratio: Escala de la pantalla.
    """
    desired = (anchor[0] - relative[0] * zoomed[0], anchor[1] - relative[1] * zoomed[1])
    return clamp_offset(desired, zoomed, area, ratio)


if __name__ == "__main__":
    # Autoprueba (sin Qt). Ejecutar desde la raíz:  python -m ui_helpers.helpers.zoom_geometry
    def close(a: Point | Size, b: Point | Size, tolerance: float = 1e-6) -> bool:
        return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))

    AREA: Rect = (0, 0, 1000, 600)

    # 1. Tamaño a 1:1 y si vale la pena ampliar
    assert zoomed_size((6000, 4000), 1.0) == (6000, 4000)
    assert close(zoomed_size((6000, 4000), 1.25), (4800, 3200))  # Windows al 125 %
    assert can_zoom((900, 600), zoomed_size((6000, 4000), 1.0))
    # Una foto que ya se ve a su tamaño (cabe): ampliar no cambia nada
    assert not can_zoom((800, 533), (800, 533)) and not can_zoom((800, 533), (800.4, 533.2))
    # Una panorámica estrecha que gana solo a lo ancho: sí
    assert can_zoom((1000, 100), (3000, 300))

    # 2. Píxeles físicos enteros
    assert snap(10.3, 1.0) == 10 and snap(10.5, 2.0) == 10.5 and close((snap(10.3, 1.25),), (10.4,))

    # 3. Dentro del espacio: sin huecos si es mayor; centrada si es menor
    zoomed = (6000.0, 4000.0)
    assert clamp_offset((100, 50), zoomed, AREA, 1.0) == (0, 0)  # no se separa del borde
    assert clamp_offset((-9000, -9000), zoomed, AREA, 1.0) == (1000 - 6000, 600 - 4000)
    assert clamp_offset((-1234.4, -10), zoomed, AREA, 1.0) == (-1234, -10)  # px enteros
    # Panorámica de 3000 × 300 en un espacio de 600 de alto: centrada en vertical
    assert clamp_offset((-500, 0), (3000, 300), AREA, 1.0) == (-500, 150)
    # Con el espacio desplazado (no empieza en 0, 0): una esquina que dejaría hueco, al
    # borde del espacio; una que no lo deja (la imagen empieza antes que él), tal cual
    assert clamp_offset((100, 100), zoomed, (16, 16, 1000, 600), 1.0) == (16, 16)
    assert clamp_offset((5, 5), zoomed, (16, 16, 1000, 600), 1.0) == (5, 5)

    # 4. Clic: el punto pulsado de la imagen se queda bajo el ratón
    shown: Rect = (50, 0, 900, 600)  # la vista ajustada de una foto de 3:2
    click = (500, 300)  # el centro de la foto
    rel = relative_point(shown, click)
    assert close(rel, (0.5, 0.5))
    offset = offset_keeping(rel, click, zoomed, AREA, 1.0)
    assert offset == (500 - 3000, 300 - 2000)
    # El punto de la imagen bajo el ratón, a 1:1: el mismo
    assert close(relative_point((*offset, *zoomed), click), rel)
    # Clic cerca de una esquina: el punto sigue bajo el ratón (la imagen no deja hueco)
    near_click = (60, 10)
    near = relative_point(shown, near_click)
    offset = offset_keeping(near, near_click, zoomed, AREA, 1.0)
    assert offset == (-7, -57) and close(relative_point((*offset, *zoomed), near_click), near, 0.002)
    # Clic justo en la esquina de la foto (con margen a la izquierda): para dejar ese punto
    # bajo el ratón quedaría un hueco, así que la imagen se pega al borde del espacio
    assert offset_keeping(relative_point(shown, (50, 0)), (50, 0), zoomed, AREA, 1.0) == (0, 0)
    # Fuera de la imagen (en el margen): cuenta como su borde
    assert relative_point(shown, (10, -5)) == (0.0, 0.0)

    # 5. Cambia el espacio (ventana más grande): el punto del centro sigue en el centro
    offset = (-2500.0, -1700.0)
    middle = relative_point((*offset, *zoomed), center_of(AREA))
    bigger: Rect = (0, 0, 1600, 900)
    moved = offset_keeping(middle, center_of(bigger), zoomed, bigger, 1.0)
    assert close(relative_point((*moved, *zoomed), center_of(bigger)), middle)

    # 6. Llega el original con otro tamaño (p. ej. el de la caché era una vista previa):
    #    el mismo punto de la imagen sigue en el centro
    smaller = (3000.0, 2000.0)
    moved = offset_keeping(middle, center_of(AREA), smaller, AREA, 1.0)
    assert close(relative_point((*moved, *smaller), center_of(AREA)), middle)

    # 7. Con el escalado de Windows: la esquina, en un píxel físico entero
    ratio = 1.25
    zoomed = zoomed_size((6000, 4000), ratio)
    offset = offset_keeping((0.37, 0.61), (333.3, 222.2), zoomed, AREA, ratio)
    assert all(abs(value * ratio - round(value * ratio)) < 1e-9 for value in offset), offset
    print("Autoprueba finalizada correctamente.")
