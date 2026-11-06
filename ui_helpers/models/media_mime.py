"""Formato con el que se arrastran tarjetas de la cuadrícula (arrastrar y soltar).

Al arrastrar una o varias tarjetas, la cuadrícula ('MediaGridModel.mimeData') empaqueta
sus 'id' con este formato propio; quien recibe la soltada (p. ej. una colección de la
barra lateral) los desempaqueta con 'decode_media_ids'.

Contenido (JSON, en UTF-8):
    {"catalog": "<carpeta del catálogo>", "ids": [12, 345, ...]}

La carpeta del catálogo sirve para no mezclar 'id' de catálogos distintos: si hubiera
dos ventanas de la aplicación abiertas con catálogos diferentes, un 'id' de uno no
significa nada en el otro.
"""

__version__ = "1.0.1"
__all__ = ["MEDIA_IDS_MIME", "MediaDrag", "decode_media_ids", "encode_media_ids"]

# Librerías estándar
import json
from dataclasses import dataclass

# Librerías de terceros (Qt)
from qtpy.QtCore import QByteArray, QMimeData

# Tipo MIME propio (el prefijo 'application/x-' indica que no es estándar)
MEDIA_IDS_MIME = "application/x-arca-media-ids"


@dataclass(frozen=True, slots=True)
class MediaDrag:
    """Lo que viaja al arrastrar tarjetas.

    Attributes:
        catalog: Carpeta del catálogo de origen (texto).
        ids: 'media_items.id' de las tarjetas, en el orden de la cuadrícula.
    """

    catalog: str
    ids: tuple[int, ...]


def encode_media_ids(catalog: str, ids: list[int]) -> QMimeData:
    """Empaqueta los 'id' de unas tarjetas para arrastrarlas."""
    mime = QMimeData()
    payload = json.dumps({"catalog": catalog, "ids": [int(i) for i in ids]})
    mime.setData(MEDIA_IDS_MIME, QByteArray(payload.encode("utf-8")))
    return mime


def decode_media_ids(mime: QMimeData | None) -> MediaDrag | None:
    """Desempaqueta unas tarjetas arrastradas; None si no son de la cuadrícula o no valen."""
    if mime is None or not mime.hasFormat(MEDIA_IDS_MIME):
        return None
    try:
        data = json.loads(bytes(mime.data(MEDIA_IDS_MIME)).decode("utf-8"))
        ids = tuple(int(i) for i in data["ids"])
        catalog = str(data["catalog"])
    except (ValueError, KeyError, TypeError):
        return None
    return MediaDrag(catalog, ids) if ids else None
