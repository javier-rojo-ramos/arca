"""Tamaños de miniatura que genera la aplicación (la "escalera" de tamaños).

Este módulo NO depende de Qt: es Python puro.

Cada elemento del catálogo puede tener hasta cuatro versiones reducidas. Todas se
miden por su LADO LARGO (el ancho en una foto horizontal, el alto en una vertical):

    THUMBNAIL     160 px   cuadrícula densa
    MEDIUM        480 px   tarjeta de contenido
    PREVIEW      1200 px   panel de inspección rápida / vista ampliada
    FULLSCREEN   2560 px   vista individual o pantalla completa, sin abrir el original

Para cambiar un tamaño (o su calidad JPEG) basta con editar 'ThumbnailSize'. Las
carpetas de la caché llevan el lado largo en el nombre ('cache/photo/160/...'), así
que un tamaño nuevo usa una carpeta nueva y no se mezcla con los archivos antiguos.

Regla general: NUNCA se amplía. Si la imagen de la que se parte es más pequeña que un
tamaño, ese tamaño contiene la propia imagen, a su medida: todos los tamaños existen siempre
para cada archivo (ver 'imaging.plan_sizes').
"""

__version__ = "1.0.0"
__all__ = ["ALL_SIZES", "DEFAULT_SIZES", "ThumbnailSize", "smallest_covering"]

# Librerías estándar
from enum import Enum


class ThumbnailSize(Enum):
    """Un tamaño de miniatura: lado largo máximo en píxeles y calidad JPEG.

    Cada miembro se define como (lado largo, calidad). El valor ('.value') del
    miembro es esa tupla, así que no puede haber dos tamaños con los mismos dos números.

    Attributes:
        max_side: Lado largo máximo, en píxeles.
        quality: Calidad JPEG (1-95). Las miniaturas pequeñas toleran menos calidad.
    """

    THUMBNAIL = (160, 80)
    MEDIUM = (480, 85)
    PREVIEW = (1200, 85)
    FULLSCREEN = (2560, 88)

    # Anotaciones de los atributos que se asignan en '__init__' (solo para el editor)
    max_side: int
    quality: int

    def __init__(self, max_side: int, quality: int) -> None:
        self.max_side = max_side
        self.quality = quality


# Todos los tamaños, de menor a mayor
ALL_SIZES: tuple[ThumbnailSize, ...] = tuple(
    sorted(ThumbnailSize, key=lambda size: size.max_side)
)

# Tamaños que se generan por defecto cuando se crean las miniaturas de un archivo.
# Si más adelante el espacio en disco preocupa (los dos tamaños grandes ocupan con
# diferencia lo más), aquí se puede dejar fuera 'FULLSCREEN' y generarlo a demanda.
DEFAULT_SIZES: tuple[ThumbnailSize, ...] = ALL_SIZES


def smallest_covering(pixels: int) -> ThumbnailSize:
    """Devuelve el tamaño más pequeño cuyo lado largo llega a 'pixels'.

    Sirve para elegir qué archivo cargar según lo que se va a mostrar: una tarjeta
    de 200 px en una pantalla con escalado del 150 % necesita 300 px reales, y el
    tamaño que los cubre es 'MEDIUM'. Si ninguno llega, devuelve el mayor.

    Args:
        pixels: Lado largo necesario, en píxeles FÍSICOS (ya multiplicado por el
            factor de escala de la pantalla).
    """
    for size in ALL_SIZES:
        if size.max_side >= pixels:
            return size
    return ALL_SIZES[-1]


if __name__ == "__main__":
    # Autoprueba de la escalera de tamaños.
    # Ejecutar desde la raíz del proyecto:  python -m core.thumbnails.sizes
    assert [size.max_side for size in ALL_SIZES] == [160, 480, 1200, 2560]
    assert ThumbnailSize.THUMBNAIL.max_side == 160 and ThumbnailSize.THUMBNAIL.quality == 80
    assert ThumbnailSize((480, 85)) is ThumbnailSize.MEDIUM  # búsqueda por valor
    assert DEFAULT_SIZES == ALL_SIZES

    assert smallest_covering(1) is ThumbnailSize.THUMBNAIL
    assert smallest_covering(160) is ThumbnailSize.THUMBNAIL
    assert smallest_covering(161) is ThumbnailSize.MEDIUM
    assert smallest_covering(300) is ThumbnailSize.MEDIUM
    assert smallest_covering(1200) is ThumbnailSize.PREVIEW
    assert smallest_covering(5000) is ThumbnailSize.FULLSCREEN  # ninguno llega: el mayor
    print("Autoprueba finalizada correctamente.")
