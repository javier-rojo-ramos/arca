"""Escritura de las etiquetas de un MP3 (ID3v2 e ID3v1): lo propio de la familia ID3.

Este módulo NO depende de Qt ni de la base de datos. Es el escritor de la familia ID3 del
motor de escritura ('tag_writer.py', que hace lo común: el temporal, comprobar que tiene las
etiquetas previstas y sustituir el original; ver su docstring). Solo lo usa el motor.

CÓMO ESCRIBE UN MP3 (docs/MOD_MUSICA.md §5; reglas acordadas con el autor el 16 y el
27/11/2026):
    - ID3v2, con mutagen SIN CONVERTIR la etiqueta ('translate=False', 'load_v1=False') y
      guardándola en su versión: solo cambian los marcos de lo editado y los demás quedan con
      el mismo contenido. mutagen reescribe la etiqueta entera (el orden de los marcos puede
      cambiar); guardar como dice su documentación borraría marcos (docs/TRAMPAS.md). Si la
      etiqueta trae marcos repetidos que mutagen no conservaría (dos letras con la misma
      descripción e idioma, dos valoraciones del mismo reproductor...), no se escribe; los
      de texto repetidos (también los comentarios) los junta en uno, con todos sus
      valores. Si el ID3v2 se crea (no tenía, o era un 2.2, que mutagen no escribe), se
      parte de lo que se lee del archivo (su ID3v1, o su 2.2 convertido), con el
      comentario del ID3v1 como comentario.
    - ID3v1, lo quita y lo vuelve a poner la aplicación ('id3v1.py'): solo lo editado,
      adaptado a sus límites; uno nuevo (si la preferida lo incluye), con todo.
    - Comprueba el temporal (además de lo común, en el motor): que lo editado se lee como se
      pidió (como lo lee el catálogo, 'tags_from_id3', adaptado a la versión) y lo demás,
      como antes (en un ID3v2 que ya estaba, marco a marco); el ID3v1; y el AUDIO: la
      huella de todo lo que hay entre el ID3v2 y el ID3v1 (con un APEv2, si lo hay), igual
      que la del original.

Lo que se escribe va en la codificación de su versión: UTF-16 en v2.3 y UTF-8 en v2.4 (como
Mp3tag). Varios valores («Rock; Pop») en el artista, el artista del álbum, el compositor y el
género: en v2.4, valores separados; en v2.3, un texto tal cual (mutagen los uniría con «/», que
se confunde con «AC/DC»). El título, el álbum y el comentario, siempre un texto. La fecha: en
v2.4, TDRC; en v2.3, TYER y, si es completa, TDAT (el mes sin día no cabe en v2.3: queda el
año); si el archivo traía la de la otra versión, también se cambia, para que no digan cosas
distintas; la hora (TIME) se quita. El comentario es el COMM sin descripción (los de iTunes y
otros programas no se tocan), con el idioma del que hubiera o «eng». La pista y el disco,
con dos cifras al menos («03/12»; el total, sin ceros: 'tag_map.pair_number_text'), también
en un ID3v2 nuevo, aunque no se hayan editado (toda la etiqueta la escribe la aplicación).

Usa dos cosas internas de mutagen 1.48 (si cambian, falla la autoprueba): 'read_frames' y la
cabecera ya leída, para saber si se perdería algún marco repetido.

1.1.0 La pista y el disco, con dos cifras al menos («03/12»; 'tag_map.pair_number_text';
      MUS 7.1b), también en un ID3v2 nuevo (los que vienen del ID3v1 o de un 2.2).
1.0.0 Primera versión (28/11/2026; docs/MOD_MUSICA.md, paso MUS 6.3a): el código del MP3 de
      'tag_writer.py' 1.0.0 (MUS 6.1c), movido sin cambiar lo que hace.

Prueba: la del motor, de punta a punta con MP3 mínimos (allí, porque la autoprueba sustituye
funciones del motor y de este módulo para simular fallos):
    python -m core.audio.tag_writer
"""

__version__ = "1.1.0"
__all__ = ["Id3Writer"]

# Librerías estándar
import copy
import hashlib
import os
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, ClassVar

# Librerías de terceros
from mutagen.id3 import COMM, ID3, TDAT, TDRC, TYER, Encoding, Frames, ID3NoHeaderError, TextFrame
from mutagen.id3._tags import read_frames
from mutagen.mp3 import MP3

# Módulos del proyecto
from core.audio.id3v1 import ID3V1_SIZE, Id3v1Tag, apply_changes, build_id3v1, parse_id3v1
from core.audio.tag_map import (
    COMMENT,
    DATE,
    MULTI_VALUE_SEPARATOR,
    PAIR,
    TAG_FIELDS,
    pair_number_text,
    tag_field,
)
from core.audio.tag_reader import AudioTags, parse_pair, tags_from_id3
from core.audio.tag_set import TagSet
from core.audio.write_base import (
    DATE_PATTERN,
    LIST_FIELDS,
    AudioWriteError,
    FormatWriter,
    PreparedWrite,
)

# Los marcos de la fecha: el de v2.4 y los de v2.3 (año, día y mes, hora)
_DATE_FRAMES: tuple[str, ...] = ("TDRC", "TYER", "TDAT", "TIME")
# El idioma de un comentario nuevo, si no había ninguno
_DEFAULT_LANGUAGE = "eng"
_LANGUAGE_PATTERN = re.compile(r"[A-Za-z]{3}")
# Descripción con la que mutagen carga el comentario de un ID3v1
_V1_COMMENT_DESC = "ID3v1 Comment"
# Codificación de lo que se escribe, por versión de ID3v2 (como Mp3tag)
_ENCODINGS: dict[int, Encoding] = {3: Encoding.UTF16, 4: Encoding.UTF8}
# Cabecera del ID3v2: «ID3», versión, revisión, banderas y tamaño (sin la cabecera)
_ID3V2_HEADER_SIZE = 10
_ID3V2_FOOTER_FLAG = 0x10
# Bloques de lectura para la huella del audio
_CHUNK_SIZE = 1 << 20
# Los campos de pareja (la pista y el disco)
_PAIR_KEYS: tuple[str, ...] = tuple(field.key for field in TAG_FIELDS if field.kind == PAIR)


@dataclass(slots=True)
class _Id3Prepared(PreparedWrite):
    """Lo preparado para escribir un MP3 y lo que se espera encontrar en el temporal."""

    version: int  # la del ID3v2 que se escribe
    tags: ID3  # la etiqueta, ya con lo editado
    expected_view: AudioTags  # cómo la leerá el catálogo
    expected_v1: Id3v1Tag | None
    # Solo si el ID3v2 ya estaba: los marcos no editados y los desconocidos de antes
    untouched: dict[str, str] | None
    unknown: list[bytes] | None
    audio_digest: str


class Id3Writer(FormatWriter):
    """La familia ID3: los MP3 (ver el docstring del archivo)."""

    name: ClassVar[str] = "id3"

    def handles(self, audio: Any) -> bool:
        return isinstance(audio, MP3)

    def preferred(self, preferred_mp3: TagSet) -> TagSet:
        return preferred_mp3

    def prepare(
        self, path: Path, wanted: dict[str, Any], current: TagSet, target: TagSet
    ) -> PreparedWrite | None:
        return _prepare(path, wanted, current, target)

    def save(self, prepared: PreparedWrite, temp: Path) -> None:
        assert isinstance(prepared, _Id3Prepared)
        if prepared.current.id3v1:
            # El ID3v1 lo quita y lo pone la aplicación (mutagen lo rehace entero y lo
            # busca de una forma más laxa: docs/TRAMPAS.md)
            os.truncate(temp, temp.stat().st_size - ID3V1_SIZE)
        prepared.tags.save(temp, v1=0, v2_version=prepared.version, v23_sep=None)
        if prepared.expected_v1 is not None:
            with temp.open("ab") as file:
                file.write(build_id3v1(prepared.expected_v1))

    def verify(self, prepared: PreparedWrite, temp: Path) -> str | None:
        assert isinstance(prepared, _Id3Prepared)
        written = ID3(temp, translate=False, load_v1=False)
        if written.version[:2] != (2, prepared.version):
            return "la versión del ID3v2 no es la prevista"
        if _view(written) != prepared.expected_view:
            return "lo escrito no se lee como se pidió"
        if prepared.untouched is not None and (
            _untouched_frames(written, prepared.wanted) != prepared.untouched
            or list(written.unknown_frames) != prepared.unknown
        ):
            return "ha cambiado algo que no se había editado"
        expected_v1 = prepared.expected_v1
        if expected_v1 is not None and parse_id3v1(_tail(temp, ID3V1_SIZE)) != expected_v1:
            return "el ID3v1 no es el previsto"
        if _audio_digest(temp, has_v1=prepared.target.id3v1) != prepared.audio_digest:
            return "el audio no es el mismo"
        return None


def _prepare(
    path: Path, wanted: dict[str, Any], current: TagSet, target: TagSet
) -> _Id3Prepared | None:
    """Prepara la etiqueta con lo editado y lo que se espera; None si ya lo tenía.

    Raises:
        AudioWriteError: Si la etiqueta tiene marcos que mutagen perdería.
    """
    version = target.id3v2
    assert version is not None  # la preferida de un MP3 lleva un ID3v2
    encoding = _ENCODINGS[version]
    creating = current.id3v2 != version
    untouched: dict[str, str] | None = None
    unknown: list[bytes] | None = None
    if creating:
        tags = _load_new(path, version, encoding)
    else:
        tags = ID3(path, translate=False, load_v1=False)
        lost = _frames_lost_on_load(path, tags)
        if lost:
            raise AudioWriteError(
                f"«{path.name}» tiene marcos repetidos que no se conservarían al escribir "
                f"({', '.join(lost)}): no se escribe"
            )
        untouched = _untouched_frames(tags, wanted)
        unknown = list(tags.unknown_frames)

    base_view = _view(tags)
    expected_view = replace(base_view, **_apply(tags, wanted, version, encoding))
    old_v1 = parse_id3v1(_tail(path, ID3V1_SIZE)) if current.id3v1 else None
    if not target.id3v1:
        expected_v1 = None
    elif old_v1 is not None:
        expected_v1 = apply_changes(old_v1, wanted)  # solo lo editado
    else:
        expected_v1 = apply_changes(None, _all_fields(expected_view))  # uno nuevo, completo

    if not creating and expected_view == base_view and expected_v1 == old_v1:
        return None  # ya tenía lo pedido: no se toca
    return _Id3Prepared(
        wanted=wanted,
        current=current,
        target=target,
        version=version,
        tags=tags,
        expected_view=expected_view,
        expected_v1=expected_v1,
        untouched=untouched,
        unknown=unknown,
        audio_digest=_audio_digest(path, has_v1=current.id3v1),
    )


def _apply(
    tags: ID3, wanted: Mapping[str, Any], version: int, encoding: Encoding
) -> dict[str, Any]:
    """Pone lo editado en la etiqueta y devuelve cómo lo leerá el catálogo (los atributos
    de 'AudioTags' que cambian)."""
    expected: dict[str, Any] = {}
    for key, value in wanted.items():
        field = tag_field(key)
        if field.kind == COMMENT:
            _set_comment(tags, value, encoding)
            expected[key] = value
        elif field.kind == DATE:
            expected[key] = _set_date(tags, value, version, encoding)
        elif field.kind == PAIR:
            number, total = value if value is not None else (None, None)
            text = None if number is None else _pair_text(number, total)
            _set_text(tags, field.id3, None if text is None else [text], encoding)
            expected[f"{key}_number"], expected[f"{key}_total"] = number, total
        else:
            texts: list[str] | None = None
            if value is not None:
                split = version == 4 and key in LIST_FIELDS
                texts = value.split(MULTI_VALUE_SEPARATOR) if split else [value]
            _set_text(tags, field.id3, texts, encoding)
            expected[key] = value
    return expected


def _set_text(tags: ID3, frame_id: str, texts: list[str] | None, encoding: Encoding) -> None:
    """Sustituye un marco de texto (o lo quita, con None)."""
    tags.delall(frame_id)
    if texts:
        tags.add(Frames[frame_id](encoding=encoding, text=texts))


def _set_comment(tags: ID3, value: str | None, encoding: Encoding) -> None:
    """Sustituye el comentario (el COMM sin descripción); los demás COMM no se tocan."""
    plain = [frame for frame in tags.getall("COMM") if not frame.desc]
    language = plain[0].lang if plain else _DEFAULT_LANGUAGE
    if not _LANGUAGE_PATTERN.fullmatch(language or ""):
        language = _DEFAULT_LANGUAGE
    for frame in plain:
        del tags[frame.HashKey]
    if value is not None:
        tags.add(COMM(encoding=encoding, lang=language, desc="", text=[value]))


def _set_date(tags: ID3, value: str | None, version: int, encoding: Encoding) -> str | None:
    """Sustituye la fecha (ver el docstring del archivo) y devuelve cómo la leerá el
    catálogo: la entera o, si solo va en TYER y TDAT, el año y el día."""
    present = {frame_id for frame_id in _DATE_FRAMES if tags.getall(frame_id)}
    for frame_id in _DATE_FRAMES:
        tags.delall(frame_id)
    if value is None:
        return None
    match = DATE_PATTERN.fullmatch(value)
    assert match is not None  # comprobada en '_clean_date'
    year, month, day = match[1], match[2], match[3]
    with_tdrc = version == 4 or "TDRC" in present
    with_tyer = version == 3 or "TYER" in present
    if with_tdrc:
        tags.add(TDRC(encoding=encoding, text=[value]))
    if with_tyer:
        tags.add(TYER(encoding=encoding, text=[year]))
        if day is not None:
            tags.add(TDAT(encoding=encoding, text=[f"{day}{month}"]))  # TDAT es DDMM
    if with_tdrc:
        return value  # el catálogo lee TDRC antes que TYER
    return f"{year}-{month}-{day}" if day is not None else year


def _all_fields(view: AudioTags) -> dict[str, Any]:
    """Todos los campos de una etiqueta como «lo editado» (para un ID3v1 nuevo)."""
    fields: dict[str, Any] = {}
    for field in TAG_FIELDS:
        if field.kind == PAIR:
            number = getattr(view, f"{field.key}_number")
            total = getattr(view, f"{field.key}_total")
            fields[field.key] = None if number is None else (number, total)
        else:
            fields[field.key] = getattr(view, field.key)
    return fields


def _load_new(path: Path, version: int, encoding: Encoding) -> ID3:
    """Un ID3v2 nuevo, con lo que se lee del archivo (su ID3v1, o su 2.2 convertido), en
    la codificación de la versión, y el comentario del ID3v1 como comentario."""
    try:
        tags = ID3(path, translate=True, v2_version=version, load_v1=True)
    except ID3NoHeaderError:
        return ID3()  # sin ninguna etiqueta
    plain = [frame for frame in tags.getall("COMM") if not frame.desc]
    for frame in [f for f in tags.getall("COMM") if f.desc == _V1_COMMENT_DESC]:
        del tags[frame.HashKey]
        if not plain:
            comment = COMM(encoding=encoding, lang=frame.lang, desc="", text=list(frame.text))
            tags.add(comment)
            plain.append(comment)
    # La pista y el disco, con dos cifras, como todo lo que escribe la aplicación (la
    # etiqueta entera es nueva); un texto que no es un número se queda como está
    for key in _PAIR_KEYS:
        frame = tags.get(tag_field(key).id3)
        if frame is not None and frame.text:
            number, total = parse_pair(frame.text[0])
            if number is not None:
                frame.text = [_pair_text(number, total)]
    for frame in tags.values():
        if hasattr(frame, "encoding"):
            frame.encoding = encoding
    return tags


def _pair_text(number: int, total: int | None) -> str:
    """El texto de la pista o del disco: «03/12», o «03» sin total."""
    return pair_number_text(number) + (f"/{total}" if total else "")


def _view(tags: ID3) -> AudioTags:
    """Cómo lee el catálogo una etiqueta ('tags_from_id3', sobre una copia convertida a
    v2.4, como hace mutagen al leer: TYER y TDAT pasan a TDRC)."""
    translated = copy.deepcopy(tags)
    translated.update_to_v24()
    return tags_from_id3(translated)


def _untouched_frames(tags: ID3, wanted: Mapping[str, Any]) -> dict[str, str]:
    """Los marcos que no son de lo editado, por su clave, con todo su contenido (su
    'repr', con todos sus datos y su codificación): para comparar antes y después."""
    touched: set[str] = set()
    plain_comment = False
    for key in wanted:
        field = tag_field(key)
        if field.kind == DATE:
            touched.update(_DATE_FRAMES)
        elif field.kind == COMMENT:
            plain_comment = True
        else:
            touched.add(field.id3)
    return {
        frame.HashKey: repr(frame)
        for frame in tags.values()
        if frame.FrameID not in touched
        and not (plain_comment and frame.FrameID == "COMM" and not frame.desc)
    }


def _frames_lost_on_load(path: Path, tags: ID3) -> list[str]:
    """Los marcos repetidos que mutagen no conserva al cargar (se queda con el último): dos
    con la misma clave que no son de texto (esos los junta, con todos sus valores) ni
    imágenes (esas las conserva). Lee otra vez la etiqueta con 'read_frames' de mutagen."""
    header = tags._header
    offset = _ID3V2_HEADER_SIZE
    size = tags.size - _ID3V2_HEADER_SIZE
    if header.f_extended:
        extended = 4 + len(header._extdata)
        offset, size = offset + extended, size - extended
    with path.open("rb") as file:
        file.seek(offset)
        data = file.read(size)
    frames, _unknown, _rest = read_frames(header, data, Frames)
    counts = Counter(
        frame.HashKey
        for frame in frames
        if frame.FrameID != "APIC" and not isinstance(frame, TextFrame)
    )
    return sorted(key for key, count in counts.items() if count > 1)


def _tail(path: Path, size: int) -> bytes:
    """Los últimos bytes de un archivo."""
    with path.open("rb") as file:
        file.seek(0, os.SEEK_END)
        file.seek(max(0, file.tell() - size))
        return file.read()


def _audio_digest(path: Path, *, has_v1: bool) -> str:
    """La huella de todo lo que hay entre el ID3v2 y el ID3v1 (el audio y, si lo hay, un
    APEv2): tiene que ser la misma antes y después de escribir."""
    with path.open("rb") as file:
        start = _id3v2_size(file.read(_ID3V2_HEADER_SIZE))
        file.seek(0, os.SEEK_END)
        end = file.tell() - (ID3V1_SIZE if has_v1 else 0)
        file.seek(start)
        digest = hashlib.blake2b(digest_size=16)
        remaining = end - start
        while remaining > 0:
            chunk = file.read(min(_CHUNK_SIZE, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def _id3v2_size(header: bytes) -> int:
    """Lo que ocupa el ID3v2 del principio del archivo (cabecera, marcos, relleno y pie);
    0 si no tiene."""
    if len(header) < _ID3V2_HEADER_SIZE or not header.startswith(b"ID3"):
        return 0
    size = 0
    for byte in header[6:10]:  # cuatro bytes de 7 bits («synchsafe»)
        size = (size << 7) | (byte & 0x7F)
    footer = _ID3V2_HEADER_SIZE if header[3] == 4 and header[5] & _ID3V2_FOOTER_FLAG else 0
    return _ID3V2_HEADER_SIZE + size + footer
