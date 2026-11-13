"""Roles de datos personalizados que comparten el modelo de la cuadrícula y su delegado.

El modelo ('MediaGridModel') y el delegado ('ThumbnailsDelegate') se hablan solo a través
de estos roles, de modo que ninguno de los dos necesita conocer al otro.

Los dos primeros ('ROLE_RATING' y 'ROLE_FLAGGED') mantienen los valores que tenían en el
prototipo ('core/workers/thumbnail_worker.py').

1.4.0 'ROLE_HAS_LOCATION': si el elemento tiene coordenadas (la chincheta de la tira del mapa).
"""

__version__ = "1.4.0"
# ruff: noqa: RUF022
__all__ = [
    "ROLE_AVAILABILITY",
    "ROLE_COLOR_LABEL",
    "ROLE_DURATION",
    "ROLE_FLAG",
    "ROLE_FLAGGED",
    "ROLE_HAS_LOCATION",
    "ROLE_LIBRARY",
    "ROLE_MEDIA_ID",
    "ROLE_MEDIA_TYPE",
    "ROLE_QUICK_SELECTION",
    "ROLE_RATING",
    "ROLE_THUMBNAIL_STATUS",
]

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt

_USER = Qt.ItemDataRole.UserRole

ROLE_RATING = _USER + 1  # int 0-5
ROLE_FLAGGED = _USER + 2  # bool: True si la marca es "marcada" (compatibilidad con el prototipo)
ROLE_FLAG = _USER + 3  # int: -1 rechazada, 0 sin marca, 1 marcada (como Lightroom)
ROLE_COLOR_LABEL = _USER + 4  # str canónico ('red'...'purple') o None
ROLE_MEDIA_ID = _USER + 5  # int: 'media_items.id' del elemento
# int: si el archivo está en disco: 0 disponible, 1 ausente, 2 ubicación desconectada
# (AVAILABLE, MISSING y OFFLINE de 'core.catalog.media_queries')
ROLE_AVAILABILITY = _USER + 6
# bool: si el elemento está en la "Selección rápida" (el círculo de la tarjeta)
ROLE_QUICK_SELECTION = _USER + 7
# Para el marcador de las tarjetas sin miniatura y la insignia de duración (paso 4a):
# str: tipo de medio ('photo', 'video', 'audio', 'ebook', 'track')
ROLE_MEDIA_TYPE = _USER + 8
# float o None: duración en segundos (vídeo y audio)
ROLE_DURATION = _USER + 9
# str o None: biblioteca ('image', 'video'...; None = sin clasificar)
ROLE_LIBRARY = _USER + 10
# int: estado de la miniatura (0 pendiente, 1 lista, 2 error)
ROLE_THUMBNAIL_STATUS = _USER + 11
# bool: si tiene coordenadas (latitud y longitud; la chincheta de la tira del mapa)
ROLE_HAS_LOCATION = _USER + 12
