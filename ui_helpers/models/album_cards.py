"""Los textos de la tarjeta de un álbum (vista de álbumes de Música; MUS 5.3).

Este módulo NO depende de Qt: recibe la fila de un álbum ('core/catalog/album_rows.py') y
devuelve sus textos. Lo usa el modelo de la cuadrícula ('MediaGridModel') para los roles de
una tarjeta agrupada:

    card_name(row)      el nombre, en la banda de la tarjeta     «Destrangis», «Sin álbum»
    card_label(row)     la insignia, en lugar de la duración     «13 canciones», «1 canción»
    card_tooltip(row)   el texto emergente                       «Estopa · 2001 · 13 canciones · 52:10»

Decidido por el autor el 26/11/2026 (docs/MOD_MUSICA.md §7.5). Lo que falta, con los textos
de la barra de Música («Sin álbum», «Sin artista»: 'music_sections.py'); los años, como en
«Artistas» («1974 – 2011»).

1.0.0 Primera versión (26/11/2026; docs/MOD_MUSICA.md, paso MUS 5.3).

Prueba rápida (desde la raíz del proyecto):
    python -m ui_helpers.models.album_cards
"""

__version__ = "1.0.0"
__all__ = ["card_label", "card_name", "card_tooltip"]

# Librerías estándar
from collections.abc import Mapping
from typing import Any

# Módulos del proyecto
from ui_helpers.inspector.formatting import format_count, format_duration
from ui_helpers.sidebars.sections.music_sections import NO_ALBUM_TEXT, NO_ARTIST_TEXT

_SEPARATOR = " · "


def card_name(row: Mapping[str, Any]) -> str:
    """El nombre de la tarjeta: el del álbum («Sin álbum» si las canciones no lo tienen)."""
    return row.get("album") or NO_ALBUM_TEXT


def card_label(row: Mapping[str, Any]) -> str:
    """Cuántas canciones: «1 canción», «13 canciones», «1.204 canciones»."""
    count = int(row.get("group_count") or 0)
    return f"{format_count(count)} {'canción' if count == 1 else 'canciones'}"


def card_tooltip(row: Mapping[str, Any]) -> str:
    """El artista, los años, las canciones y la duración: «Estopa · 2001 · 13 canciones ·
    52:10» (lo que no tiene, no sale; sin artista, «Sin artista»)."""
    parts = [row.get("artist") or NO_ARTIST_TEXT]
    low, high = row.get("year_min"), row.get("year_max")
    if low is not None:
        parts.append(str(low) if high in (None, low) else f"{low} – {high}")
    parts.append(card_label(row))
    duration = format_duration(row.get("duration"))
    if duration:
        parts.append(duration)
    return _SEPARATOR.join(parts)


if __name__ == "__main__":
    # Autoprueba (sin Qt). Ejecutar desde la raíz:  python -m ui_helpers.models.album_cards
    album = {"album": "Destrangis", "artist": "Estopa", "year_min": 2001, "year_max": 2001,
             "group_count": 13, "duration": 3130.0}  # fmt: skip
    assert card_name(album) == "Destrangis" and card_label(album) == "13 canciones"
    assert card_tooltip(album) == "Estopa · 2001 · 13 canciones · 52:10", card_tooltip(album)
    span = {"album": "Grandes Éxitos", "artist": None, "year_min": 1974, "year_max": 2011,
            "group_count": 1, "duration": None}  # fmt: skip
    assert card_tooltip(span) == "Sin artista · 1974 – 2011 · 1 canción", card_tooltip(span)
    loose = {"album": None, "artist": "Estopa", "group_count": 1204}
    assert card_name(loose) == "Sin álbum" and card_label(loose) == "1.204 canciones"
    assert card_tooltip(loose) == "Estopa · 1.204 canciones"
    print("Autoprueba finalizada correctamente.")
