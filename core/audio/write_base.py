"""Lo común a los escritores de etiquetas de cada formato: interfaz, errores, lo editado.

Este módulo NO depende de Qt ni de la base de datos. Lo usan el motor de escritura
('tag_writer.py': el recorrido común de toda escritura, que elige la familia) y el escritor
de cada familia de etiquetas ('id3_writer.py', el MP3; 'vorbis_writer.py', FLAC, Ogg y Opus;
'mp4_writer.py', M4A).

    FormatWriter      la interfaz de una familia: qué archivos atiende, su etiqueta
                      preferida, y preparar, guardar y comprobar lo editado
    PreparedWrite     lo preparado para escribir un archivo (cada familia añade lo suyo)
    clean_changes     lo editado, comprobado y limpio: igual para todas las familias
    TagWriteResult, AudioWriteError, UnsupportedAudioWriteError

LO EDITADO ('changes'): las claves de 'tag_map.TAG_FIELDS' y None para vaciar. Los textos y
la fecha («2001», «2001-05» o «2001-05-04»), como texto; la pista y el disco, como la pareja
(número, total), con None en lo que falte (sin número, se borra la pareja entera). Lo que no
vale (una clave que no es de la tabla, una fecha mal escrita, un número que no es positivo)
es 'ValueError' ('TypeError' si no es un texto): es un error de quien llama, no del archivo.
Varios valores («Rock; Pop») en el artista, el artista del álbum, el compositor y el género
('LIST_FIELDS'), sin repetidos; cada familia decide cómo los guarda.

1.0.1 Los comentarios, al día con las familias que se escriben (MUS 6.4).
1.0.0 Primera versión (28/11/2026; docs/MOD_MUSICA.md, paso MUS 6.3a): lo común de
      'tag_writer.py' 1.0.0 (MUS 6.1c), movido sin cambiar lo que hace, y la interfaz de una
      familia ('FormatWriter', 'PreparedWrite').

Prueba rápida (desde la raíz del proyecto; sin archivos):
    python -m core.audio.write_base
"""

__version__ = "1.0.1"
__all__ = [
    "DATE_PATTERN",
    "LIST_FIELDS",
    "WRITE_ERRORS",
    "AudioWriteError",
    "FormatWriter",
    "PreparedWrite",
    "TagWriteResult",
    "UnsupportedAudioWriteError",
    "clean_changes",
]

# Librerías estándar
import re
import struct
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

# Librerías de terceros
from mutagen import MutagenError

# Módulos del proyecto
from core.audio.tag_map import DATE, MULTI_VALUE_SEPARATOR, PAIR, tag_field
from core.audio.tag_reader import AudioReadError
from core.audio.tag_set import TagSet

# Los campos que pueden tener varios valores (cada familia decide cómo los guarda)
LIST_FIELDS: frozenset[str] = frozenset({"artist", "album_artist", "composer", "genre"})
# Una fecha: el año y, si los trae, el mes y el día
DATE_PATTERN = re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?")
# Un año menor no es un año («0000» es lo que escriben algunos programas sin dato)
_FIRST_YEAR = 1000

# Errores que pueden dar mutagen o el disco al preparar o escribir (se dan como
# 'AudioWriteError'; lo que no vale de lo editado se comprueba antes, como 'ValueError')
WRITE_ERRORS = (
    MutagenError, AudioReadError, OSError, ValueError, TypeError, KeyError, EOFError,
    struct.error,
)  # fmt: skip


class AudioWriteError(Exception):
    """No se ha podido escribir: el original queda como estaba."""


class UnsupportedAudioWriteError(AudioWriteError):
    """Las etiquetas de ese formato todavía no se escriben (hoy, WAV, AIFF y lo que no es
    MP3, FLAC, Ogg, Opus ni M4A)."""


@dataclass(frozen=True, slots=True)
class TagWriteResult:
    """Cómo ha ido una escritura.

    Attributes:
        written: True si se ha cambiado el archivo; False si ya tenía lo pedido.
        tags_before: Las etiquetas que tenía.
        tags_after: Las que tiene ahora (las mismas, salvo que le faltara el ID3v2).
    """

    written: bool
    tags_before: TagSet
    tags_after: TagSet

    @property
    def tags_changed(self) -> bool:
        """True si ha cambiado el tipo de etiqueta (el catálogo tiene que releerlo)."""
        return self.tags_before != self.tags_after


@dataclass(slots=True)
class PreparedWrite:
    """Lo preparado para escribir un archivo, lo común; cada familia lo amplía con lo suyo
    (su etiqueta ya con lo editado, lo que espera encontrar en el temporal...)."""

    wanted: dict[str, Any]  # lo editado, ya limpio ('clean_changes')
    current: TagSet  # las etiquetas que tiene
    target: TagSet  # las que tendrá ('tag_set.tags_for_edit')


class FormatWriter(ABC):
    """Lo propio de una familia de etiquetas (ID3, Vorbis, MP4). El motor ('tag_writer')
    hace lo demás: el temporal (una copia del original), comprobar que tiene las etiquetas
    previstas y sustituir el original. Ningún método toca el original.

    Attributes:
        name: Nombre corto de la familia, para el registro.
    """

    name: ClassVar[str] = ""

    @abstractmethod
    def handles(self, audio: Any) -> bool:
        """True si escribe en ese archivo (el objeto de mutagen de 'tag_reader.open_audio')."""

    @abstractmethod
    def preferred(self, preferred_mp3: TagSet) -> TagSet:
        """Su etiqueta preferida, la que se crea si le falta la principal
        ('preferred_mp3' es la de los MP3, la de las Opciones)."""

    @abstractmethod
    def prepare(
        self, path: Path, wanted: dict[str, Any], current: TagSet, target: TagSet
    ) -> PreparedWrite | None:
        """Prepara lo editado y lo que se espera encontrar después; None si el archivo ya
        tenía lo pedido (entonces no se toca).

        Raises:
            AudioWriteError: Si no se puede escribir sin perder algo. Los errores de
                mutagen o del disco salen tal cual: el motor los da como 'AudioWriteError'.
        """

    @abstractmethod
    def save(self, prepared: PreparedWrite, temp: Path) -> None:
        """Escribe lo preparado en el temporal (una copia del original)."""

    @abstractmethod
    def verify(self, prepared: PreparedWrite, temp: Path) -> str | None:
        """Comprueba el temporal (lo editado, lo demás, el audio): qué no es lo previsto, o
        None si todo lo es."""


def clean_changes(changes: Mapping[str, Any]) -> dict[str, Any]:
    """Lo editado, comprobado y limpio (textos sin espacios a los lados; vacío = None;
    varios valores sin repetir; la pareja sin número = None).

    Raises:
        ValueError, TypeError: Si algo no vale.
    """
    cleaned: dict[str, Any] = {}
    for key, value in changes.items():
        try:
            field = tag_field(key)
        except KeyError:
            raise ValueError(f"Campo desconocido: «{key}»") from None
        if field.kind == PAIR:
            cleaned[key] = _clean_pair(key, value)
        elif field.kind == DATE:
            cleaned[key] = _clean_date(value)
        else:
            text = _clean_text(key, value)
            if text is not None and key in LIST_FIELDS:
                text = _clean_list(text)
            cleaned[key] = text
    return cleaned


def _clean_text(key: str, value: object) -> str | None:
    """Un texto editado: sin caracteres nulos ni espacios a los lados; vacío, None."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"«{key}» tiene que ser un texto: {value!r}")
    return value.replace("\x00", "").strip() or None


def _clean_list(text: str) -> str | None:
    """Varios valores («Rock; Pop»), sin vacíos ni repetidos."""
    parts: list[str] = []
    for part in text.split(MULTI_VALUE_SEPARATOR):
        part = part.strip()
        if part and part not in parts:
            parts.append(part)
    return MULTI_VALUE_SEPARATOR.join(parts) or None


def _clean_date(value: object) -> str | None:
    """Una fecha editada: «2001», «2001-05» o «2001-05-04»; vacía, None."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"La fecha tiene que ser un texto: {value!r}")
    text = value.strip()
    if not text:
        return None
    match = DATE_PATTERN.fullmatch(text)
    if (
        not match
        or int(match[1]) < _FIRST_YEAR
        or (match[2] is not None and not 1 <= int(match[2]) <= 12)
        or (match[3] is not None and not 1 <= int(match[3]) <= 31)
    ):
        raise ValueError(f"Fecha no válida: «{value}»")
    return text


def _clean_pair(key: str, value: object) -> tuple[int, int | None] | None:
    """Una pareja editada (número, total); sin número, None (se borra entera)."""
    if value is None:
        return None
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError(f"«{key}» tiene que ser la pareja (número, total): {value!r}")
    for item in value:
        positive = isinstance(item, int) and not isinstance(item, bool) and item > 0
        if item is not None and not positive:
            raise ValueError(f"«{key}» tiene que llevar números positivos: {value!r}")
    number, total = value
    return None if number is None else (number, total)


if __name__ == "__main__":
    # Autoprueba (sin Qt ni archivos). Desde la raíz del proyecto:
    #     python -m core.audio.write_base

    # --- Lo editado, limpio: textos sin espacios a los lados (vacío, None), varios valores
    # sin repetidos, la pareja sin número = None, la fecha comprobada
    assert clean_changes({
        "title": "  Vino Tinto ", "comment": "   ", "genre": " Rock; Pop; Rock ",
        "track": (3, None), "disc": (None, 2), "date": " 2001-05 ", "album": None,
    }) == {
        "title": "Vino Tinto", "comment": None, "genre": "Rock; Pop", "track": (3, None),
        "disc": None, "date": "2001-05", "album": None,
    }  # fmt: skip
    assert clean_changes({"artist": "a\x00b"}) == {"artist": "ab"}
    assert set(LIST_FIELDS) == {"artist", "album_artist", "composer", "genre"}
    for bad, error in (
        ({"titulo": "x"}, ValueError), ({"date": "05/2001"}, ValueError),
        ({"date": "0000"}, ValueError), ({"date": "2001-13"}, ValueError),
        ({"track": (0, 1)}, ValueError), ({"track": "3/12"}, ValueError),
        ({"disc": (True, None)}, ValueError), ({"title": 3}, TypeError),
        ({"date": 2001}, TypeError),
    ):  # fmt: skip
        try:
            clean_changes(bad)
            raise AssertionError(f"debía fallar: {bad}")
        except error:
            pass

    # --- El resultado y la interfaz de una familia
    assert TagWriteResult(True, TagSet(id3v1=True), TagSet(id3v2=3, id3v1=True)).tags_changed
    assert not TagWriteResult(False, TagSet(id3v2=3), TagSet(id3v2=3)).tags_changed
    try:
        FormatWriter()  # type: ignore[abstract]
        raise AssertionError("debía fallar: FormatWriter es una interfaz")
    except TypeError:
        pass
    assert issubclass(UnsupportedAudioWriteError, AudioWriteError)

    print("Autoprueba finalizada correctamente.")
