"""El tipo de etiqueta de una canción, como dato, y en qué etiquetas se escribe al editarla.

Este módulo NO depende de Qt, de la base de datos ni de mutagen: es un dato y una regla.

Un archivo de audio puede llevar varias etiquetas a la vez («ID3v2.3 + ID3v1»). 'TagSet' dice
cuáles. Su texto ('TagSet.text') es el de la columna «Tag» de Mp3tag, el que muestra el
inspector y guarda el catálogo ('audio_details.tag_type'); 'TagSet.from_text' lo vuelve a
convertir en dato.

    current = TagSet.from_text("ID3v1")          # lo que tiene el archivo
    preferred = TagSet(id3v2=3)                   # la etiqueta preferida (las Opciones)
    tags_for_edit(current, preferred).text        # 'ID3v2.3 + ID3v1'

Las etiquetas:
    id3v2    ID3v2, con su versión (2, 3 o 4): la principal de MP3 (y de WAV y AIFF)
    id3v1    ID3v1: los 128 bytes del final de un MP3; antigua y limitada
    ape      APEv2 (al final de un MP3, o la de WavPack): se detecta, no se lee ni se escribe
    vorbis   comentarios Vorbis: la principal de FLAC, Ogg Vorbis y Opus
    mp4      la de M4A
    other    otra que mutagen abre y la aplicación no traduce, por su nombre ('ASF', de WMA)

EN QUÉ ETIQUETAS SE ESCRIBE AL EDITAR ('tags_for_edit'; decidido con el autor el 27/11/2026,
docs/MOD_MUSICA.md §5):
    1. En las que el archivo ya tiene, y en cada una solo los campos editados: editar nunca
       añade ni quita una etiqueta, ni cambia la versión del ID3v2.
    2. Solo si le falta la principal de su formato (un MP3 sin ID3v2, o solo con ID3v1) se
       le añade la PREFERIDA: la de las Opciones (ID3v2.3 o 2.4 y, si se marca, ID3v1). El
       escritor la crea completa, con todo lo que se lee del archivo. Lo que tenía se queda
       (un ID3v1, al día; un APEv2, sin tocar). Un ID3v2.2 (muy antiguo: mutagen no lo
       escribe) cuenta como si faltara.
    3. Cambiar el tipo de etiqueta (convertir de versión, quitar el ID3v1 o el APEv2,
       limpiar) es solo cosa de la herramienta «Reescribir etiquetas…» (MUS 8.4), a
       petición y con vista previa; su regla irá también aquí.
La codificación del texto va con la versión (v2.3, UTF-16; v2.4, UTF-8; como Mp3tag): la
decide el escritor ('tag_writer.py', MUS 6.1c).

1.1.0 'mp3_tags_from_settings': la etiqueta preferida a partir de las dos opciones de
      Opciones > Música (MUS 6.1d).
1.0.0 Primera versión (27/11/2026; docs/MOD_MUSICA.md, paso MUS 6.1a).

Prueba rápida (desde la raíz del proyecto):
    python -m core.audio.tag_set
"""

__version__ = "1.1.0"
__all__ = [
    "DEFAULT_MP3_TAGS",
    "ID3V2_VERSIONS",
    "ID3V2_WRITE_VERSIONS",
    "TagSet",
    "mp3_tags_from_settings",
    "tags_for_edit",
]

# Librerías estándar
import re
from dataclasses import dataclass, replace

# Versiones de ID3v2 que existen y las que se escriben (mutagen no escribe la 2.2)
ID3V2_VERSIONS: tuple[int, ...] = (2, 3, 4)
ID3V2_WRITE_VERSIONS: tuple[int, ...] = (3, 4)

# Los nombres de cada etiqueta en el texto (los de la columna «Tag» de Mp3tag)
_ID3V2_TEXT = "ID3v2.{}"
_ID3V1_TEXT = "ID3v1"
_APE_TEXT = "APEv2"
_VORBIS_TEXT = "Vorbis"
_MP4_TEXT = "MP4"
_SEPARATOR = " + "
_ID3V2_PATTERN = re.compile(r"ID3v2\.(\d)")
# Lo que empieza así es de ID3: si no es una de las de arriba, el texto está mal
_ID3_PREFIX = "ID3"


@dataclass(frozen=True, slots=True)
class TagSet:
    """Las etiquetas de un archivo de audio: las que tiene o las que tendrá.

    Attributes:
        id3v2: Versión de su ID3v2 (2, 3 o 4); None si no tiene.
        id3v1: Si tiene ID3v1.
        ape: Si tiene APEv2.
        vorbis: Si tiene comentarios Vorbis.
        mp4: Si tiene etiqueta MP4.
        other: Otra etiqueta que la aplicación no traduce, por su nombre ('ASF'); vacío si no.

    Raises:
        ValueError: Si la versión de ID3v2 no existe.
    """

    id3v2: int | None = None
    id3v1: bool = False
    ape: bool = False
    vorbis: bool = False
    mp4: bool = False
    other: str = ""

    def __post_init__(self) -> None:
        if self.id3v2 is not None and self.id3v2 not in ID3V2_VERSIONS:
            raise ValueError(f"No existe la versión de ID3v2 «2.{self.id3v2}»")

    @property
    def text(self) -> str:
        """El tipo de etiqueta como texto, como la columna «Tag» de Mp3tag: la principal
        primero y después las del final del archivo («ID3v2.3 + ID3v1 + APEv2»). Vacío si
        no tiene ninguna."""
        parts: list[str] = []
        if self.id3v2 is not None:
            parts.append(_ID3V2_TEXT.format(self.id3v2))
        if self.vorbis:
            parts.append(_VORBIS_TEXT)
        if self.mp4:
            parts.append(_MP4_TEXT)
        if self.other:
            parts.append(self.other)
        if self.id3v1:
            parts.append(_ID3V1_TEXT)
        if self.ape:
            parts.append(_APE_TEXT)
        return _SEPARATOR.join(parts)

    def is_empty(self) -> bool:
        """True si no tiene ninguna etiqueta."""
        return self == TagSet()

    @classmethod
    def from_text(cls, text: str | None) -> "TagSet":
        """El dato de un texto como los de 'text' (el que guarda el catálogo).

        None o vacío: sin etiquetas. Un nombre que no es de ninguna de las conocidas es
        'other' ('ASF').

        Raises:
            ValueError: Si el texto no puede ser de 'text': una parte vacía o repetida, un
                nombre de ID3 que no existe («ID3v2.5», «ID3v3»), dos desconocidas.
        """
        values: dict[str, object] = {}
        for raw_part in text.split(_SEPARATOR) if text else ():
            part = raw_part.strip()
            match = _ID3V2_PATTERN.fullmatch(part)
            if match:
                key, value = "id3v2", int(match.group(1))  # la versión la comprueba la clase
            elif part == _ID3V1_TEXT:
                key, value = "id3v1", True
            elif part == _APE_TEXT:
                key, value = "ape", True
            elif part == _VORBIS_TEXT:
                key, value = "vorbis", True
            elif part == _MP4_TEXT:
                key, value = "mp4", True
            elif part and not part.startswith(_ID3_PREFIX):
                key, value = "other", part
            else:
                raise ValueError(f"Tipo de etiqueta no válido: «{text}»")
            if key in values:
                raise ValueError(f"Tipo de etiqueta con una parte repetida: «{text}»")
            values[key] = value
        return cls(**values)


# La etiqueta preferida de los MP3 mientras no se elija otra en las Opciones: ID3v2.3 (en
# UTF-16), sin ID3v1, como el Mp3tag del autor (27/11/2026)
DEFAULT_MP3_TAGS = TagSet(id3v2=3)


def mp3_tags_from_settings(id3_version: object, include_id3v1: object) -> TagSet:
    """La etiqueta preferida de los MP3 a partir de sus dos opciones (Opciones > Música:
    las claves 'audio_id3_version' y 'audio_include_id3v1' de settings.json).

    Cada una que no valga (una versión que no se escribe, algo que no es un sí o un no),
    la de 'DEFAULT_MP3_TAGS': así la página de las Opciones y el trabajo de escritura
    entienden lo mismo de un settings.json tocado a mano.
    """
    valid_version = (
        isinstance(id3_version, int)
        and not isinstance(id3_version, bool)
        and id3_version in ID3V2_WRITE_VERSIONS
    )
    return TagSet(
        id3v2=id3_version if valid_version else DEFAULT_MP3_TAGS.id3v2,
        id3v1=include_id3v1 if isinstance(include_id3v1, bool) else DEFAULT_MP3_TAGS.id3v1,
    )


def tags_for_edit(current: TagSet, preferred: TagSet) -> TagSet:
    """Las etiquetas que tendrá un archivo tras escribir en él lo editado (reglas 1 y 2 de
    la cabecera): las que tiene y, si le falta la principal, la preferida.

    Args:
        current: Las que tiene ahora.
        preferred: La preferida de SU formato (la elige quien llama): en MP3, la de las
            Opciones; en FLAC y Ogg, Vorbis; en M4A, MP4.

    Raises:
        ValueError: Si 'preferred' no vale como preferida: tiene que tener una sola
            principal que se pueda escribir (ID3v2.3 o 2.4, Vorbis o MP4); el ID3v1, solo
            junto a un ID3v2; ni APEv2 ni otras.
    """
    _check_preferred(preferred)
    if preferred.id3v2 is not None:
        if current.id3v2 in ID3V2_WRITE_VERSIONS:
            return current  # regla 1: las que tiene, con su versión
        # Regla 2: sin un ID3v2 que se pueda escribir (ninguno, o un 2.2), la preferida; lo
        # que tenía se queda (su ID3v1 y su APEv2)
        return replace(current, id3v2=preferred.id3v2, id3v1=current.id3v1 or preferred.id3v1)
    if preferred.vorbis:
        return current if current.vorbis else replace(current, vorbis=True)
    return current if current.mp4 else replace(current, mp4=True)


def _check_preferred(preferred: TagSet) -> None:
    """Comprueba que una etiqueta vale como preferida (ver 'tags_for_edit').

    Raises:
        ValueError: Si no vale.
    """
    mains = (preferred.id3v2 is not None, preferred.vorbis, preferred.mp4)
    if mains.count(True) != 1:
        raise ValueError(
            f"La etiqueta preferida necesita una principal, y solo una: «{preferred.text}»"
        )
    if preferred.id3v2 is not None and preferred.id3v2 not in ID3V2_WRITE_VERSIONS:
        raise ValueError(f"El ID3v2.{preferred.id3v2} no se puede escribir")
    if preferred.id3v1 and preferred.id3v2 is None:
        raise ValueError("El ID3v1 solo puede ir junto a un ID3v2")
    if preferred.ape or preferred.other:
        raise ValueError(f"La etiqueta preferida no puede llevar «{preferred.text}»")


if __name__ == "__main__":
    # Autoprueba (sin Qt, sin mutagen y sin archivos). Desde la raíz del proyecto:
    #     python -m core.audio.tag_set

    # --- El texto: el mismo que daba el lector antes de este módulo (y que guarda el
    # catálogo), en el mismo orden: la principal, después ID3v1 y APEv2
    texts = {
        "": TagSet(),
        "ID3v2.3": TagSet(id3v2=3),
        "ID3v2.4": TagSet(id3v2=4),
        "ID3v2.2": TagSet(id3v2=2),
        "ID3v1": TagSet(id3v1=True),
        "ID3v2.3 + ID3v1": TagSet(id3v2=3, id3v1=True),
        "ID3v2.4 + APEv2": TagSet(id3v2=4, ape=True),
        "ID3v2.3 + ID3v1 + APEv2": TagSet(id3v2=3, id3v1=True, ape=True),
        "APEv2": TagSet(ape=True),
        "Vorbis": TagSet(vorbis=True),
        "MP4": TagSet(mp4=True),
        "ASF": TagSet(other="ASF"),
    }
    for text, tag_set in texts.items():
        assert tag_set.text == text, (tag_set, text)
        assert TagSet.from_text(text) == tag_set, text  # ida y vuelta
    assert TagSet.from_text(None) == TagSet() and TagSet().is_empty()
    assert not TagSet(id3v1=True).is_empty()
    # Con otro orden o espacios de más, el mismo dato
    assert TagSet.from_text("ID3v1 + ID3v2.3") == TagSet(id3v2=3, id3v1=True)
    assert TagSet.from_text(" ID3v2.4 +  APEv2 ") == TagSet(id3v2=4, ape=True)
    # Textos que no pueden ser de 'text'
    for bad in ("ID3v2.5", "ID3v3", "ID3v2.3 + ID3v2.4", "ID3v1 + ID3v1", "ID3v2.3 + ",
                "ASF + WMA"):  # fmt: skip
        try:
            TagSet.from_text(bad)
            raise AssertionError(f"debía fallar: {bad!r}")
        except ValueError:
            pass
    try:
        TagSet(id3v2=1)
        raise AssertionError("debía fallar: ID3v2.1")
    except ValueError:
        pass

    # --- Al editar: la tabla acordada con el autor (27/11/2026)
    v23, v24 = TagSet(id3v2=3), TagSet(id3v2=4)
    v23_v1, v24_v1 = TagSet(id3v2=3, id3v1=True), TagSet(id3v2=4, id3v1=True)
    cases = [
        # (lo que tiene, la preferida, lo que tendrá)
        ("ID3v2.3", v23, "ID3v2.3"),
        ("ID3v2.3", v24_v1, "ID3v2.3"),  # ni cambia la versión ni se añade ID3v1
        ("ID3v2.4", v23, "ID3v2.4"),
        ("ID3v2.3 + ID3v1", v23, "ID3v2.3 + ID3v1"),  # el ID3v1 no se quita
        ("ID3v2.3 + APEv2", v23_v1, "ID3v2.3 + APEv2"),
        ("ID3v1", v23, "ID3v2.3 + ID3v1"),  # le falta la principal: la preferida
        ("ID3v1", v24_v1, "ID3v2.4 + ID3v1"),
        ("", v23, "ID3v2.3"),
        ("", v23_v1, "ID3v2.3 + ID3v1"),
        ("", v24, "ID3v2.4"),
        ("APEv2", v23, "ID3v2.3 + APEv2"),
        ("ID3v2.2", v23, "ID3v2.3"),  # la 2.2 no se escribe: cuenta como si faltara
        ("ID3v2.2 + ID3v1", v24_v1, "ID3v2.4 + ID3v1"),
        ("Vorbis", TagSet(vorbis=True), "Vorbis"),
        ("", TagSet(vorbis=True), "Vorbis"),
        ("MP4", TagSet(mp4=True), "MP4"),
        ("", TagSet(mp4=True), "MP4"),
    ]
    for current, preferred, expected in cases:
        result = tags_for_edit(TagSet.from_text(current), preferred)
        assert result.text == expected, (current, preferred.text, result.text)
    assert tags_for_edit(TagSet(), DEFAULT_MP3_TAGS).text == "ID3v2.3"

    # --- La preferida de las Opciones; lo que no valga, la de partida
    assert mp3_tags_from_settings(3, False) == DEFAULT_MP3_TAGS
    assert mp3_tags_from_settings(4, True) == TagSet(id3v2=4, id3v1=True)
    assert mp3_tags_from_settings(None, None) == DEFAULT_MP3_TAGS  # sin guardar
    for bad_version in (2, 5, "4", 4.0, True):
        assert mp3_tags_from_settings(bad_version, True) == TagSet(id3v2=3, id3v1=True)
    assert mp3_tags_from_settings(4, "sí") == TagSet(id3v2=4)
    tags_for_edit(TagSet(), mp3_tags_from_settings("x", 1))  # siempre vale como preferida

    # --- Lo que no vale como preferida
    for bad_preferred in (
        TagSet(),  # sin principal
        TagSet(id3v2=2),  # la 2.2 no se escribe
        TagSet(id3v1=True),  # solo ID3v1
        TagSet(vorbis=True, id3v1=True),  # ID3v1 sin ID3v2
        TagSet(id3v2=3, vorbis=True),  # dos principales
        TagSet(id3v2=3, ape=True),
        TagSet(mp4=True, other="ASF"),
    ):
        try:
            tags_for_edit(TagSet(), bad_preferred)
            raise AssertionError(f"debía fallar: {bad_preferred}")
        except ValueError:
            pass

    print("Autoprueba finalizada correctamente.")
