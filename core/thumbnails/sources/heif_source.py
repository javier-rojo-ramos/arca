"""Origen de miniaturas para HEIC/HEIF (fotos del iPhone), con 'pillow-heif'.

Este módulo NO depende de Qt. Qt no sabe decodificar HEIC, y Pillow tampoco sin
ayuda: 'pillow-heif' (o su versión ligera 'pi-heif', que solo decodifica y tiene una
licencia más permisiva para redistribuir) le añade ese formato.

    pip install pillow-heif        o bien        pip install pi-heif

Si ninguna de las dos está instalada, este origen lo indica con un
'UnsupportedSourceError' que explica cómo instalarla: los HEIC se anotan como
"sin miniatura" y se podrán generar más tarde, sin tocar nada más.

Detalles que ya resuelve la librería: aplica la rotación guardada en el propio HEIC,
reduce los HEIC de 10 bits a 8 y entrega el perfil de color (Display P3 en el
iPhone), que 'generator.py' convierte a sRGB.
"""

__version__ = "1.0.0"
__all__ = ["HeifSource", "heif_support_available"]

# Librerías estándar
import threading
from typing import ClassVar

# Módulos del proyecto
from core.thumbnails.sources.base import UnsupportedSourceError
from core.thumbnails.sources.pillow_source import PillowSource

# El registro del formato en Pillow es global y solo debe hacerse una vez
_register_lock = threading.Lock()
_registered = False

_INSTALL_HINT = (
    "Falta la librería para leer HEIC: instala 'pillow-heif' (pip install pillow-heif) "
    "o su versión ligera 'pi-heif'."
)


def heif_support_available() -> bool:
    """Registra el formato HEIC en Pillow si se puede. Devuelve True si queda disponible."""
    global _registered
    with _register_lock:
        if _registered:
            return True
        try:
            from pillow_heif import register_heif_opener
        except ImportError:
            try:
                from pi_heif import register_heif_opener
            except ImportError:
                return False
        register_heif_opener()
        _registered = True
        return True


class HeifSource(PillowSource):
    """Lee con Pillow (más pillow-heif) los archivos HEIC/HEIF."""

    name: ClassVar[str] = "heif"
    extensions: ClassVar[frozenset[str] | None] = frozenset({"heic", "heif", "hif"})

    def is_available(self) -> bool:
        """True si 'pillow-heif' o 'pi-heif' están instaladas."""
        return heif_support_available()

    def _ensure_ready(self) -> None:
        """Registra el formato en Pillow antes de abrir el archivo."""
        if not heif_support_available():
            raise UnsupportedSourceError(_INSTALL_HINT)
