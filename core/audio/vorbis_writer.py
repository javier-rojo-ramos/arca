"""Escritura de los comentarios Vorbis (FLAC, Ogg Vorbis y Opus): lo propio de esta familia.

Este módulo NO depende de Qt ni de la base de datos. Es el escritor de la familia Vorbis del
motor de escritura ('tag_writer.py', que hace lo común: el temporal, comprobar que tiene las
etiquetas previstas y sustituir el original; ver su docstring). Solo lo usa el motor.

CÓMO ESCRIBE (docs/MOD_MUSICA.md, «Cómo se escribe en Vorbis»; acordado con el autor el
28/11/2026, tras mirar sus 14 FLAC y 13 Ogg Vorbis):
    1. El nombre de cada campo: el principal ('tag_map.TagField.vorbis[0]': TITLE, ARTIST,
       ALBUM, ALBUMARTIST, TRACKNUMBER, TRACKTOTAL, DISCNUMBER, DISCTOTAL, GENRE, COMPOSER,
       COMMENT, DATE), conservando cómo lo escribe el archivo (mayúsculas o minúsculas). Los
       otros nombres del mismo campo que use el archivo («ALBUM ARTIST», «TOTALTRACKS»,
       «TOTALDISCS», «DESCRIPTION», «YEAR»), también, con el mismo valor; al vaciar un campo
       se quitan todos (si no, al releer volvería el valor antiguo: el lector toma el primero
       que tenga valor).
    2. La pista y su total, en campos separados (TRACKNUMBER=3, TRACKTOTAL=12), como Mp3tag;
       si el archivo usa «3/12» en TRACKNUMBER, se mantiene esa forma (y los otros nombres
       del total que tenga, al día). Sin total, se quitan sus campos. El número, tal cual
       (el cero delante es M10: docs/MOD_MUSICA.md).
    3. Varios valores («Rock; Pop») en el artista, el artista del álbum, el compositor y el
       género, separados de verdad (un GENRE por valor); el título, el álbum, el comentario y
       la fecha, un texto.
    4. Lo demás no se toca: los otros campos (ORGANIZATION, REPLAYGAIN..., ENCODER), el
       «vendor», las imágenes (los bloques PICTURE del FLAC; METADATA_BLOCK_PICTURE en los
       Ogg, que es un campo más) y los demás bloques del FLAC. El orden de los campos puede
       cambiar (mutagen pone al final los que cambia). Un FLAC sin bloque de comentarios
       recibe uno con lo editado.
    5. Comprueba el temporal (además de lo común, en el motor): que lo editado se lee como se
       pidió (como lo lee el catálogo, 'tags_from_vorbis'), que los demás campos y el vendor
       son los de antes y el AUDIO:
         - FLAC: los demás bloques (STREAMINFO, con la huella MD5 del audio; las imágenes...)
           iguales, y la huella de las tramas de audio (todo lo que sigue a los bloques),
           la misma. Sin relleno (los FLAC del autor no tienen), mutagen reescribe el
           archivo entero, y añade relleno para la próxima vez.
         - Ogg: al guardar, mutagen rehace las páginas de las cabeceras (y rellena con ceros
           el paquete de los comentarios) y puede volver a numerar las siguientes: cambian
           sus bytes, no el audio. Se comparan los paquetes de cabecera (menos el de los
           comentarios), cada paquete de audio y la posición (granule) de cada página de
           audio, y lo mismo de cualquier otro flujo del archivo.
Ogg FLAC y Speex (muy raros) no se escriben.

1.0.0 Primera versión (28/11/2026; docs/MOD_MUSICA.md, paso MUS 6.3b).

Prueba: la del motor, de punta a punta con archivos mínimos (FLAC, Ogg Vorbis y Opus):
    python -m core.audio.tag_writer
"""

__version__ = "1.0.0"
__all__ = ["VorbisWriter"]

# Librerías estándar
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, ClassVar

# Librerías de terceros
import mutagen
from mutagen.flac import FLAC
from mutagen.ogg import OggPage
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

# Módulos del proyecto
from core.audio.tag_map import MULTI_VALUE_SEPARATOR, PAIR, TagField, tag_field
from core.audio.tag_reader import AudioTags, tags_from_vorbis
from core.audio.tag_set import TagSet
from core.audio.write_base import LIST_FIELDS, AudioWriteError, FormatWriter, PreparedWrite

# La etiqueta de esta familia (no hay nada que elegir en las Opciones)
_VORBIS_TAGS = TagSet(vorbis=True)
# Los formatos que escribe
_FORMATS: tuple[type, ...] = (FLAC, OggVorbis, OggOpus)
# FLAC: su marca, los bloques que se rehacen (los comentarios y el relleno) y el bit de
# «último bloque» de la cabecera de cada uno
_FLAC_MARK = b"fLaC"
_FLAC_REWRITTEN_BLOCKS: frozenset[int] = frozenset({1, 4})  # relleno, comentarios
_FLAC_LAST_BLOCK = 0x80
_ID3V2_HEADER_SIZE = 10
# Ogg: cuántos paquetes de cabecera tiene cada formato; el de los comentarios es el segundo
_OGG_HEADER_PACKETS: dict[type, int] = {OggVorbis: 3, OggOpus: 2}
_OGG_COMMENT_PACKET = 1
# Bloques de lectura para la huella del audio
_CHUNK_SIZE = 1 << 20


@dataclass(slots=True)
class _VorbisPrepared(PreparedWrite):
    """Lo preparado para escribir un FLAC, un Ogg Vorbis o un Opus, y lo que se espera
    encontrar en el temporal."""

    audio: Any  # el objeto de mutagen (FLAC, OggVorbis u OggOpus), ya con lo editado
    expected_view: AudioTags  # cómo lo leerá el catálogo
    untouched: list[tuple[str, str]]  # los campos no editados (clave, valor), ordenados
    vendor: str
    flac_blocks: list[tuple[int, bytes]] | None  # FLAC: los bloques que no se rehacen
    audio_digest: str


class VorbisWriter(FormatWriter):
    """La familia Vorbis: FLAC, Ogg Vorbis y Opus (ver el docstring del archivo)."""

    name: ClassVar[str] = "vorbis"

    def handles(self, audio: Any) -> bool:
        return isinstance(audio, _FORMATS)

    def preferred(self, preferred_mp3: TagSet) -> TagSet:
        return _VORBIS_TAGS

    def prepare(
        self, path: Path, wanted: dict[str, Any], current: TagSet, target: TagSet
    ) -> PreparedWrite | None:
        audio = mutagen.File(path)
        if not isinstance(audio, _FORMATS):
            raise AudioWriteError(f"«{path.name}» ya no es un FLAC, un Ogg Vorbis ni un Opus")
        if audio.tags is None:
            audio.add_tags()  # un FLAC sin bloque de comentarios
        tags = audio.tags
        base_view = tags_from_vorbis(tags)
        names = _edited_names(wanted)
        untouched = _untouched(tags, names)
        expected_view = replace(base_view, **_apply(tags, wanted))
        if current == target and expected_view == base_view:
            return None  # ya tenía lo pedido: no se toca
        return _VorbisPrepared(
            wanted=wanted,
            current=current,
            target=target,
            audio=audio,
            expected_view=expected_view,
            untouched=untouched,
            vendor=tags.vendor,
            flac_blocks=_flac_blocks(audio),
            audio_digest=_audio_digest(path, type(audio)),
        )

    def save(self, prepared: PreparedWrite, temp: Path) -> None:
        assert isinstance(prepared, _VorbisPrepared)
        prepared.audio.save(temp)

    def verify(self, prepared: PreparedWrite, temp: Path) -> str | None:
        assert isinstance(prepared, _VorbisPrepared)
        written = type(prepared.audio)(temp)
        tags = written.tags
        if tags is None:
            return "no tiene comentarios"
        if tags_from_vorbis(tags) != prepared.expected_view:
            return "lo escrito no se lee como se pidió"
        if (
            _untouched(tags, _edited_names(prepared.wanted)) != prepared.untouched
            or tags.vendor != prepared.vendor
        ):
            return "ha cambiado algo que no se había editado"
        if prepared.flac_blocks is not None and _flac_blocks(written) != prepared.flac_blocks:
            return "ha cambiado un bloque del FLAC que no se había editado (una imagen...)"
        if _audio_digest(temp, type(written)) != prepared.audio_digest:
            return "el audio no es el mismo"
        return None


# =============================================================================
# Lo editado
# =============================================================================


def _apply(tags: Any, wanted: Mapping[str, Any]) -> dict[str, Any]:
    """Pone lo editado en los comentarios y devuelve cómo lo leerá el catálogo (los
    atributos de 'AudioTags' que cambian)."""
    expected: dict[str, Any] = {}
    for key, value in wanted.items():
        field = tag_field(key)
        if field.kind == PAIR:
            number, total = value if value is not None else (None, None)
            _set_pair(tags, field, number, total)
            expected[f"{key}_number"], expected[f"{key}_total"] = number, total
        else:
            values: list[str] | None = None
            if value is not None:
                values = value.split(MULTI_VALUE_SEPARATOR) if key in LIST_FIELDS else [value]
            _set_values(tags, field.vorbis, values)
            expected[key] = value
    return expected


def _set_values(tags: Any, names: Sequence[str], values: list[str] | None) -> None:
    """Pone un campo (todos sus nombres) a unos valores; None lo quita (todos sus nombres).

    El principal se escribe siempre (con la forma que tenga en el archivo, si está); los
    otros nombres, solo si el archivo ya los usa.
    """
    existing = _present(tags, names)
    if values is None:
        for key in existing:
            del tags[key]
        return
    primary = next((key for key in existing if key.upper() == names[0]), names[0])
    for key in [primary, *(key for key in existing if key.upper() != names[0])]:
        tags[key] = list(values)


def _set_pair(tags: Any, field: TagField, number: int | None, total: int | None) -> None:
    """Pone una pareja (la pista o el disco) con su total; sin número, la quita entera."""
    number_keys = _present(tags, field.vorbis)
    if number is None:
        for key in [*number_keys, *_present(tags, field.vorbis_total)]:
            del tags[key]
        return
    slash = any("/" in value for key in number_keys for value in tags[key])
    if slash:
        # «3/12» en el número: se mantiene esa forma; los otros nombres del total, al día
        _set_values(tags, field.vorbis, [f"{number}/{total}" if total else f"{number}"])
        total_values = None if total is None else [str(total)]
        for key in _present(tags, field.vorbis_total):
            if total_values is None:
                del tags[key]
            else:
                tags[key] = total_values
    else:
        _set_values(tags, field.vorbis, [str(number)])
        _set_values(tags, field.vorbis_total, None if total is None else [str(total)])


def _present(tags: Any, names: Sequence[str]) -> list[str]:
    """Los nombres de un campo que usa el archivo, escritos como en él (en el orden de
    'names'; sin distinguir mayúsculas)."""
    spelled: dict[str, str] = {}
    for key, _value in tags:
        spelled.setdefault(key.upper(), key)
    return [spelled[name] for name in names if name in spelled]


def _edited_names(wanted: Mapping[str, Any]) -> frozenset[str]:
    """Todos los nombres (en mayúsculas) de los campos editados."""
    names: set[str] = set()
    for key in wanted:
        field = tag_field(key)
        names.update(field.vorbis, field.vorbis_total)
    return frozenset(names)


def _untouched(tags: Any, names: frozenset[str]) -> list[tuple[str, str]]:
    """Los campos que no son de lo editado (clave, valor), ordenados: para comparar antes y
    después (mutagen puede cambiar su orden)."""
    return sorted((key, value) for key, value in tags if key.upper() not in names)


# =============================================================================
# El archivo
# =============================================================================


def _flac_blocks(audio: Any) -> list[tuple[int, bytes]] | None:
    """Los bloques de un FLAC que no se rehacen al escribir (todos salvo los comentarios y
    el relleno), con todo su contenido; None si no es un FLAC."""
    if not isinstance(audio, FLAC):
        return None
    return [
        (block.code, block.write())
        for block in audio.metadata_blocks
        if block.code not in _FLAC_REWRITTEN_BLOCKS
    ]


def _audio_digest(path: Path, kind: type) -> str:
    """La huella del audio, la misma antes y después de escribir (ver el paso 5)."""
    if kind is FLAC:
        return _flac_audio_digest(path)
    return _ogg_audio_digest(path, _OGG_HEADER_PACKETS[kind])


def _flac_audio_digest(path: Path) -> str:
    """La huella de las tramas de audio de un FLAC: todo lo que sigue a sus bloques."""
    digest = hashlib.blake2b(digest_size=16)
    with path.open("rb") as file:
        file.seek(_flac_audio_offset(file.read(_ID3V2_HEADER_SIZE), file))
        while chunk := file.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _flac_audio_offset(start: bytes, file: Any) -> int:
    """Dónde empiezan las tramas de un FLAC (tras un ID3v2 al principio, si lo hay, la marca
    «fLaC» y sus bloques).

    Raises:
        ValueError: Si no es un FLAC.
    """
    offset = 0
    if start.startswith(b"ID3") and len(start) == _ID3V2_HEADER_SIZE:
        size = 0
        for byte in start[6:10]:  # cuatro bytes de 7 bits («synchsafe»)
            size = (size << 7) | (byte & 0x7F)
        offset = _ID3V2_HEADER_SIZE + size
    file.seek(offset)
    if file.read(len(_FLAC_MARK)) != _FLAC_MARK:
        raise ValueError("no es un FLAC")
    offset += len(_FLAC_MARK)
    while True:
        header = file.read(4)
        if len(header) < 4:
            raise ValueError("FLAC cortado")
        offset += 4 + int.from_bytes(header[1:4], "big")
        file.seek(offset)
        if header[0] & _FLAC_LAST_BLOCK:
            return offset


def _ogg_audio_digest(path: Path, header_packets: int) -> str:
    """La huella del audio de un Ogg: sus paquetes (menos el de los comentarios) y la
    posición de cada página de audio, flujo a flujo (ver el paso 5)."""
    pages: list[OggPage] = []
    with path.open("rb") as file:
        while True:
            try:
                pages.append(OggPage(file))
            except EOFError:
                break
    digest = hashlib.blake2b(digest_size=16)
    main_serial = pages[0].serial if pages else None
    for serial in dict.fromkeys(page.serial for page in pages):
        stream = [page for page in pages if page.serial == serial]
        packets = OggPage.to_packets(stream)
        if serial == main_serial:
            del packets[_OGG_COMMENT_PACKET]  # el único que cambia
            # Las páginas de las cabeceras se rehacen; las de audio, no
            stream = _audio_pages(stream, header_packets)
        digest.update(repr(serial).encode())
        for packet in packets:
            digest.update(len(packet).to_bytes(8, "big") + packet)
        digest.update(repr([(page.position, page.last) for page in stream]).encode())
    return digest.hexdigest()


def _audio_pages(stream: list[OggPage], header_packets: int) -> list[OggPage]:
    """Las páginas de audio de un flujo: las que siguen a la que termina su última cabecera
    (el audio empieza siempre en una página nueva). Se cuentan los paquetes que termina cada
    página: no basta su posición, porque las de un paquete de comentarios grande (con la
    carátula) pueden llevar -1."""
    completed = 0
    for index, page in enumerate(stream):
        completed += len(page.packets) - (0 if page.complete else 1)
        if completed >= header_packets:
            return stream[index + 1 :]
    return []
