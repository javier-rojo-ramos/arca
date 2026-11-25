"""Lectura de una canción con mutagen: sus etiquetas, sus datos técnicos y sus imágenes.

Este módulo NO depende de Qt ni de la base de datos: recibe una ruta y devuelve un
'AudioInfo'. Lo usan el extractor de audio (docs/MOD_MUSICA.md, MUS 1.3), que decide en
qué columna del catálogo va cada dato, y la herramienta de diagnóstico
('core/metadata/audio/inspect_cli.py'). Solo lee: nunca cambia el archivo.

    info = read_audio(Path("cancion.mp3"))
    info.tags.title, info.tags.track_number, info.tags.genre   # 'AudioTags'
    info.technical.duration, info.technical.codec               # 'AudioTechnical'
    info.tag_type        # 'ID3v2.3 + ID3v1'
    info.pictures        # todas las imágenes ('AudioPicture', sin sus bytes)
    info.cover           # la portada o, si no hay, la primera imagen

Formatos:
    - Con etiquetas (la tabla de 'tag_map.py'): ID3 (MP3, WAV, AIFF), Vorbis (FLAC, Ogg
      Vorbis, Opus) y MP4 (M4A).
    - Otros que mutagen abre (WMA, AAC sin contenedor, WavPack...): solo los datos técnicos.
    - Lo que mutagen no abre (MKA, un archivo que no es de audio): 'UnsupportedAudioError'.
      Un archivo dañado o que no se puede leer: 'AudioReadError' (la clase de la anterior).

Cómo se traduce (los detalles de cada campo, en 'tag_map.py'):
    - Un texto vacío o solo con espacios es «sin valor» (None).
    - Varios valores: unidos con 'MULTI_VALUE_SEPARATOR' («Rock; Pop»), sin repetir.
    - Pista y disco: «3/12» -> 3 y 12; «03» -> 3. Lo que no es un número positivo, None.
    - La fecha, tal cual («2001», «2001-05-04»): el extractor decide qué guarda.
    - Pasar las etiquetas a campos ('tags_from_id3', 'tags_from_vorbis', 'tags_from_mp4')
      va separado de abrir el archivo: se prueba sin archivos y lo usará el escritor.

Las imágenes: su tipo (la clave de 'picture_types.py'; en MP4, que no tiene tipos, la
portada, como Mp3tag: su átomo 'covr' es la carátula), su formato, su tamaño en píxeles
(de la cabecera de la imagen, con Pillow: ID3 no lo guarda) y su peso. Sus bytes no se
guardan en 'AudioInfo' (la miniatura, en MUS 3, los pedirá).

Los datos técnicos ('AudioTechnical') salen de mutagen y van APARTE: si un día hace falta
otra fuente (MediaInfo, docs/MOD_MUSICA.md §4), se rellena esa parte sin tocar las demás.
El códec es una clave corta ('mp3', 'aac', 'alac', 'flac', 'vorbis', 'opus', 'pcm', 'wma'...);
la profundidad de bits, solo en los formatos sin pérdida (en AAC o MP3 no significa nada).
La tasa de bits es la MEDIA, como la de Mp3tag (comparado con las 75 canciones del autor):
la que da mutagen, salvo en Ogg Vorbis, donde mutagen da la nominal de la cabecera y se
calcula con el tamaño del archivo sin las etiquetas.

1.3.0 La huella de cada imagen ('AudioPicture.digest', BLAKE2) y la familia de la etiqueta
      ('AudioInfo.tag_family'), para el extractor (MUS 1.3).
1.2.0 Las imágenes de un MP4 (M4A), como portadas (antes, sin tipo), como Mp3tag.
1.1.0 Ogg Vorbis: la tasa de bits media, no la nominal (mutagen daba 160 kbps en todas;
      Mp3tag, de 127 a 147, como ahora, con 1 kbps de diferencia como mucho).
1.0.0 Primera versión (25/11/2026; docs/MOD_MUSICA.md, paso MUS 1.1).

Prueba rápida (desde la raíz del proyecto; crea un MP3 y un FLAC mínimos en una carpeta
temporal):
    python -m core.audio.tag_reader
"""

__version__ = "1.3.0"
__all__ = [
    "ID3_FAMILY",
    "MP4_FAMILY",
    "VORBIS_FAMILY",
    "AudioInfo",
    "AudioPicture",
    "AudioReadError",
    "AudioTags",
    "AudioTechnical",
    "UnsupportedAudioError",
    "parse_pair",
    "picture_digest",
    "pictures_from_flac",
    "pictures_from_id3",
    "pictures_from_mp4",
    "pictures_from_vorbis",
    "read_audio",
    "tags_from_id3",
    "tags_from_mp4",
    "tags_from_vorbis",
]

# Librerías estándar
import base64
import binascii
import hashlib
import io
import re
import struct
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Librerías de terceros
import mutagen
from mutagen._constants import GENRES
from mutagen._vorbis import VComment
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3
from mutagen.mp3 import MP3, BitrateMode
from mutagen.mp4 import MP4Cover, MP4Tags
from PIL import Image, UnidentifiedImageError

# Módulos del proyecto
from core.audio.picture_types import FRONT_COVER, picture_type_key
from core.audio.tag_map import (
    COMMENT,
    DATE,
    GENRE,
    MP4_GENRE_NUMBER,
    MULTI_VALUE_SEPARATOR,
    PAIR,
    TAG_FIELDS,
    TagField,
)

# Familias de etiquetas ('AudioInfo.tag_family'; las de 'tag_map.py')
ID3_FAMILY = "id3"
VORBIS_FAMILY = "vorbis"
MP4_FAMILY = "mp4"
# Bytes de la huella de una imagen ('picture_digest')
_DIGEST_BYTES = 16

# Códec según la clase de mutagen que abre el archivo (MP4 y MP3 se afinan aparte)
_CODEC_BY_CLASS: dict[str, str] = {
    "MP3": "mp3",
    "FLAC": "flac",
    "OggFLAC": "flac",
    "OggVorbis": "vorbis",
    "OggOpus": "opus",
    "OggSpeex": "speex",
    "WAVE": "pcm",
    "AIFF": "pcm",
    "AAC": "aac",
    "AC3": "ac3",
    "ASF": "wma",
    "WavPack": "wavpack",
    "MonkeysAudio": "ape",
    "TrueAudio": "tta",
    "OptimFROG": "ofr",
    "Musepack": "mpc",
    "DSF": "dsd",
    "DSDIFF": "dsd",
}
# Códecs sin pérdida (los únicos en los que la profundidad de bits significa algo)
_LOSSLESS: frozenset[str] = frozenset({"flac", "alac", "pcm", "wavpack", "ape", "tta", "ofr", "dsd"})
# Opus siempre se descodifica a 48 kHz (mutagen no da la frecuencia)
_OPUS_SAMPLE_RATE = 48000
# Modo de la tasa de bits de un MP3 (mutagen) -> clave
_BITRATE_MODES: dict[Any, str] = {
    BitrateMode.CBR: "cbr",
    BitrateMode.VBR: "vbr",
    BitrateMode.ABR: "abr",
}
# Formato de las imágenes de MP4 (mutagen) -> tipo MIME
_MP4_IMAGE_MIMES: dict[int, str] = {
    MP4Cover.FORMAT_JPEG: "image/jpeg",
    MP4Cover.FORMAT_PNG: "image/png",
}
# Formato de una imagen según Pillow -> tipo MIME (cuando el archivo no lo dice)
_PILLOW_MIMES: dict[str, str] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "WEBP": "image/webp",
    "TIFF": "image/tiff",
}
# Descripciones de los comentarios de iTunes en ID3 (datos internos, no un comentario)
_ITUNES_COMMENT_PREFIX = "itun"
# Clave de Vorbis con las imágenes (bloques PICTURE de FLAC, en base64): Ogg y Opus
_VORBIS_PICTURE_KEY = "METADATA_BLOCK_PICTURE"
# Las etiquetas que van al final de un MP3: ID3v1 (128 bytes, empiezan por «TAG») y APEv2
# (su pie, de 32 bytes, empieza por «APETAGEX»; antes del ID3v1 si lo hay)
_ID3V1_SIZE = 128
_APE_FOOTER = b"APETAGEX"
_TAIL_SIZE = _ID3V1_SIZE + 32

# Errores que puede dar mutagen (o lo que hay debajo) con un archivo dañado
_READ_ERRORS = (
    mutagen.MutagenError, OSError, EOFError, ValueError, IndexError, KeyError, TypeError,
    struct.error,
)  # fmt: skip


class AudioReadError(Exception):
    """No se ha podido leer el archivo (dañado, sin permiso, desaparecido...)."""


class UnsupportedAudioError(AudioReadError):
    """mutagen no reconoce el formato del archivo (MKA, o no es de audio)."""


@dataclass(frozen=True, slots=True)
class AudioTags:
    """Los campos de la canción (ver 'tag_map.py'). None = sin valor."""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    date: str | None = None
    track_number: int | None = None
    track_total: int | None = None
    disc_number: int | None = None
    disc_total: int | None = None
    genre: str | None = None
    album_artist: str | None = None
    composer: str | None = None
    comment: str | None = None

    def is_empty(self) -> bool:
        """True si no tiene ningún campo."""
        return all(getattr(self, name) is None for name in self.__slots__)


@dataclass(frozen=True, slots=True)
class AudioTechnical:
    """Los datos técnicos (de mutagen; ver el docstring del archivo).

    Attributes:
        codec: Clave corta del códec ('mp3', 'aac', 'flac'...); None si no se sabe.
        codec_detail: La descripción que da mutagen, si la da («AAC LC»).
        duration: Segundos.
        bitrate: Bits por segundo (la media, en VBR).
        bitrate_mode: 'cbr', 'vbr' o 'abr' (solo MP3, y si se sabe).
        sample_rate: Hz.
        channels: Número de canales.
        bit_depth: Bits por muestra (solo en los formatos sin pérdida).
        lossless: Si el formato es sin pérdida.
    """

    codec: str | None = None
    codec_detail: str | None = None
    duration: float | None = None
    bitrate: int | None = None
    bitrate_mode: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bit_depth: int | None = None
    lossless: bool = False


@dataclass(frozen=True, slots=True)
class AudioPicture:
    """Una imagen de la canción (sin sus bytes).

    Attributes:
        type_key: Su tipo ('picture_types.py'); en MP4, siempre la portada. None si el
            archivo trae un número que no es ningún tipo.
        mime: Tipo MIME («image/jpeg»); None si no se sabe.
        width, height: Tamaño en píxeles; None si no se ha podido leer.
        size_bytes: Peso de la imagen.
        description: La descripción que trae (casi siempre vacía).
        digest: Su huella ('picture_digest'): dos imágenes con la misma son la misma.
    """

    type_key: str | None
    mime: str | None
    width: int | None
    height: int | None
    size_bytes: int
    description: str = ""
    digest: str | None = None


@dataclass(frozen=True, slots=True)
class AudioInfo:
    """Lo que se lee de una canción.

    Attributes:
        tags: Sus campos.
        technical: Sus datos técnicos.
        tag_type: Tipo de etiqueta, como la columna «Tag» de Mp3tag («ID3v2.3 + ID3v1»,
            «Vorbis», «MP4»); vacío si no tiene.
        pictures: Sus imágenes, en el orden del archivo.
        tag_family: La familia de la etiqueta de la que salen los campos ('id3', 'vorbis'
            o 'mp4', las de 'tag_map.py'); None si no hay ninguna que se traduzca.
    """

    tags: AudioTags
    technical: AudioTechnical
    tag_type: str = ""
    pictures: tuple[AudioPicture, ...] = ()
    tag_family: str | None = None

    @property
    def cover(self) -> AudioPicture | None:
        """La carátula: la primera portada o, si no hay ninguna, la primera imagen."""
        for picture in self.pictures:
            if picture.type_key == FRONT_COVER:
                return picture
        return self.pictures[0] if self.pictures else None


# -----------------------------------------------------------------------------
# Leer un archivo
# -----------------------------------------------------------------------------


def read_audio(path: Path) -> AudioInfo:
    """Lee las etiquetas, los datos técnicos y las imágenes de una canción.

    Raises:
        UnsupportedAudioError: Si mutagen no reconoce el formato.
        AudioReadError: Si el archivo no se puede leer.
    """
    try:
        audio = mutagen.File(path)
    except _READ_ERRORS as error:
        raise AudioReadError(f"No se ha podido leer «{path.name}»: {error}") from error
    if audio is None:
        raise UnsupportedAudioError(f"Formato de audio no reconocido: «{path.name}»")

    tags = audio.tags
    family: str | None = None
    if isinstance(tags, ID3):  # MP3, WAV, AIFF
        audio_tags, pictures, family = tags_from_id3(tags), pictures_from_id3(tags), ID3_FAMILY
    elif isinstance(audio, FLAC):  # con o sin bloque de comentarios
        audio_tags = tags_from_vorbis(tags if tags is not None else {})
        pictures = pictures_from_flac(audio.pictures)
        family = VORBIS_FAMILY if tags is not None else None
    elif isinstance(tags, VComment):  # Ogg Vorbis, Opus
        audio_tags, pictures = tags_from_vorbis(tags), pictures_from_vorbis(tags)
        family = VORBIS_FAMILY
    elif isinstance(tags, MP4Tags):  # M4A
        audio_tags, pictures = tags_from_mp4(tags), pictures_from_mp4(tags.get("covr", ()))
        family = MP4_FAMILY
    else:  # sin etiquetas, o de un formato que no se traduce (WMA...)
        audio_tags, pictures = AudioTags(), ()
    return AudioInfo(
        tags=audio_tags,
        technical=_technical(audio, path),
        tag_type=_tag_type(audio, path),
        pictures=pictures,
        tag_family=family,
    )


# -----------------------------------------------------------------------------
# Etiquetas -> campos
# -----------------------------------------------------------------------------


def tags_from_id3(id3: ID3) -> AudioTags:
    """Los campos de una etiqueta ID3 (ya leída por mutagen)."""
    values: dict[str, Any] = {}
    for field in TAG_FIELDS:
        if field.kind == COMMENT:
            texts = [
                text
                for frame in id3.getall(field.id3)
                if not frame.desc  # el comentario sin descripción (el de Mp3tag)
                for text in frame.text
            ]
            values[field.key] = _join(texts)
        elif field.kind == GENRE:
            # 'genres' resuelve los números de ID3v1: «(17)» o «17» es «Rock»
            values[field.key] = _join(g for frame in id3.getall(field.id3) for g in frame.genres)
        else:
            texts = [text for frame in id3.getall(field.id3) for text in frame.text]
            _store(values, field, texts)
    return AudioTags(**values)


def tags_from_vorbis(comments: Mapping[str, Sequence[str]] | Any) -> AudioTags:
    """Los campos de unos comentarios de Vorbis (FLAC, Ogg, Opus): un diccionario de
    clave -> lista de textos, con las claves en mayúsculas o minúsculas."""
    upper: dict[str, list[str]] = {}
    for key, texts in comments.items():
        upper.setdefault(str(key).upper(), []).extend(
            [texts] if isinstance(texts, str) else texts
        )

    def first(keys: Iterable[str]) -> list[str]:
        """Los valores de la primera clave que tenga alguno."""
        for key in keys:
            texts = [text for text in upper.get(key, ()) if _clean(text)]
            if texts:
                return texts
        return []

    values: dict[str, Any] = {}
    for field in TAG_FIELDS:
        texts = first(field.vorbis)
        if field.kind == PAIR:
            number, total = parse_pair(texts[0] if texts else None)
            if total is None:
                total, _ = parse_pair(_first_text(first(field.vorbis_total)))
            _store_pair(values, field, number, total)
        else:
            _store(values, field, texts)
    return AudioTags(**values)


def tags_from_mp4(atoms: Mapping[str, Sequence[Any]] | Any) -> AudioTags:
    """Los campos de una etiqueta MP4 (M4A): un diccionario de átomo -> lista de valores."""
    values: dict[str, Any] = {}
    for field in TAG_FIELDS:
        items = list(atoms.get(field.mp4) or ())
        if field.kind == PAIR:
            # Un par de números (número, total); 0 es «sin valor»
            pair = items[0] if items else ()
            number = pair[0] if len(pair) > 0 else None
            total = pair[1] if len(pair) > 1 else None
            _store_pair(values, field, _positive(number), _positive(total))
        elif field.kind == GENRE and not items:
            # iTunes antiguos: el género como número de ID3v1 más uno
            numbers = [_positive(n) for n in atoms.get(MP4_GENRE_NUMBER) or ()]
            values[field.key] = _join(GENRES[n - 1] for n in numbers if n and n <= len(GENRES))
        else:
            _store(values, field, items)
    return AudioTags(**values)


def parse_pair(text: object) -> tuple[int | None, int | None]:
    """«3/12» -> (3, 12); «03» -> (3, None); lo que no es un número positivo, None."""
    if text is None:
        return None, None
    number, _slash, total = str(text).partition("/")
    return _positive(number), _positive(total)


# -----------------------------------------------------------------------------
# Imágenes
# -----------------------------------------------------------------------------


def pictures_from_id3(id3: ID3) -> tuple[AudioPicture, ...]:
    """Las imágenes de una etiqueta ID3 (marcos APIC)."""
    return tuple(
        _picture(frame.data, picture_type_key(frame.type), _id3_mime(frame.mime), frame.desc)
        for frame in id3.getall("APIC")
    )


def pictures_from_flac(pictures: Iterable[Picture]) -> tuple[AudioPicture, ...]:
    """Las imágenes de un FLAC (bloques PICTURE)."""
    return tuple(
        _picture(p.data, picture_type_key(p.type), p.mime or None, p.desc, p.width, p.height)
        for p in pictures
    )


def pictures_from_vorbis(comments: Mapping[str, Sequence[str]] | Any) -> tuple[AudioPicture, ...]:
    """Las imágenes de unos comentarios de Vorbis (Ogg, Opus): bloques PICTURE de FLAC en
    base64. Las que no se pueden descifrar se saltan."""
    blocks = [
        text
        for key, texts in comments.items()
        if str(key).upper() == _VORBIS_PICTURE_KEY
        for text in ([texts] if isinstance(texts, str) else texts)
    ]
    pictures = []
    for block in blocks:
        try:
            picture = Picture(base64.b64decode(block))
        except (binascii.Error, mutagen.MutagenError, struct.error, ValueError):
            continue
        pictures.extend(pictures_from_flac([picture]))
    return tuple(pictures)


def pictures_from_mp4(covers: Iterable[bytes]) -> tuple[AudioPicture, ...]:
    """Las imágenes de una etiqueta MP4 (átomo 'covr'). MP4 no guarda el tipo: se leen
    como portadas, como hace Mp3tag (decidido por el autor el 25/11/2026)."""
    return tuple(
        _picture(
            bytes(cover), FRONT_COVER, _MP4_IMAGE_MIMES.get(getattr(cover, "imageformat", None))
        )
        for cover in covers
    )


def _picture(
    data: bytes,
    type_key: str | None,
    mime: str | None,
    description: str = "",
    width: int = 0,
    height: int = 0,
) -> AudioPicture:
    """Una imagen, con su tamaño leído de su cabecera (si no, el que diga el archivo)."""
    try:
        with Image.open(io.BytesIO(data)) as image:  # solo lee la cabecera
            width, height = image.size
            mime = mime or _PILLOW_MIMES.get(image.format or "")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        pass
    return AudioPicture(
        type_key=type_key,
        mime=mime,
        width=width or None,
        height=height or None,
        size_bytes=len(data),
        description=_clean(description) or "",
        digest=picture_digest(data),
    )


def picture_digest(data: bytes) -> str:
    """La huella de una imagen: BLAKE2 de sus bytes, 32 caracteres hexadecimales. Rápida
    y suficiente para saber si dos carátulas son la misma (no es una firma de seguridad)."""
    return hashlib.blake2b(data, digest_size=_DIGEST_BYTES).hexdigest()


def _id3_mime(mime: str) -> str | None:
    """El tipo MIME de un APIC; en ID3v2.2 venía como «JPG» o «PNG»."""
    mime = (mime or "").strip().lower()
    if not mime:
        return None
    if "/" not in mime:
        return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(mime)
    return mime


# -----------------------------------------------------------------------------
# Datos técnicos y tipo de etiqueta
# -----------------------------------------------------------------------------


def _technical(audio: Any, path: Path) -> AudioTechnical:
    """Los datos técnicos del archivo abierto por mutagen."""
    info = audio.info
    class_name = type(audio).__name__
    length = getattr(info, "length", None)
    bitrate = _positive(getattr(info, "bitrate", None))
    if class_name == "OggVorbis" and length:
        # mutagen da la tasa NOMINAL de la cabecera de Vorbis (160 kbps en todas las de
        # prueba), no la media: se calcula, como Mp3tag, con el tamaño del archivo sin
        # las etiquetas (que llevan la carátula, en base64)
        try:
            file_size = path.stat().st_size
        except OSError:
            file_size = 0
        bitrate = _average_bitrate(file_size, _comment_bytes(audio.tags or {}), length) or bitrate
    codec = _CODEC_BY_CLASS.get(class_name)
    detail = None
    if class_name == "MP4":
        codec = _mp4_codec(getattr(info, "codec", "") or "")
        detail = getattr(info, "codec_description", None)
    elif class_name == "MP3" and getattr(info, "layer", 3) != 3:
        codec = f"mp{info.layer}"  # MPEG Layer 1 o 2
    elif class_name == "ASF":
        detail = getattr(info, "codec_name", None)
    lossless = codec in _LOSSLESS
    sample_rate = _positive(getattr(info, "sample_rate", None))
    if codec == "opus" and sample_rate is None:
        sample_rate = _OPUS_SAMPLE_RATE
    return AudioTechnical(
        codec=codec,
        codec_detail=_clean(detail),
        duration=float(length) if length else None,
        bitrate=bitrate,
        bitrate_mode=_BITRATE_MODES.get(getattr(info, "bitrate_mode", None)),
        sample_rate=sample_rate,
        channels=_positive(getattr(info, "channels", None)),
        bit_depth=_positive(getattr(info, "bits_per_sample", None)) if lossless else None,
        lossless=lossless,
    )


def _comment_bytes(comments: Mapping[str, Sequence[str]] | Any) -> int:
    """Lo que ocupan unos comentarios de Vorbis en el archivo (clave, «=» y valor)."""
    return sum(
        len(str(key).encode("utf-8")) + 1 + len(str(value).encode("utf-8"))
        for key, values in comments.items()
        for value in ([values] if isinstance(values, str) else values)
    )


def _average_bitrate(file_size: int, tag_bytes: int, length: float) -> int | None:
    """La tasa media (bits por segundo) del audio: el tamaño sin las etiquetas entre la
    duración; None si no se puede calcular."""
    audio_bytes = file_size - tag_bytes
    if audio_bytes <= 0 or length <= 0:
        return None
    return round(audio_bytes * 8 / length)


def _mp4_codec(codec: str) -> str | None:
    """Clave del códec de un MP4: «mp4a.40.2» es AAC; «alac», ALAC; «ac-3», AC-3."""
    codec = codec.lower()
    if codec.startswith("mp4a"):
        return "aac"
    return {"alac": "alac", "ac-3": "ac3", "ec-3": "eac3"}.get(codec, codec or None)


def _tag_type(audio: Any, path: Path) -> str:
    """El tipo de etiqueta, como la columna «Tag» de Mp3tag; vacío si no tiene."""
    tags = audio.tags
    parts: list[str] = []
    if isinstance(tags, ID3):
        major, minor = tags.version[:2]
        # Solo ID3v1: mutagen lo carga como un ID3 de versión 1.1
        parts.append("ID3v1" if major == 1 else f"ID3v2.{minor}")
    elif isinstance(tags, VComment) or (isinstance(audio, FLAC) and tags is not None):
        parts.append("Vorbis")
    elif isinstance(tags, MP4Tags):
        parts.append("MP4")
    elif tags is not None:
        parts.append(type(tags).__name__.removesuffix("Tags"))  # ASF, APEv2...
    if isinstance(audio, MP3):
        # Las que van al final del archivo: mutagen une el ID3v1 al ID3v2 sin decirlo
        tail = _file_tail(path)
        if tail[-_ID3V1_SIZE:].startswith(b"TAG") and parts and parts[0] != "ID3v1":
            parts.append("ID3v1")
        if _APE_FOOTER in tail:
            parts.append("APEv2")
    return " + ".join(parts)


def _file_tail(path: Path) -> bytes:
    """Los últimos bytes del archivo (vacío si no se pueden leer)."""
    try:
        with path.open("rb") as file:
            file.seek(0, io.SEEK_END)
            file.seek(max(0, file.tell() - _TAIL_SIZE))
            return file.read()
    except OSError:
        return b""


# -----------------------------------------------------------------------------
# Ayudas
# -----------------------------------------------------------------------------


def _clean(text: object) -> str | None:
    """Un texto sin espacios a los lados ni caracteres nulos; None si queda vacío."""
    if text is None:
        return None
    cleaned = str(text).replace("\x00", "").strip()
    return cleaned or None


def _first_text(texts: Sequence[object]) -> str | None:
    """El primero de una lista de textos (None si está vacía)."""
    return _clean(texts[0]) if texts else None


def _join(texts: Iterable[object]) -> str | None:
    """Varios valores en un texto, sin repetir y sin los vacíos (None si no queda nada)."""
    parts: list[str] = []
    for text in texts:
        cleaned = _clean(text)
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    return MULTI_VALUE_SEPARATOR.join(parts) or None


def _positive(value: object) -> int | None:
    """Un número entero positivo («03» -> 3); None si no lo es (también el 0)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value).strip()
    if not re.fullmatch(r"\d+", text):
        return None
    number = int(text)
    return number if number > 0 else None


def _store(values: dict[str, Any], field: TagField, texts: Sequence[object]) -> None:
    """Guarda en 'values' un campo de texto, de fecha o una pareja escrita como texto."""
    if field.kind == PAIR:
        number, total = parse_pair(_first_text(texts))
        _store_pair(values, field, number, total)
    elif field.kind == DATE:
        values[field.key] = _first_text(texts)
    else:
        values[field.key] = _join(texts)


def _store_pair(
    values: dict[str, Any], field: TagField, number: int | None, total: int | None
) -> None:
    """Guarda una pareja: 'track' -> 'track_number' y 'track_total'."""
    values[f"{field.key}_number"] = number
    values[f"{field.key}_total"] = total


if __name__ == "__main__":
    # Autoprueba (sin Qt). Crea un MP3 y un FLAC mínimos en una carpeta temporal y lee
    # también etiquetas hechas en memoria. Desde la raíz del proyecto:
    #     python -m core.audio.tag_reader
    import tempfile

    from mutagen.id3 import APIC, COMM, TALB, TCOM, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK

    def image_bytes(size: tuple[int, int], image_format: str) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", size, "red").save(buffer, image_format)
        return buffer.getvalue()

    JPEG = image_bytes((30, 20), "JPEG")
    PNG = image_bytes((12, 12), "PNG")

    # --- La tasa media de Ogg Vorbis: el archivo sin las etiquetas, entre la duración
    assert _comment_bytes({"title": ["Á"], "GENRE": "BSO"}) == (5 + 1 + 2) + (5 + 1 + 3)
    assert _average_bitrate(3_000_000, 40_000, 160.0) == 148_000
    assert _average_bitrate(100, 200, 10.0) is None and _average_bitrate(100, 0, 0.0) is None

    # --- Parejas y números
    assert parse_pair("3/12") == (3, 12) and parse_pair("03") == (3, None)
    assert parse_pair(" 7 / 10 ") == (7, 10) and parse_pair("/5") == (None, 5)
    assert parse_pair("A1") == (None, None) and parse_pair(None) == (None, None)
    assert parse_pair("0/0") == (None, None) and parse_pair("-2") == (None, None)

    # --- ID3 en memoria
    id3 = ID3()
    id3.add(TIT2(encoding=3, text=["  Vino Tinto  "]))
    id3.add(TPE1(encoding=3, text=["Estopa", "Rosendo", "Estopa"]))  # se quita el repetido
    id3.add(TALB(encoding=3, text=["Destrangis"]))
    id3.add(TDRC(encoding=3, text=["2001-05-04"]))
    id3.add(TRCK(encoding=3, text=["03/12"]))
    id3.add(TPOS(encoding=3, text=["1"]))
    id3.add(TCON(encoding=3, text=["(17)"]))  # el número de ID3v1 de Rock
    id3.add(TPE2(encoding=3, text=[""]))  # vacío: sin valor
    id3.add(TCOM(encoding=3, text=["J. Muñoz"]))
    id3.add(COMM(encoding=3, lang="eng", desc="iTunNORM", text=[" 0000 0000"]))
    id3.add(COMM(encoding=3, lang="spa", desc="", text=["Primer disco"]))
    tags = tags_from_id3(id3)
    assert tags == AudioTags(
        title="Vino Tinto", artist="Estopa; Rosendo", album="Destrangis", date="2001-05-04",
        track_number=3, track_total=12, disc_number=1, disc_total=None, genre="Rock",
        album_artist=None, composer="J. Muñoz", comment="Primer disco",
    ), tags  # fmt: skip
    assert tags_from_id3(ID3()).is_empty()
    two_genres = ID3()
    two_genres.add(TCON(encoding=3, text=["Rock", "Pop"]))
    assert tags_from_id3(two_genres).genre == "Rock; Pop"

    # --- Vorbis en memoria: claves en minúsculas o mayúsculas, alias y totales aparte
    tags = tags_from_vorbis({
        "title": ["Misirlou"], "Artist": ["Dick Dale"], "DATE": ["1994"],
        "tracknumber": ["01"], "TOTALTRACKS": ["15"], "DISCNUMBER": ["2/3"],
        "DISCTOTAL": ["9"],  # el total de «2/3» manda
        "genre": ["BSO", "Surf"], "ALBUM ARTIST": ["Varios"], "description": ["Nota"],
        "organization": ["Warner"],  # no es de la tabla: se ignora
    })  # fmt: skip
    assert (tags.title, tags.artist, tags.date) == ("Misirlou", "Dick Dale", "1994")
    assert (tags.track_number, tags.track_total) == (1, 15), tags
    assert (tags.disc_number, tags.disc_total) == (2, 3), tags
    assert (tags.genre, tags.album_artist, tags.comment) == ("BSO; Surf", "Varios", "Nota")
    # COMMENT antes que DESCRIPTION; YEAR solo si no hay DATE
    assert tags_from_vorbis({"COMMENT": ["A"], "DESCRIPTION": ["B"]}).comment == "A"
    assert tags_from_vorbis({"YEAR": ["1999"]}).date == "1999"
    assert tags_from_vorbis({"DATE": [" "], "YEAR": ["1999"]}).date == "1999"
    assert tags_from_vorbis({}).is_empty()

    # --- MP4 en memoria: parejas de números, el género como número, sin total (0)
    tags = tags_from_mp4({
        "©nam": ["Vino Tinto"], "trkn": [(1, 12)], "disk": [(1, 0)], "gnre": [18],
        "©day": ["2001-01-01T08:00:00Z"],
    })  # fmt: skip
    assert (tags.title, tags.track_number, tags.track_total) == ("Vino Tinto", 1, 12)
    assert (tags.disc_number, tags.disc_total, tags.genre) == (1, None, "Rock")
    assert tags.date == "2001-01-01T08:00:00Z"
    assert tags_from_mp4({"©gen": ["Pop Folk"], "gnre": [18]}).genre == "Pop Folk"
    assert tags_from_mp4({"trkn": [(0, 0)]}).track_number is None

    # --- Imágenes en memoria
    covers = pictures_from_mp4([MP4Cover(PNG, MP4Cover.FORMAT_PNG)])
    assert covers == (
        AudioPicture(FRONT_COVER, "image/png", 12, 12, len(PNG), digest=picture_digest(PNG)),
    ), covers
    block = Picture()
    block.type, block.mime, block.data = 4, "image/jpeg", JPEG
    encoded = base64.b64encode(block.write()).decode("ascii")
    pictures = pictures_from_vorbis({"metadata_block_picture": [encoded, "no-es-base64!"]})
    back = AudioPicture("cover_back", "image/jpeg", 30, 20, len(JPEG), digest=picture_digest(JPEG))
    assert pictures == (back,), pictures
    assert len(picture_digest(JPEG)) == 32 and picture_digest(JPEG) != picture_digest(PNG)
    # Una imagen que Pillow no entiende: sin tamaño (o el que diga el archivo)
    assert _picture(b"nada", None, None).width is None
    assert _picture(b"nada", None, None, width=600, height=600).width == 600

    with tempfile.TemporaryDirectory(prefix="arca_audio_") as folder:
        root = Path(folder)

        # --- Un MP3 mínimo: 40 tramas de silencio (MPEG-1 Layer III, 128 kbps, 44,1 kHz,
        # estéreo; 417 bytes cada una) con ID3v2.3 (y ID3v1) y dos imágenes
        frame = b"\xff\xfb\x90\x00" + bytes(413)
        mp3 = root / "cancion.mp3"
        mp3.write_bytes(frame * 40)
        id3 = ID3()
        id3.add(TIT2(encoding=1, text=["Stretch Your Eyes"]))
        id3.add(TPE1(encoding=1, text=["Agnes Obel"]))
        id3.add(TRCK(encoding=1, text=["01"]))
        id3.add(TCON(encoding=1, text=["Folk"]))
        id3.add(APIC(encoding=1, mime="image/png", type=4, desc="", data=PNG))
        id3.add(APIC(encoding=1, mime="image/jpeg", type=3, desc="Portada", data=JPEG))
        id3.save(mp3, v2_version=3, v1=2)  # v1=2: también ID3v1
        info = read_audio(mp3)
        assert info.tag_type == "ID3v2.3 + ID3v1", info.tag_type
        assert (info.tags.title, info.tags.artist, info.tags.track_number) == (
            "Stretch Your Eyes", "Agnes Obel", 1)  # fmt: skip
        assert info.tags.genre == "Folk"
        technical = info.technical
        assert (technical.codec, technical.sample_rate, technical.channels) == ("mp3", 44100, 2)
        assert technical.bitrate == 128000 and not technical.lossless and technical.bit_depth is None
        assert technical.duration and 0.9 < technical.duration < 1.2, technical.duration
        assert len(info.pictures) == 2 and info.pictures[0].type_key == "cover_back"
        cover = info.cover  # la portada, aunque no sea la primera
        assert cover == AudioPicture(
            FRONT_COVER, "image/jpeg", 30, 20, len(JPEG), "Portada", picture_digest(JPEG)
        )
        assert info.tag_family == ID3_FAMILY

        # El mismo MP3 en ID3v2.4, sin ID3v1; y otro solo con ID3v1
        id3.save(mp3, v2_version=4, v1=0)
        assert read_audio(mp3).tag_type == "ID3v2.4"
        only_v1 = root / "solo_v1.mp3"
        only_v1.write_bytes(frame * 10)
        id3 = ID3()
        id3.add(TIT2(encoding=0, text=["Antigua"]))
        id3.save(only_v1, v1=2)
        only_v1.write_bytes(frame * 10 + only_v1.read_bytes()[-_ID3V1_SIZE:])  # sin el v2
        info = read_audio(only_v1)
        assert info.tag_type == "ID3v1" and info.tags.title == "Antigua", info

        # --- Un FLAC mínimo: la cabecera y su STREAMINFO (2 s, 44,1 kHz, estéreo, 16 bits),
        # sin audio, con comentarios y una imagen
        streaminfo = struct.pack(">HH", 4096, 4096) + bytes(6)
        streaminfo += ((44100 << 44) | (1 << 41) | (15 << 36) | 88200).to_bytes(8, "big")
        streaminfo += bytes(16)  # MD5
        flac_path = root / "cancion.flac"
        flac_path.write_bytes(b"fLaC" + bytes([0x80]) + len(streaminfo).to_bytes(3, "big") + streaminfo)
        flac = FLAC(flac_path)
        flac.add_tags()
        flac["TITLE"] = "Misirlou"
        flac["TRACKNUMBER"] = "2"
        flac["TRACKTOTAL"] = "15"
        flac["GENRE"] = ["BSO", "Surf"]
        picture = Picture()
        picture.type, picture.mime, picture.data = 3, "image/jpeg", JPEG
        flac.add_picture(picture)
        flac.save()
        info = read_audio(flac_path)
        assert info.tag_type == "Vorbis" and info.tags.title == "Misirlou"
        assert (info.tags.track_number, info.tags.track_total, info.tags.genre) == (2, 15, "BSO; Surf")
        technical = info.technical
        assert (technical.codec, technical.lossless, technical.bit_depth) == ("flac", True, 16)
        assert (technical.sample_rate, technical.channels, technical.duration) == (44100, 2, 2.0)
        assert info.cover == AudioPicture(
            FRONT_COVER, "image/jpeg", 30, 20, len(JPEG), digest=picture_digest(JPEG)
        )
        assert info.tag_family == VORBIS_FAMILY

        # --- Lo que no se puede leer
        unknown = root / "pista.mka"
        unknown.write_bytes(b"\x1a\x45\xdf\xa3" + bytes(60))  # cabecera de Matroska
        damaged = root / "rota.flac"
        damaged.write_bytes(b"fLaC\x00\x00")
        for bad, error_type in (
            (unknown, UnsupportedAudioError),
            (damaged, AudioReadError),
            (root / "no_existe.mp3", AudioReadError),
        ):
            try:
                read_audio(bad)
                raise AssertionError(f"debía fallar: {bad.name}")
            except error_type:
                pass

    print("Autoprueba finalizada correctamente.")
