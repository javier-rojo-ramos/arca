"""Escritura de las etiquetas de una canción en el propio archivo, sin tocar nada más.

Este módulo NO depende de Qt ni de la base de datos: recibe una ruta y lo editado, y deja el
archivo con lo editado o como estaba. Es el motor del escritor de audio de la cola de
escritura ('core/userdata/audio_writer.py', MUS 6.2). Hoy escribe MP3 (ID3v2 e ID3v1);
FLAC, M4A y Ogg, en MUS 6.3 y 6.4.

    result = write_tags(path, {"title": "Vino Tinto", "track": (3, 12)}, preferred)
    result.written         # False si ya tenía esos valores (el archivo no se toca)
    result.tags_before     # 'TagSet' de antes: ID3v1
    result.tags_after      # y el de después: ID3v2.3 + ID3v1

LO EDITADO ('changes'): las claves de 'tag_map.TAG_FIELDS' y None para vaciar. Los textos y
la fecha («2001», «2001-05» o «2001-05-04»), como texto; la pista y el disco, como la pareja
(número, total), con None en lo que falte (sin número, se borra la pareja entera). Lo que no
vale (una clave que no es de la tabla, una fecha mal escrita, un número que no es positivo)
es 'ValueError' ('TypeError' si no es un texto): es un error de quien llama, no del archivo.

CÓMO ESCRIBE (docs/MOD_MUSICA.md §5; reglas acordadas con el autor el 16 y el 27/11/2026):
    1. En qué etiquetas: 'tag_set.tags_for_edit' (en las que tiene; si le falta el ID3v2, la
       preferida, completa).
    2. Copia el archivo en un temporal de su carpeta ('.cancion.mp3.arca.tmp': el escáner no
       lo cataloga nunca, por el punto y por '.tmp').
    3. ID3v2, con mutagen SIN CONVERTIR la etiqueta ('translate=False', 'load_v1=False') y
       guardándola en su versión: solo cambian los marcos de lo editado y los demás quedan con
       el mismo contenido. mutagen reescribe la etiqueta entera (el orden de los marcos puede
       cambiar); guardar como dice su documentación borraría marcos (docs/TRAMPAS.md). Si la
       etiqueta trae marcos repetidos que mutagen no conservaría (dos letras con la misma
       descripción e idioma, dos valoraciones del mismo reproductor...), no se escribe; los
       de texto repetidos (también los comentarios) los junta en uno, con todos sus
       valores. Si el ID3v2 se crea (no tenía, o era un 2.2, que mutagen no escribe), se
       parte de lo que se lee del archivo (su ID3v1, o su 2.2 convertido), con el
       comentario del ID3v1 como comentario.
    4. ID3v1, lo quita y lo vuelve a poner la aplicación ('id3v1.py'): solo lo editado,
       adaptado a sus límites; uno nuevo (si la preferida lo incluye), con todo.
    5. Comprueba el temporal antes de usarlo: que tiene las etiquetas previstas; que lo
       editado se lee como se pidió (como lo lee el catálogo, 'tags_from_id3', adaptado a la
       versión) y lo demás, como antes (en un ID3v2 que ya estaba, marco a marco); el ID3v1;
       y el AUDIO: la huella de todo lo que hay entre el ID3v2 y el ID3v1 (con un APEv2, si
       lo hay), igual que la del original.
    6. Si el original no ha cambiado mientras tanto, el temporal lo sustituye: en Windows, con
       'ReplaceFileW', que conserva la fecha de creación, los atributos y los permisos del
       original; en macOS y Linux, con 'os.replace' (y los permisos del original). Si el
       archivo está en uso un momento (un antivirus, el indexador), se reintenta.
Si algo falla, el original queda como estaba, el temporal se borra y se lanza
'AudioWriteError'. La fecha de modificación del archivo cambia, como con las fotos.

Lo que se escribe va en la codificación de su versión: UTF-16 en v2.3 y UTF-8 en v2.4 (como
Mp3tag). Varios valores («Rock; Pop») en el artista, el artista del álbum, el compositor y el
género: en v2.4, valores separados; en v2.3, un texto tal cual (mutagen los uniría con «/», que
se confunde con «AC/DC»). El título, el álbum y el comentario, siempre un texto. La fecha: en
v2.4, TDRC; en v2.3, TYER y, si es completa, TDAT (el mes sin día no cabe en v2.3: queda el
año); si el archivo traía la de la otra versión, también se cambia, para que no digan cosas
distintas; la hora (TIME) se quita. El comentario es el COMM sin descripción (los de iTunes y
otros programas no se tocan), con el idioma del que hubiera o «eng».

Usa dos cosas internas de mutagen 1.48 (si cambian, falla la autoprueba): 'read_frames' y la
cabecera ya leída, para saber si se perdería algún marco repetido.

1.0.0 Primera versión (27/11/2026; docs/MOD_MUSICA.md, paso MUS 6.1c).

Prueba rápida (desde la raíz del proyecto; crea MP3 mínimos en una carpeta temporal):
    python -m core.audio.tag_writer
"""

__version__ = "1.0.0"
__all__ = ["AudioWriteError", "TagWriteResult", "UnsupportedAudioWriteError", "write_tags"]

# Librerías estándar
import copy
import hashlib
import os
import re
import shutil
import struct
import sys
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger
from mutagen import MutagenError
from mutagen.id3 import COMM, ID3, TDAT, TDRC, TYER, Encoding, Frames, ID3NoHeaderError, TextFrame
from mutagen.id3._tags import read_frames
from mutagen.mp3 import MP3

# Módulos del proyecto
from core.audio.id3v1 import ID3V1_SIZE, Id3v1Tag, apply_changes, build_id3v1, parse_id3v1
from core.audio.tag_map import COMMENT, DATE, MULTI_VALUE_SEPARATOR, PAIR, TAG_FIELDS, tag_field
from core.audio.tag_reader import (
    AudioReadError,
    AudioTags,
    UnsupportedAudioError,
    open_audio,
    tag_set_of,
    tags_from_id3,
)
from core.audio.tag_set import DEFAULT_MP3_TAGS, TagSet, tags_for_edit

# Los campos que pueden tener varios valores (en v2.4, separados; ver el docstring)
_LIST_FIELDS: frozenset[str] = frozenset({"artist", "album_artist", "composer", "genre"})
# Los marcos de la fecha: el de v2.4 y los de v2.3 (año, día y mes, hora)
_DATE_FRAMES: tuple[str, ...] = ("TDRC", "TYER", "TDAT", "TIME")
# Una fecha: el año y, si los trae, el mes y el día
_DATE_PATTERN = re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?")
# Un año menor no es un año («0000» es lo que escriben algunos programas sin dato)
_FIRST_YEAR = 1000
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
# El temporal: en la misma carpeta, oculto por el punto y con '.tmp' (el escáner lo salta)
_TEMP_SUFFIX = ".arca.tmp"
# Bloques de lectura para la huella del audio
_CHUNK_SIZE = 1 << 20
# Sustituir el original: intentos si está en uso un momento, y la espera entre ellos
_REPLACE_ATTEMPTS = 5
_REPLACE_WAIT = 0.1  # segundos
_IS_WINDOWS = sys.platform == "win32"
# ReplaceFileW: sin copia de seguridad y sin fallar por no poder mezclar los atributos
_REPLACEFILE_IGNORE_MERGE_ERRORS = 0x00000002
# Errores de Windows que pueden ser de un momento: acceso denegado, en uso, bloqueado
_TRANSIENT_WINERRORS: frozenset[int] = frozenset({5, 32, 33})

# Errores que pueden dar mutagen o el disco al preparar o escribir (se dan como
# 'AudioWriteError'; lo que no vale de lo editado se comprueba antes, como 'ValueError')
_WRITE_ERRORS = (
    MutagenError, AudioReadError, OSError, ValueError, TypeError, KeyError, EOFError,
    struct.error,
)  # fmt: skip


class AudioWriteError(Exception):
    """No se ha podido escribir: el original queda como estaba."""


class UnsupportedAudioWriteError(AudioWriteError):
    """Las etiquetas de ese formato todavía no se escriben (hoy, todo lo que no es MP3)."""


class _VerifyError(AudioWriteError):
    """El temporal no es lo previsto: no sustituye al original."""


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
class _Plan:
    """Lo preparado para escribir un MP3 y lo que se espera encontrar en el temporal."""

    wanted: dict[str, Any]  # lo editado, ya limpio
    current: TagSet
    target: TagSet
    version: int  # la del ID3v2 que se escribe
    tags: ID3  # la etiqueta, ya con lo editado
    expected_view: AudioTags  # cómo la leerá el catálogo
    expected_v1: Id3v1Tag | None
    # Solo si el ID3v2 ya estaba: los marcos no editados y los desconocidos de antes
    untouched: dict[str, str] | None
    unknown: list[bytes] | None
    audio_digest: str


# =============================================================================
# Escribir
# =============================================================================


def write_tags(
    path: Path, changes: Mapping[str, Any], preferred: TagSet = DEFAULT_MP3_TAGS
) -> TagWriteResult:
    """Escribe lo editado en las etiquetas de una canción (ver el docstring del archivo).

    Args:
        path: La canción.
        changes: Lo editado (ver «Lo editado» en el docstring del archivo).
        preferred: La etiqueta preferida de los MP3 (la de las Opciones): la que se crea si
            le falta el ID3v2.

    Raises:
        ValueError, TypeError: Si lo editado no vale o 'preferred' no es la de un MP3.
        UnsupportedAudioWriteError: Si su formato todavía no se escribe.
        AudioWriteError: Si no se ha podido escribir (el original queda como estaba).
    """
    wanted = _clean_changes(changes)
    if preferred.id3v2 is None:
        raise ValueError(f"La etiqueta preferida de un MP3 lleva un ID3v2: «{preferred.text}»")
    try:
        before = path.stat()
        audio = open_audio(path)
    except FileNotFoundError as error:
        raise AudioWriteError(f"El archivo no existe: «{path.name}»") from error
    except UnsupportedAudioError as error:
        raise UnsupportedAudioWriteError(str(error)) from error
    except (AudioReadError, OSError) as error:
        raise AudioWriteError(f"No se ha podido leer «{path.name}»: {error}") from error
    if not isinstance(audio, MP3):
        raise UnsupportedAudioWriteError(
            f"Todavía no se escriben las etiquetas de «{path.name}» (solo las de los MP3)"
        )

    current = tag_set_of(audio, path)
    target = tags_for_edit(current, preferred)
    try:
        plan = _prepare(path, wanted, current, target)
    except AudioWriteError:
        raise
    except _WRITE_ERRORS as error:
        raise AudioWriteError(f"No se ha podido preparar «{path.name}»: {error}") from error
    if plan is None:
        return TagWriteResult(False, current, current)  # ya tenía lo pedido
    if not os.access(path, os.W_OK):
        raise AudioWriteError(f"«{path.name}» es de solo lectura")
    _write_and_replace(path, before, plan)
    return TagWriteResult(True, current, target)


def _prepare(
    path: Path, wanted: dict[str, Any], current: TagSet, target: TagSet
) -> _Plan | None:
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
    return _Plan(
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


def _write_and_replace(path: Path, before: os.stat_result, plan: _Plan) -> None:
    """Escribe en el temporal, lo comprueba y sustituye el original.

    Raises:
        AudioWriteError: Si algo falla (el original queda como estaba).
    """
    temp = path.with_name(f".{path.name}{_TEMP_SUFFIX}")
    replaced = False
    try:
        temp.unlink(missing_ok=True)  # uno que quedara de una escritura interrumpida
        shutil.copyfile(path, temp)
        if plan.current.id3v1:
            # El ID3v1 lo quita y lo pone la aplicación (mutagen lo rehace entero y lo
            # busca de una forma más laxa: docs/TRAMPAS.md)
            os.truncate(temp, temp.stat().st_size - ID3V1_SIZE)
        plan.tags.save(temp, v1=0, v2_version=plan.version, v23_sep=None)
        if plan.expected_v1 is not None:
            with temp.open("ab") as file:
                file.write(build_id3v1(plan.expected_v1))
        _verify(temp, plan)
        if not _same_state(path, before):
            raise AudioWriteError(f"«{path.name}» ha cambiado mientras se escribía: no se toca")
        _replace(temp, path)
        replaced = True
    except AudioWriteError:
        raise
    except _WRITE_ERRORS as error:
        raise AudioWriteError(f"No se ha podido escribir «{path.name}»: {error}") from error
    finally:
        if not replaced:
            _discard(temp, path)  # con cualquier error, también uno inesperado


def _verify(temp: Path, plan: _Plan) -> None:
    """Comprueba el temporal (ver el paso 5 del docstring del archivo).

    Raises:
        _VerifyError: Si no es lo previsto.
    """
    name = temp.name.removeprefix(".").removesuffix(_TEMP_SUFFIX)

    def fail(what: str) -> None:
        raise _VerifyError(f"No se escribe «{name}»: {what}")

    if tag_set_of(open_audio(temp), temp) != plan.target:
        fail("las etiquetas no son las previstas")
    written = ID3(temp, translate=False, load_v1=False)
    if written.version[:2] != (2, plan.version):
        fail("la versión del ID3v2 no es la prevista")
    if _view(written) != plan.expected_view:
        fail("lo escrito no se lee como se pidió")
    if plan.untouched is not None and (
        _untouched_frames(written, plan.wanted) != plan.untouched
        or list(written.unknown_frames) != plan.unknown
    ):
        fail("ha cambiado algo que no se había editado")
    if plan.expected_v1 is not None and parse_id3v1(_tail(temp, ID3V1_SIZE)) != plan.expected_v1:
        fail("el ID3v1 no es el previsto")
    if _audio_digest(temp, has_v1=plan.target.id3v1) != plan.audio_digest:
        fail("el audio no es el mismo")


def _discard(temp: Path, path: Path) -> None:
    """Borra el temporal tras un fallo. Si el original no está (no debería pasar), el
    temporal se deja: es la única copia."""
    try:
        if path.exists():
            temp.unlink(missing_ok=True)
        elif temp.exists():
            logger.error(f"No está «{path}» tras un fallo al escribirlo: su copia es «{temp}»")
    except OSError as error:
        logger.warning(f"No se ha podido borrar el temporal «{temp}»: {error}")


# =============================================================================
# Lo editado
# =============================================================================


def _clean_changes(changes: Mapping[str, Any]) -> dict[str, Any]:
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
            if text is not None and key in _LIST_FIELDS:
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
    match = _DATE_PATTERN.fullmatch(text)
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
            text = None if number is None else (f"{number}/{total}" if total else f"{number}")
            _set_text(tags, field.id3, None if text is None else [text], encoding)
            expected[f"{key}_number"], expected[f"{key}_total"] = number, total
        else:
            texts: list[str] | None = None
            if value is not None:
                split = version == 4 and key in _LIST_FIELDS
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
    match = _DATE_PATTERN.fullmatch(value)
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


# =============================================================================
# La etiqueta
# =============================================================================


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
    for frame in tags.values():
        if hasattr(frame, "encoding"):
            frame.encoding = encoding
    return tags


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


# =============================================================================
# El archivo
# =============================================================================


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


def _same_state(path: Path, before: os.stat_result) -> bool:
    """True si el archivo sigue como al empezar (mismo tamaño y fecha de modificación)."""
    try:
        now = path.stat()
    except OSError:
        return False
    return (now.st_size, now.st_mtime_ns) == (before.st_size, before.st_mtime_ns)


def _replace(temp: Path, path: Path) -> None:
    """El temporal sustituye al original (ver el paso 6 del docstring del archivo).

    Raises:
        OSError: Si no se ha podido (tras reintentar si estaba en uso un momento).
    """
    for attempt in range(1, _REPLACE_ATTEMPTS + 1):
        try:
            if _IS_WINDOWS:
                _replace_file_windows(path, temp)
            else:
                shutil.copymode(path, temp)
                os.replace(temp, path)
            return
        except OSError as error:
            transient = getattr(error, "winerror", None) in _TRANSIENT_WINERRORS
            if attempt == _REPLACE_ATTEMPTS or not transient:
                raise
            time.sleep(_REPLACE_WAIT)


def _replace_file_windows(replaced: Path, replacement: Path) -> None:
    """'ReplaceFileW': 'replacement' pasa a ser 'replaced', que conserva su fecha de
    creación, sus atributos y sus permisos.

    Raises:
        OSError: Si Windows no lo hace.
    """
    import ctypes  # solo en Windows
    from ctypes import wintypes

    function = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
    function.argtypes = (
        wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        wintypes.LPVOID, wintypes.LPVOID,
    )  # fmt: skip
    function.restype = wintypes.BOOL
    flags = _REPLACEFILE_IGNORE_MERGE_ERRORS
    if not function(str(replaced), str(replacement), None, flags, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


if __name__ == "__main__":
    # Autoprueba (sin Qt). Crea MP3 mínimos en una carpeta temporal y escribe en ellos.
    # Desde la raíz del proyecto:
    #     python -m core.audio.tag_writer
    import stat
    import tempfile

    from mutagen.flac import FLAC
    from mutagen.id3 import APIC, PRIV, TALB, TCON, TIME, TIT2, TPE1, TRCK, TSIZ, TSOP, TXXX

    from core.audio.id3v1 import NO_GENRE
    from core.audio.tag_reader import read_audio

    FRAME = b"\xff\xfb\x90\x00" + bytes(413)  # una trama de silencio (MPEG-1 Layer III)
    AUDIO = FRAME * 40
    APE_FOOTER = b"APETAGEX" + bytes(24)  # basta el pie: el lector solo lo detecta

    def raw(path: Path) -> ID3:
        """La etiqueta tal como está en el archivo (sin convertir ni mezclar el ID3v1)."""
        return ID3(path, translate=False, load_v1=False)

    def insert_frame(path: Path, name: bytes, body: bytes) -> None:
        """Mete un marco de v2.3 en bruto en el relleno de la etiqueta (lo que mutagen no
        deja hacer: uno desconocido, dos repetidos)."""
        tags = raw(path)
        end = tags.size - tags._padding
        frame = name + struct.pack(">I", len(body)) + b"\x00\x00" + body
        assert tags._padding >= len(frame)
        data = bytearray(path.read_bytes())
        data[end : end + len(frame)] = frame
        path.write_bytes(bytes(data))

    def expect_error(error_type: type[Exception], *args: Any) -> None:
        """Llamar a 'write_tags' con 'args' tiene que fallar con 'error_type'."""
        try:
            write_tags(*args)
        except error_type:
            return
        raise AssertionError(f"debía fallar: {args}")

    with tempfile.TemporaryDirectory(prefix="arca_tag_writer_") as folder:
        root = Path(folder)

        # --- 1. Un ID3v2.3 con de todo, ID3v1 y APEv2: solo cambia lo editado
        rich = root / "rica.mp3"
        rich.write_bytes(AUDIO)
        tags = ID3()
        tags.add(TIT2(encoding=0, text=["Título viejo"]))  # en Latin-1
        tags.add(TPE1(encoding=1, text=["Estopa", "Rosendo"]))  # dos valores
        tags.add(TALB(encoding=1, text=["Destrangis"]))
        tags.add(TYER(encoding=0, text=["2001"]))
        tags.add(TDAT(encoding=0, text=["0405"]))
        tags.add(TIME(encoding=0, text=["1200"]))
        tags.add(TRCK(encoding=0, text=["3/12"]))
        tags.add(TCON(encoding=0, text=["Rock"]))
        tags.add(TSOP(encoding=1, text=["Estopa"]))  # de v2.4: iTunes lo pone en v2.3
        tags.add(TSIZ(encoding=0, text=["12345"]))  # de v2.3: mutagen lo quita al convertir
        tags.add(PRIV(owner="WM/MediaClassPrimaryID", data=b"\x01\x02"))
        tags.add(TXXX(encoding=1, desc="REPLAYGAIN_TRACK_GAIN", text=["-6.5 dB"]))
        tags.add(COMM(encoding=1, lang="eng", desc="iTunNORM", text=[" 0000 0000"]))
        tags.add(COMM(encoding=1, lang="spa", desc="", text=["Viejo comentario"]))
        tags.add(APIC(encoding=0, mime="image/jpeg", type=3, desc="", data=b"portada"))
        tags.save(rich, v2_version=3, v1=2, v23_sep=None)
        # Otra imagen sin descripción (portada y contraportada, como en muchos archivos):
        # 'add' de mutagen sustituiría la primera; al leer el archivo, las conserva las dos
        insert_frame(rich, b"APIC", b"\x00image/jpeg\x00\x04\x00contra")
        insert_frame(rich, b"XYZW", b"desconocido")  # un marco que mutagen no conoce
        v1_bytes = rich.read_bytes()[-ID3V1_SIZE:]
        rich.write_bytes(rich.read_bytes()[:-ID3V1_SIZE] + APE_FOOTER + v1_bytes)
        assert read_audio(rich).tag_type == "ID3v2.3 + ID3v1 + APEv2"
        before = raw(rich)
        assert len(before.unknown_frames) == 1 and len(before.getall("APIC")) == 2
        # Un temporal que quedó de una escritura interrumpida: se sustituye y se borra
        (root / f".rica.mp3{_TEMP_SUFFIX}").write_bytes(b"resto")
        birth = rich.stat().st_birthtime if _IS_WINDOWS else None
        time.sleep(0.05)  # el temporal nace después: se notaría si cambiara la fecha
        result = write_tags(rich, {
            "title": "Vino Tinto", "album": None, "date": "2001-06-07",
            "comment": "Nuevo", "track": (4, 12),
        })  # fmt: skip
        assert result.written and not result.tags_changed, result
        assert result.tags_after == TagSet(id3v2=3, id3v1=True, ape=True)
        after = raw(rich)
        assert after.version == (2, 3, 0)
        assert after["TIT2"].text == ["Vino Tinto"] and after["TIT2"].encoding == Encoding.UTF16
        assert "TALB" not in after and "TIME" not in after
        assert after["TYER"].text == ["2001"] and after["TDAT"].text == ["0706"]  # DDMM
        assert after["TRCK"].text == ["4/12"]
        assert after["COMM::spa"].text == ["Nuevo"]  # el comentario, con su idioma
        edited = {"TIT2", "TALB", "TYER", "TDAT", "TIME", "TRCK"}

        def others(tags: ID3) -> dict[str, str]:
            """Los marcos no editados, con todo su contenido."""
            return {
                key: repr(frame)
                for key, frame in tags.items()
                if frame.FrameID not in edited and key != "COMM::spa"
            }

        assert others(after) == others(before)  # TSOP, TSIZ, PRIV, TXXX, imágenes...
        assert after.unknown_frames == before.unknown_frames
        assert after["TPE1"].text == ["Estopa", "Rosendo"]  # sin unir con «/»
        data = rich.read_bytes()
        assert AUDIO + APE_FOOTER in data  # el audio y el APEv2, tal cual
        assert parse_id3v1(data[-ID3V1_SIZE:]) == Id3v1Tag(
            "Vino Tinto", "Estopa", "", "2001", "Nuevo", 4, 17
        )  # lo editado; el artista y el género, los de antes
        info = read_audio(rich)
        assert info.tag_type == "ID3v2.3 + ID3v1 + APEv2"
        song = info.tags
        assert (song.title, song.album, song.date, song.comment) == (
            "Vino Tinto", None, "2001-06-07", "Nuevo"
        ), song  # fmt: skip
        assert (song.track_number, song.track_total, song.artist, song.genre) == (
            4, 12, "Estopa; Rosendo", "Rock"
        ), song  # fmt: skip
        if birth is not None:
            assert rich.stat().st_birthtime == birth  # la fecha de creación, la de antes
        # Lo mismo otra vez: ya lo tiene, no se toca
        mtime = rich.stat().st_mtime_ns
        again = write_tags(rich, {"title": "Vino Tinto", "date": "2001-06-07"})
        assert not again.written and rich.stat().st_mtime_ns == mtime
        # En v2.3: varios géneros, un texto; el mes sin día, solo el año
        write_tags(rich, {"genre": "Rock; Pop", "date": "1999-03"})
        after = raw(rich)
        assert after["TCON"].text == ["Rock; Pop"] and after["TYER"].text == ["1999"]
        assert "TDAT" not in after
        song = read_audio(rich).tags
        assert (song.genre, song.date) == ("Rock; Pop", "1999"), song

        # --- 2. Un ID3v2.4: se queda en v2.4, sin ID3v1 (aunque la preferida lo lleve)
        v24 = root / "v24.mp3"
        v24.write_bytes(AUDIO)
        tags = ID3()
        tags.add(TIT2(encoding=3, text=["Hola"]))
        tags.add(TCON(encoding=3, text=["Pop"]))
        tags.save(v24, v2_version=4, v1=0)
        result = write_tags(v24, {
            "genre": "Rock; Pop; Rock", "artist": " A; B ", "date": "2001-05",
            "track": (3, None), "disc": (1, 2), "composer": "",
        }, TagSet(id3v2=3, id3v1=True))  # fmt: skip
        assert result.written and result.tags_after == TagSet(id3v2=4), result
        after = raw(v24)
        assert after.version == (2, 4, 0)
        assert after["TCON"].text == ["Rock", "Pop"] and after["TPE1"].text == ["A", "B"]
        assert after["TCON"].encoding == Encoding.UTF8
        assert str(after["TDRC"]) == "2001-05" and "TYER" not in after
        assert after["TRCK"].text == ["3"] and after["TPOS"].text == ["1/2"]
        assert "TCOM" not in after and after["TIT2"].text == ["Hola"]
        song = read_audio(v24).tags
        assert (song.genre, song.artist, song.date) == ("Rock; Pop", "A; B", "2001-05"), song
        assert (song.track_number, song.disc_number, song.disc_total) == (3, 1, 2), song

        # --- 3. Sin etiquetas: la preferida, con lo editado
        bare = root / "sin_etiquetas.mp3"
        bare.write_bytes(AUDIO)
        result = write_tags(
            bare, {"title": "Nueva", "genre": "Pop Folk", "track": (1, 10)},
            TagSet(id3v2=3, id3v1=True),
        )  # fmt: skip
        assert result.tags_before == TagSet() and result.tags_changed
        assert read_audio(bare).tag_type == "ID3v2.3 + ID3v1"
        assert raw(bare)["TIT2"].encoding == Encoding.UTF16 and AUDIO in bare.read_bytes()
        new_v1 = parse_id3v1(bare.read_bytes()[-ID3V1_SIZE:])
        assert new_v1 is not None and (new_v1.title, new_v1.genre, new_v1.track) == (
            "Nueva", NO_GENRE, 1
        ), new_v1  # fmt: skip
        bare24 = root / "sin_etiquetas_24.mp3"
        bare24.write_bytes(AUDIO)
        assert write_tags(bare24, {"title": "X"}, TagSet(id3v2=4)).tags_after == TagSet(id3v2=4)
        assert read_audio(bare24).tag_type == "ID3v2.4"

        # --- 4. Solo ID3v1: un ID3v2.3 completo (con su comentario) y el ID3v1, al día
        only_v1 = root / "solo_v1.mp3"
        old_tag = Id3v1Tag("Antigua", "Artista", "Álbum", "1999", "Comentario v1", 5, 17)
        only_v1.write_bytes(AUDIO + build_id3v1(old_tag))
        result = write_tags(only_v1, {"title": "Moderna"})
        assert result.tags_after == TagSet(id3v2=3, id3v1=True), result
        after = raw(only_v1)
        assert (after["TIT2"].text, after["TPE1"].text, after["TALB"].text) == (
            ["Moderna"], ["Artista"], ["Álbum"]
        )  # fmt: skip
        assert after["TYER"].text == ["1999"] and after["TRCK"].text == ["5"]
        assert after["TCON"].text == ["Rock"]  # el nombre, no el número del ID3v1
        comments = [(frame.desc, frame.text) for frame in after.getall("COMM")]
        assert comments == [("", ["Comentario v1"])], comments
        assert all(f.encoding == Encoding.UTF16 for f in after.values() if hasattr(f, "encoding"))
        assert parse_id3v1(only_v1.read_bytes()[-ID3V1_SIZE:]) == replace(old_tag, title="Moderna")
        assert read_audio(only_v1).tags.comment == "Comentario v1"

        # --- 5. Un ID3v2.2 (mutagen no lo escribe): pasa a la versión preferida
        body = b"TT2" + (6).to_bytes(3, "big") + b"\x00Viejo"
        body += b"TP1" + (8).to_bytes(3, "big") + b"\x00Artista"
        v22 = root / "v22.mp3"
        v22.write_bytes(b"ID3\x02\x00\x00\x00\x00\x00" + bytes([len(body)]) + body + AUDIO)
        assert read_audio(v22).tag_type == "ID3v2.2"
        assert write_tags(v22, {"album": "Nuevo"}).tags_after == TagSet(id3v2=3)
        song = read_audio(v22).tags
        assert (song.title, song.artist, song.album) == ("Viejo", "Artista", "Nuevo"), song
        assert AUDIO in v22.read_bytes()

        # --- 6. Lo que no vale y lo que no se escribe (el archivo, como estaba)
        flac = root / "cancion.flac"
        streaminfo = struct.pack(">HH", 4096, 4096) + bytes(6)
        streaminfo += ((44100 << 44) | (1 << 41) | (15 << 36) | 88200).to_bytes(8, "big")
        streaminfo += bytes(16)
        flac.write_bytes(b"fLaC\x80" + len(streaminfo).to_bytes(3, "big") + streaminfo)
        FLAC(flac)  # es un FLAC de verdad
        expect_error(UnsupportedAudioWriteError, flac, {"title": "X"})
        expect_error(AudioWriteError, root / "no_existe.mp3", {"title": "X"})
        for bad in ({"titulo": "X"}, {"date": "05/2001"}, {"date": "0000"}, {"track": (0, 1)},
                    {"track": "3/12"}, {"disc": (True, None)}):  # fmt: skip
            expect_error(ValueError, v24, bad)
        expect_error(TypeError, v24, {"title": 3})
        expect_error(ValueError, v24, {"title": "X"}, TagSet(vorbis=True))
        # Solo lectura
        locked = root / "solo_lectura.mp3"
        shutil.copyfile(v24, locked)
        content = locked.read_bytes()
        os.chmod(locked, stat.S_IREAD)
        try:
            expect_error(AudioWriteError, locked, {"title": "No"})
        finally:
            os.chmod(locked, stat.S_IREAD | stat.S_IWRITE)
        assert locked.read_bytes() == content
        # Dos letras con la misma descripción e idioma: mutagen perdería una (dos
        # comentarios, no: son marcos de texto y los junta, con sus dos valores)
        repeated = root / "repetidos.mp3"
        repeated.write_bytes(AUDIO)
        tags = ID3()
        tags.add(TIT2(encoding=0, text=["Repetidos"]))
        tags.save(repeated, v2_version=3, v1=0)
        for text in (b"uno", b"dos"):
            insert_frame(repeated, b"USLT", b"\x00eng" + b"Letra\x00" + text)
        content = repeated.read_bytes()
        expect_error(AudioWriteError, repeated, {"title": "No"})
        assert repeated.read_bytes() == content
        # El original cambia mientras se escribe: no se sustituye
        changing = root / "cambia.mp3"
        shutil.copyfile(v24, changing)
        real_verify = _verify

        def verify_and_touch(temp: Path, plan: _Plan) -> None:
            """La comprobación de siempre y, después, alguien cambia el original."""
            real_verify(temp, plan)
            with changing.open("ab") as file:
                file.write(b"x")

        globals()["_verify"] = verify_and_touch
        try:
            expect_error(AudioWriteError, changing, {"title": "Otro"})
        finally:
            globals()["_verify"] = real_verify
        assert changing.read_bytes().endswith(b"x") and raw(changing)["TIT2"].text == ["Hola"]
        # La comprobación falla (el audio del temporal no es el mismo): no se sustituye
        real_digest = _audio_digest

        def other_digest(path: Path, *, has_v1: bool) -> str:
            """Otra huella para el temporal, como si su audio hubiera cambiado."""
            if path.name.endswith(_TEMP_SUFFIX):
                return "otra"
            return real_digest(path, has_v1=has_v1)

        globals()["_audio_digest"] = other_digest
        content = v24.read_bytes()
        try:
            expect_error(AudioWriteError, v24, {"title": "Otro"})
        finally:
            globals()["_audio_digest"] = real_digest
        assert v24.read_bytes() == content

        # Ningún temporal se ha quedado en la carpeta
        leftovers = list(root.glob(f"*{_TEMP_SUFFIX}"))
        assert not leftovers, leftovers

    print("Autoprueba finalizada correctamente.")
