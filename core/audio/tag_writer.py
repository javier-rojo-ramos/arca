"""Escritura de las etiquetas de una canción en el propio archivo, sin tocar nada más.

Este módulo NO depende de Qt ni de la base de datos: recibe una ruta y lo editado, y deja el
archivo con lo editado o como estaba. Es el motor del escritor de audio de la cola de
escritura ('core/userdata/audio_writer.py', MUS 6.2). Escribe MP3 (ID3v2 e ID3v1), FLAC,
Ogg Vorbis y Opus (comentarios Vorbis) y M4A (MP4).

    result = write_tags(path, {"title": "Vino Tinto", "track": (3, 12)}, preferred)
    result.written         # False si ya tenía esos valores (el archivo no se toca)
    result.tags_before     # 'TagSet' de antes: ID3v1
    result.tags_after      # y el de después: ID3v2.3 + ID3v1

Lo editado ('changes'): ver 'write_base.py' (las claves de 'tag_map.TAG_FIELDS', None para
vaciar; lo que no vale es 'ValueError' o 'TypeError').

DOS PARTES (MUS 6.3a): aquí, el recorrido común de toda escritura; lo propio de cada familia
de etiquetas, en su módulo, con la interfaz 'write_base.FormatWriter': 'id3_writer.py' (el
MP3), 'vorbis_writer.py' (FLAC, Ogg Vorbis y Opus) y 'mp4_writer.py' (M4A). Una familia
nueva es un módulo y una línea en '_FORMAT_WRITERS'.

CÓMO ESCRIBE (docs/MOD_MUSICA.md §5; reglas acordadas con el autor el 16 y el 27/11/2026):
    1. La familia del archivo ('_FORMAT_WRITERS'); si no hay ninguna, 'UnsupportedAudioWriteError'.
    2. En qué etiquetas: 'tag_set.tags_for_edit' (en las que tiene; si le falta la
       principal, la preferida de su familia, completa).
    3. La familia prepara lo editado ('FormatWriter.prepare'); si el archivo ya lo tenía,
       no se toca.
    4. Copia el archivo en un temporal de su carpeta ('.cancion.mp3.arca.tmp': el escáner no
       lo cataloga nunca, por el punto y por '.tmp') y la familia escribe en él ('save').
    5. Comprueba el temporal antes de usarlo: que tiene las etiquetas previstas y lo que
       comprueba la familia ('verify': lo editado, lo demás, el audio).
    6. Si el original no ha cambiado mientras tanto, el temporal lo sustituye: en Windows, con
       'ReplaceFileW', que conserva la fecha de creación, los atributos y los permisos del
       original; en macOS y Linux, con 'os.replace' (y los permisos del original). Si el
       archivo está en uso un momento (un antivirus, el indexador), se reintenta.
Si algo falla, el original queda como estaba, el temporal se borra y se lanza
'AudioWriteError'. La fecha de modificación del archivo cambia, como con las fotos.

1.3.2 Autoprueba: los saltos de línea del comentario («\r\n» en el archivo; MUS 7.1c).
1.3.1 Autoprueba: varios valores escritos a mano («Rock;Pop;») y la pista y el disco con
      dos cifras («04/12», MUS 7.1b).
1.3.0 La familia MP4: M4A ('mp4_writer.py', MUS 6.4).
1.2.0 La familia Vorbis: FLAC, Ogg Vorbis y Opus ('vorbis_writer.py', MUS 6.3b).
1.1.0 En dos partes (MUS 6.3a): el recorrido común, aquí; lo del MP3, a 'id3_writer.py'; lo
      que comparten, a 'write_base.py'. Nada cambia en lo que hace.
1.0.0 Primera versión (27/11/2026; docs/MOD_MUSICA.md, paso MUS 6.1c).

Prueba rápida (desde la raíz del proyecto; crea MP3, FLAC, Ogg, Opus y M4A mínimos en una
carpeta temporal):
    python -m core.audio.tag_writer
"""

__version__ = "1.3.2"
__all__ = ["AudioWriteError", "TagWriteResult", "UnsupportedAudioWriteError", "write_tags"]

# Librerías estándar
import os
import shutil
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.audio.id3_writer import Id3Writer
from core.audio.mp4_writer import Mp4Writer
from core.audio.tag_reader import AudioReadError, UnsupportedAudioError, open_audio, tag_set_of
from core.audio.tag_set import DEFAULT_MP3_TAGS, TagSet, tags_for_edit
from core.audio.vorbis_writer import VorbisWriter
from core.audio.write_base import (
    WRITE_ERRORS,
    AudioWriteError,
    FormatWriter,
    PreparedWrite,
    TagWriteResult,
    UnsupportedAudioWriteError,
    clean_changes,
)

# El temporal: en la misma carpeta, oculto por el punto y con '.tmp' (el escáner lo salta)
_TEMP_SUFFIX = ".arca.tmp"
# Sustituir el original: intentos si está en uso un momento, y la espera entre ellos
_REPLACE_ATTEMPTS = 5
_REPLACE_WAIT = 0.1  # segundos
_IS_WINDOWS = sys.platform == "win32"
# ReplaceFileW: sin copia de seguridad y sin fallar por no poder mezclar los atributos
_REPLACEFILE_IGNORE_MERGE_ERRORS = 0x00000002
# Errores de Windows que pueden ser de un momento: acceso denegado, en uso, bloqueado
_TRANSIENT_WINERRORS: frozenset[int] = frozenset({5, 32, 33})

# Las familias de etiquetas que se escriben, cada una con lo suyo ('write_base.FormatWriter')
_FORMAT_WRITERS: tuple[FormatWriter, ...] = (Id3Writer(), VorbisWriter(), Mp4Writer())


class _VerifyError(AudioWriteError):
    """El temporal no es lo previsto: no sustituye al original."""


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
    wanted = clean_changes(changes)
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
    writer = next((family for family in _FORMAT_WRITERS if family.handles(audio)), None)
    if writer is None:
        raise UnsupportedAudioWriteError(
            f"Todavía no se escriben las etiquetas de «{path.name}» (solo las de MP3, FLAC, Ogg Vorbis, Opus y M4A)"
        )

    current = tag_set_of(audio, path)
    target = tags_for_edit(current, writer.preferred(preferred))
    try:
        prepared = writer.prepare(path, wanted, current, target)
    except AudioWriteError:
        raise
    except WRITE_ERRORS as error:
        raise AudioWriteError(f"No se ha podido preparar «{path.name}»: {error}") from error
    if prepared is None:
        return TagWriteResult(False, current, current)  # ya tenía lo pedido
    if not os.access(path, os.W_OK):
        raise AudioWriteError(f"«{path.name}» es de solo lectura")
    _write_and_replace(path, before, writer, prepared)
    return TagWriteResult(True, current, target)


def _write_and_replace(
    path: Path, before: os.stat_result, writer: FormatWriter, prepared: PreparedWrite
) -> None:
    """Escribe en el temporal, lo comprueba y sustituye el original.

    Raises:
        AudioWriteError: Si algo falla (el original queda como estaba).
    """
    temp = path.with_name(f".{path.name}{_TEMP_SUFFIX}")
    replaced = False
    try:
        temp.unlink(missing_ok=True)  # uno que quedara de una escritura interrumpida
        shutil.copyfile(path, temp)
        writer.save(prepared, temp)
        _verify(temp, writer, prepared)
        if not _same_state(path, before):
            raise AudioWriteError(f"«{path.name}» ha cambiado mientras se escribía: no se toca")
        _replace(temp, path)
        replaced = True
    except AudioWriteError:
        raise
    except WRITE_ERRORS as error:
        raise AudioWriteError(f"No se ha podido escribir «{path.name}»: {error}") from error
    finally:
        if not replaced:
            _discard(temp, path)  # con cualquier error, también uno inesperado


def _verify(temp: Path, writer: FormatWriter, prepared: PreparedWrite) -> None:
    """Comprueba el temporal (ver el paso 5 del docstring del archivo).

    Raises:
        _VerifyError: Si no es lo previsto.
    """
    name = temp.name.removeprefix(".").removesuffix(_TEMP_SUFFIX)

    def fail(what: str) -> None:
        raise _VerifyError(f"No se escribe «{name}»: {what}")

    if tag_set_of(open_audio(temp), temp) != prepared.target:
        fail("las etiquetas no son las previstas")
    problem = writer.verify(prepared, temp)
    if problem is not None:
        fail(problem)


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
# El archivo
# =============================================================================


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
    # Autoprueba (sin Qt). Crea MP3, FLAC, Ogg, Opus y M4A mínimos en una carpeta temporal y
    # escribe en ellos.
    # Desde la raíz del proyecto:
    #     python -m core.audio.tag_writer
    import stat
    import struct
    import tempfile
    from dataclasses import replace

    from mutagen._vorbis import VCommentDict
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import (
        APIC,
        COMM,
        ID3,
        PRIV,
        TALB,
        TCON,
        TDAT,
        TIME,
        TIT2,
        TPE1,
        TRCK,
        TSIZ,
        TSOP,
        TXXX,
        TYER,
        Encoding,
    )
    from mutagen.mp4 import MP4, Atom, Atoms
    from mutagen.ogg import OggPage
    from mutagen.oggopus import OggOpus
    from mutagen.oggvorbis import OggVorbis

    from core.audio import id3_writer, mp4_writer
    from core.audio.id3v1 import ID3V1_SIZE, NO_GENRE, Id3v1Tag, build_id3v1, parse_id3v1
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
        assert after["TRCK"].text == ["04/12"]
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
        assert after["TRCK"].text == ["03"] and after["TPOS"].text == ["01/2"]
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
        assert after["TYER"].text == ["1999"] and after["TRCK"].text == ["05"]
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
        wav = root / "cancion.wav"  # un WAV: todavía no se escribe
        fmt = struct.pack("<HHIIHH", 1, 2, 44100, 44100 * 4, 4, 16)
        body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
        body += b"data" + struct.pack("<I", 400) + bytes(400)
        wav.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
        expect_error(UnsupportedAudioWriteError, wav, {"title": "X"})
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

        def verify_and_touch(temp: Path, writer: FormatWriter, prepared: PreparedWrite) -> None:
            """La comprobación de siempre y, después, alguien cambia el original."""
            real_verify(temp, writer, prepared)
            with changing.open("ab") as file:
                file.write(b"x")

        globals()["_verify"] = verify_and_touch
        try:
            expect_error(AudioWriteError, changing, {"title": "Otro"})
        finally:
            globals()["_verify"] = real_verify
        assert changing.read_bytes().endswith(b"x") and raw(changing)["TIT2"].text == ["Hola"]
        # La comprobación falla (el audio del temporal no es el mismo): no se sustituye
        real_digest = id3_writer._audio_digest  # el del MP3, en su módulo

        def other_digest(path: Path, *, has_v1: bool) -> str:
            """Otra huella para el temporal, como si su audio hubiera cambiado."""
            if path.name.endswith(_TEMP_SUFFIX):
                return "otra"
            return real_digest(path, has_v1=has_v1)

        id3_writer._audio_digest = other_digest
        content = v24.read_bytes()
        try:
            expect_error(AudioWriteError, v24, {"title": "Otro"})
        finally:
            id3_writer._audio_digest = real_digest
        assert v24.read_bytes() == content

        # --- 7. Vorbis (MUS 6.3b): FLAC, Ogg Vorbis y Opus
        streaminfo = struct.pack(">HH", 4096, 4096) + bytes(6)
        streaminfo += ((44100 << 44) | (1 << 41) | (15 << 36) | 88200).to_bytes(8, "big")
        streaminfo += bytes(16)
        flac_audio = bytes(range(256)) * 8  # las «tramas» (mutagen no las mira)

        def new_flac(name: str, comments: list[tuple[str, str]] | None) -> Path:
            """Un FLAC mínimo, sin relleno (como los del autor), con una imagen y esos
            comentarios, tal cual (None: sin bloque de comentarios)."""
            flac_path = root / name
            flac_path.write_bytes(
                b"fLaC\x80" + len(streaminfo).to_bytes(3, "big") + streaminfo + flac_audio
            )
            flac = FLAC(flac_path)
            picture = Picture()
            picture.type, picture.mime, picture.data = 3, "image/jpeg", b"portada"
            flac.add_picture(picture)
            if comments is not None:
                flac.add_tags()
                flac.tags.extend(comments)
            flac.save(padding=lambda info: 0)
            return flac_path

        def comments_of(tags: Any) -> dict[str, list[str]]:
            """Los campos de unos comentarios Vorbis, con la clave como está escrita."""
            found: dict[str, list[str]] = {}
            for key, value in tags:
                found.setdefault(key, []).append(value)
            return found

        # a) Un FLAC con otros nombres de los campos (los de foobar2000): se actualizan
        #    también; vaciar quita todos; la imagen, el vendor y el audio, intactos
        rich_flac = new_flac("rica.flac", [
            ("TITLE", "Viejo"), ("Artist", "Estopa"), ("ALBUM ARTIST", "Varios"),
            ("TRACKNUMBER", "03"), ("TOTALTRACKS", "12"), ("GENRE", "Rock"),
            ("DESCRIPTION", "Nota"), ("ORGANIZATION", "Warner"),
            ("REPLAYGAIN_TRACK_GAIN", "-6 dB"),
        ])  # fmt: skip
        vendor = FLAC(rich_flac).tags.vendor
        result = write_tags(rich_flac, {
            "title": "Nuevo", "artist": "Estopa", "album_artist": "Estopa", "track": (4, 15),
            "genre": "Rock; Pop; Jazz", "comment": None,
        })  # fmt: skip
        assert result.written and result.tags_after == TagSet(vorbis=True), result
        after_flac = FLAC(rich_flac)
        found = comments_of(after_flac.tags)
        assert found["TITLE"] == ["Nuevo"] and found["Artist"] == ["Estopa"], found
        assert found["ALBUMARTIST"] == found["ALBUM ARTIST"] == ["Estopa"], found
        assert found["TRACKNUMBER"] == ["04"], found
        assert found["TRACKTOTAL"] == found["TOTALTRACKS"] == ["15"], found
        assert found["GENRE"] == ["Rock", "Pop", "Jazz"], found
        assert "DESCRIPTION" not in found and "COMMENT" not in found, found
        assert found["ORGANIZATION"] == ["Warner"] and found["REPLAYGAIN_TRACK_GAIN"] == ["-6 dB"]
        assert after_flac.tags.vendor == vendor
        assert [picture.data for picture in after_flac.pictures] == [b"portada"]
        assert rich_flac.read_bytes().endswith(flac_audio)
        song = read_audio(rich_flac).tags
        assert (song.title, song.album_artist, song.genre, song.comment) == (
            "Nuevo", "Estopa", "Rock; Pop; Jazz", None
        ), song  # fmt: skip
        assert (song.track_number, song.track_total) == (4, 15), song
        mtime = rich_flac.stat().st_mtime_ns  # lo mismo otra vez: no se toca
        assert not write_tags(rich_flac, {"title": "Nuevo", "track": (4, 15)}).written
        assert rich_flac.stat().st_mtime_ns == mtime

        # b) «3/12» en la pista: se mantiene esa forma; sin total, fuera sus campos
        slash = new_flac("barra.flac", [
            ("TITLE", "Barra"), ("TRACKNUMBER", "3/12"), ("TRACKTOTAL", "12"),
        ])  # fmt: skip
        write_tags(slash, {"track": (5, 12)})
        assert FLAC(slash).tags["TRACKNUMBER"] == ["05/12"]
        assert FLAC(slash).tags["TRACKTOTAL"] == ["12"]
        write_tags(slash, {"track": (5, None)})
        assert FLAC(slash).tags["TRACKNUMBER"] == ["05"] and "TRACKTOTAL" not in FLAC(slash).tags
        assert (read_audio(slash).tags.track_number, read_audio(slash).tags.track_total) == (
            5, None
        )  # fmt: skip
        # Varios valores escritos a mano, con «;» sin espacio y al final (MUS 7.1b)
        write_tags(slash, {"genre": "Rock;Pop;"})
        assert FLAC(slash).tags["GENRE"] == ["Rock", "Pop"]

        # c) Un FLAC sin bloque de comentarios: se le crea
        bare_flac = new_flac("sin_comentarios.flac", None)
        assert read_audio(bare_flac).tag_type == ""
        result = write_tags(bare_flac, {"title": "Nuevo"})
        assert result.tags_changed and read_audio(bare_flac).tag_type == "Vorbis"
        assert read_audio(bare_flac).tags.title == "Nuevo"
        assert FLAC(bare_flac).pictures[0].data == b"portada"
        assert bare_flac.read_bytes().endswith(flac_audio)

        # d) Ogg Vorbis y Opus mínimos: la cabecera de identificación en su página; los
        #    comentarios (y la configuración) en las suyas, con -1 en las que no terminan
        #    ningún paquete, como un codificador de verdad; 30 paquetes de «audio»
        audio_packets = [bytes([number]) * 300 for number in range(30)]
        vorbis_head = b"\x01vorbis" + struct.pack("<IBIiiiBB", 0, 2, 44100, 0, 128000, 0, 0xB8, 1)
        vorbis_setup = b"\x05vorbis" + bytes(40)
        opus_head = b"OpusHead" + struct.pack("<BBHIhB", 1, 2, 312, 48000, 0, 0)

        def new_ogg(name: str, head: bytes, comments: VCommentDict, setup: bytes | None) -> Path:
            """Un Ogg mínimo (Vorbis si lleva 'setup'; si no, Opus)."""
            if setup is not None:
                headers = [b"\x03vorbis" + comments.write(), setup]
            else:
                headers = [b"OpusTags" + comments.write(framing=False)]
            first = OggPage()
            first.packets, first.first, first.serial = [head], True, 7
            pages = [first]
            for page in OggPage.from_packets(headers, sequence=1):
                page.serial, page.position = 7, 0 if page.complete else -1
                pages.append(page)
            sound = OggPage.from_packets(audio_packets, sequence=len(pages))
            for number, page in enumerate(sound, start=1):
                page.serial, page.position = 7, number * 960
            sound[-1].last = True
            ogg_path = root / name
            ogg_path.write_bytes(b"".join(page.write() for page in [*pages, *sound]))
            return ogg_path

        def ogg_packets(ogg_path: Path) -> list[bytes]:
            """Los paquetes de un Ogg (de su único flujo), leídos aparte."""
            pages = []
            with ogg_path.open("rb") as file:
                while True:
                    try:
                        pages.append(OggPage(file))
                    except EOFError:
                        return OggPage.to_packets(pages)

        ogg_comments = VCommentDict()
        ogg_comments.vendor = "Xiph.Org libVorbis (prueba)"
        ogg_comments["TITLE"] = ["Viejo"]
        ogg_comments["ORGANIZATION"] = ["Warner"]
        # Como la carátula de los Ogg del autor: en un campo, en varias páginas
        ogg_comments["METADATA_BLOCK_PICTURE"] = ["A" * 20000]
        ogg = new_ogg("cancion.ogg", vorbis_head, ogg_comments, vorbis_setup)
        assert read_audio(ogg).tag_type == "Vorbis" and read_audio(ogg).tags.title == "Viejo"
        before_packets = ogg_packets(ogg)
        result = write_tags(ogg, {"title": "Ogg nuevo", "album": "Álbum", "artist": "A; B"})
        assert result.written and not result.tags_changed, result
        after_ogg = OggVorbis(ogg)
        assert after_ogg.tags["TITLE"] == ["Ogg nuevo"] and after_ogg.tags["ARTIST"] == ["A", "B"]
        assert after_ogg.tags["METADATA_BLOCK_PICTURE"] == ["A" * 20000]
        assert after_ogg.tags["ORGANIZATION"] == ["Warner"]
        assert after_ogg.tags.vendor == "Xiph.Org libVorbis (prueba)"
        after_packets = ogg_packets(ogg)
        # La identificación, la configuración y el audio, idénticos (los comentarios, no)
        assert after_packets[0] == before_packets[0] and after_packets[2:] == before_packets[2:]
        song = read_audio(ogg).tags
        assert (song.title, song.artist, song.album) == ("Ogg nuevo", "A; B", "Álbum"), song

        opus_comments = VCommentDict()
        opus_comments.vendor = "libopus (prueba)"
        opus_comments["TITLE"] = ["Viejo"]
        opus = new_ogg("cancion.opus", opus_head, opus_comments, None)
        assert isinstance(OggOpus(opus).tags, VCommentDict)
        before_packets = ogg_packets(opus)
        assert write_tags(opus, {"title": "Opus nuevo", "date": "2001"}).written
        after_packets = ogg_packets(opus)
        assert after_packets[0] == before_packets[0] and after_packets[2:] == before_packets[2:]
        song = read_audio(opus).tags
        assert (song.title, song.date) == ("Opus nuevo", "2001"), song

        # --- 8. MP4 (MUS 6.4): M4A
        def box(name: bytes, *parts: bytes) -> bytes:
            """Un átomo con su contenido."""
            return Atom.render(name, b"".join(parts))

        def data_box(flags: int, payload: bytes) -> bytes:
            """El átomo 'data' de una etiqueta ('flags': su tipo; 1 es texto, 0 «implícito»)."""
            return box(b"data", struct.pack(">2I", flags, 0), payload)

        samples = [bytes([number]) * (90 + 7 * number) for number in range(40)]
        # Trozos de 3 muestras y uno de 1 al final (dos rachas en 'stsc'), como un codificador
        chunk_samples = [3] * 13 + [1]
        # Como los M4A del autor: el género como número ('gnre', 18 es Rock), la carátula de
        # tipo «implícito», el programa, iTunSMPB y el orden del álbum
        m4a_tags = [
            box(b"\xa9nam", data_box(1, b"Viejo")),
            box(b"\xa9ART", data_box(1, b"Estopa")),
            box(b"gnre", data_box(0, struct.pack(">H", 18))),
            box(b"trkn", data_box(0, struct.pack(">4H", 0, 3, 12, 0))),
            box(b"\xa9too", data_box(1, b"iTunes 12.9")),
            box(b"covr", data_box(0, b"\xff\xd8\xff\xe0portada")),
            box(b"----", box(b"mean", bytes(4), b"com.apple.iTunes"),
                box(b"name", bytes(4), b"iTunSMPB"), data_box(1, b" 00000000 00000840")),
            box(b"soal", data_box(1, b"Orden")),
        ]  # fmt: skip

        def new_m4a(
            name: str, items: list[bytes] | None, padding: int = 0, chapters: bool = True
        ) -> Path:
            """Un M4A mínimo: la cabecera ('moov', con una pista y sus tablas) antes del audio
            ('mdat'), con esas etiquetas en bruto (None: sin 'meta'), relleno junto a ellas y
            capítulos de Nero ('chpl'); sin capítulos ni etiquetas, sin 'udta'."""

            def moov(offsets: list[int]) -> bytes:
                sizes = [len(sample) for sample in samples]
                table_sizes = struct.pack(f">2I{len(sizes)}I", 0, len(sizes), *sizes)
                table_offsets = struct.pack(f">{len(offsets) + 1}I", len(offsets), *offsets)
                stbl = box(
                    b"stbl",
                    box(b"stsd", bytes(4), struct.pack(">I", 0)),
                    box(b"stts", bytes(4), struct.pack(">3I", 1, len(samples), 1024)),
                    box(b"stsc", bytes(4), struct.pack(">7I", 2, 1, 3, 1, 14, 1, 1)),
                    box(b"stsz", bytes(4), table_sizes),
                    box(b"stco", bytes(4), table_offsets),
                )
                mdia = box(
                    b"mdia",
                    box(b"mdhd", bytes(4), struct.pack(">4I2H", 0, 0, 44100, 40 * 1024, 0x55C4, 0)),
                    box(b"hdlr", bytes(8), b"soun", bytes(12), b"SoundHandler\x00"),
                    box(b"minf", box(b"smhd", bytes(8)), stbl),
                )  # fmt: skip
                parts = []
                if chapters:
                    parts.append(box(
                        b"chpl", b"\x01" + bytes(7), bytes([2]),
                        struct.pack(">Q", 0), bytes([5]), b"Uno 1",
                        struct.pack(">Q", 50_000_000), bytes([5]), b"Dos 2",
                    ))  # fmt: skip
                if items is not None:
                    meta = [bytes(4), box(b"hdlr", bytes(8), b"mdirappl", bytes(9))]
                    meta.append(box(b"ilst", *items))
                    if padding:
                        meta.append(box(b"free", bytes(padding)))
                    parts.append(box(b"meta", *meta))
                mvhd = box(
                    b"mvhd", bytes(4), struct.pack(">4I", 0, 0, 44100, 40 * 1024),
                    struct.pack(">IH", 0x10000, 0x100), bytes(70), struct.pack(">I", 2),
                )  # fmt: skip
                tkhd = box(b"tkhd", b"\x00\x00\x00\x07", bytes(80))
                udta = box(b"udta", *parts) if parts else b""
                return box(b"moov", mvhd, box(b"trak", tkhd, mdia), udta)

            ftyp = box(b"ftyp", b"M4A ", bytes(4), b"M4A mp42isom")
            free = box(b"free", bytes(64))  # como los del autor: tras la cabecera (no se usa)
            position = len(ftyp) + len(moov([0] * len(chunk_samples))) + len(free) + 8
            offsets, sample = [], 0
            for count in chunk_samples:
                offsets.append(position)
                position += sum(len(item) for item in samples[sample : sample + count])
                sample += count
            m4a_path = root / name
            m4a_path.write_bytes(ftyp + moov(offsets) + free + box(b"mdat", *samples))
            return m4a_path

        def m4a_items(m4a_path: Path) -> dict[bytes, list[bytes]]:
            """Los átomos de etiqueta de un M4A, enteros y en bruto (leídos aparte)."""
            found: dict[bytes, list[bytes]] = {}
            with m4a_path.open("rb") as file:
                for child in Atoms(file)[b"moov.udta.meta.ilst"].children:
                    file.seek(child.offset)
                    found.setdefault(child.name, []).append(file.read(child.length))
            return found

        def m4a_audio(m4a_path: Path) -> tuple[int, list[bytes]]:
            """Dónde empieza el audio de un M4A y sus muestras, leídas aparte con su 'stco'."""
            with m4a_path.open("rb") as file:
                stbl = Atoms(file)[b"moov.trak.mdia.minf.stbl"]
                _ok, table = next(stbl.findall(b"stco")).read(file)
                offsets = struct.unpack(f">{len(chunk_samples)}I", table[8:])
                found, sample = [], 0
                for offset, count in zip(offsets, chunk_samples, strict=True):
                    file.seek(offset)
                    found += [file.read(len(item)) for item in samples[sample : sample + count]]
                    sample += count
            return offsets[0], found

        # a) Sin relleno (como 178 de los 291 del autor): lo editado, en su átomo (varios
        #    valores, en un texto; sin total, 0); lo demás, byte a byte (también 'gnre' y la
        #    carátula, que mutagen cambiaría); el audio se desplaza, con sus tablas al día
        rich_m4a = new_m4a("rica.m4a", m4a_tags)
        original_m4a = rich_m4a.read_bytes()
        before_items = m4a_items(rich_m4a)
        before_offset, before_samples = m4a_audio(rich_m4a)
        assert before_samples == samples
        song = read_audio(rich_m4a)
        assert song.tag_type == "MP4" and (song.tags.genre, song.tags.track_number) == ("Rock", 3)
        result = write_tags(rich_m4a, {
            "title": "Nuevo", "artist": "A; B", "track": (4, None), "comment": "Nota",
        })  # fmt: skip
        assert result.written and result.tags_after == TagSet(mp4=True), result
        assert not result.tags_changed
        after_items = m4a_items(rich_m4a)
        for name in (b"gnre", b"covr", b"----", b"\xa9too", b"soal"):
            assert after_items[name] == before_items[name], name
        m4a = MP4(rich_m4a)
        assert m4a.tags["\xa9nam"] == ["Nuevo"] and m4a.tags["\xa9ART"] == ["A; B"]
        assert m4a.tags["trkn"] == [(4, 0)] and m4a.tags["\xa9cmt"] == ["Nota"]
        assert [(c.start, c.title) for c in m4a.chapters] == [(0.0, "Uno 1"), (5.0, "Dos 2")]
        after_offset, after_samples = m4a_audio(rich_m4a)
        assert after_offset > before_offset and after_samples == samples
        song = read_audio(rich_m4a).tags
        assert (song.title, song.artist, song.genre, song.comment) == (
            "Nuevo", "A; B", "Rock", "Nota"
        ), song  # fmt: skip
        assert (song.track_number, song.track_total) == (4, None), song
        mtime = rich_m4a.stat().st_mtime_ns  # lo mismo otra vez: no se toca
        assert not write_tags(rich_m4a, {"title": "Nuevo", "track": (4, None)}).written
        assert rich_m4a.stat().st_mtime_ns == mtime

        # b) El género: al editarlo se quita 'gnre'; al vaciarlo, se quitan los dos
        write_tags(rich_m4a, {"genre": "Pop; Rock"})
        after_items = m4a_items(rich_m4a)
        assert b"gnre" not in after_items and MP4(rich_m4a).tags["\xa9gen"] == ["Pop; Rock"]
        assert read_audio(rich_m4a).tags.genre == "Pop; Rock"
        assert after_items[b"covr"] == before_items[b"covr"]
        two_genres = new_m4a("dos_generos.m4a", [*m4a_tags, box(b"\xa9gen", data_box(1, b"Pop"))])
        assert read_audio(two_genres).tags.genre == "Rock; Pop"
        write_tags(two_genres, {"genre": None})
        assert not {b"gnre", b"\xa9gen"} & set(m4a_items(two_genres))
        assert read_audio(two_genres).tags.genre is None

        # c) Sin etiquetas (ni 'udta'): se le crean, con lo editado
        bare_m4a = new_m4a("sin_etiquetas.m4a", None, chapters=False)
        assert read_audio(bare_m4a).tag_type == ""
        result = write_tags(bare_m4a, {"title": "Nuevo", "disc": (1, 2)})
        assert result.tags_changed and read_audio(bare_m4a).tag_type == "MP4"
        assert MP4(bare_m4a).tags["disk"] == [(1, 2)] and m4a_audio(bare_m4a)[1] == samples

        # d) Con relleno junto a las etiquetas: el audio no se mueve
        padded = new_m4a("relleno.m4a", m4a_tags, padding=2048)
        size, start = padded.stat().st_size, m4a_audio(padded)[0]
        write_tags(padded, {"title": "Con relleno", "track": None, "album": "Álbum"})
        assert padded.stat().st_size == size and m4a_audio(padded) == (start, samples)
        assert "trkn" not in MP4(padded).tags and MP4(padded).tags["\xa9alb"] == ["Álbum"]

        # e) Lo que no se escribe (el archivo, como estaba): un MP4 fragmentado, un 'meta'
        #    sin etiquetas; y lo que nota la comprobación: si mutagen volviera a escribir
        #    los átomos no editados ('gnre' a ©gen, el tipo de la carátula), o el audio
        fragmented = new_m4a("fragmentado.m4a", m4a_tags)
        with fragmented.open("ab") as file:
            file.write(box(b"moof", box(b"mfhd", bytes(8))))
        content = fragmented.read_bytes()
        expect_error(AudioWriteError, fragmented, {"title": "No"})
        assert fragmented.read_bytes() == content
        no_ilst = new_m4a("meta_sin_ilst.m4a", [])
        content = no_ilst.read_bytes()
        assert content.count(b"\x00\x00\x00\x08ilst") == 1  # el mismo tamaño: nada se mueve
        no_ilst.write_bytes(content.replace(b"\x00\x00\x00\x08ilst", b"\x00\x00\x00\x08free"))
        assert MP4(no_ilst).tags is None
        expect_error(AudioWriteError, no_ilst, {"title": "No"})
        real_keep = mp4_writer._keep_untouched

        def keep_nothing(tags: Any, untouched: list[tuple[str, bytes]], edited: Any) -> None:
            """Sin copiar en bruto lo no editado: mutagen lo vuelve a escribir a su manera."""

        mp4_writer._keep_untouched = keep_nothing
        normalized = root / "normalizada.m4a"
        normalized.write_bytes(original_m4a)
        try:
            expect_error(AudioWriteError, normalized, {"title": "No"})
        finally:
            mp4_writer._keep_untouched = real_keep
        assert normalized.read_bytes() == original_m4a

        def digest_of(m4a_path: Path) -> str:
            """La huella del audio de un M4A, la de su escritor."""
            with m4a_path.open("rb") as file:
                return mp4_writer._audio_digest(Atoms(file), file)

        other_audio = root / "otro_audio.m4a"
        other_audio.write_bytes(original_m4a)
        with other_audio.open("r+b") as file:
            file.seek(before_offset + 500)
            file.write(b"\xee")
        assert digest_of(other_audio) != digest_of(normalized)

        # --- 9. Los saltos de línea del comentario (MUS 7.1c): en el archivo, los de Windows
        #     («\r\n», como Mp3tag); al leerlo, «\n»; lo mismo otra vez no toca el archivo
        write_tags(v24, {"comment": "Una\nDos"})
        assert [f.text for f in raw(v24).getall("COMM") if not f.desc] == [["Una\r\nDos"]]
        write_tags(rich_flac, {"comment": "Una\nDos"})
        assert FLAC(rich_flac).tags["COMMENT"] == ["Una\r\nDos"]
        write_tags(padded, {"comment": "Una\nDos"})
        assert MP4(padded).tags["\xa9cmt"] == ["Una\r\nDos"]
        for song_path in (v24, rich_flac, padded):
            assert read_audio(song_path).tags.comment == "Una\nDos", song_path
            assert not write_tags(song_path, {"comment": "Una\nDos"}).written, song_path

        # Ningún temporal se ha quedado en la carpeta
        leftovers = list(root.glob(f"*{_TEMP_SUFFIX}"))
        assert not leftovers, leftovers

    print("Autoprueba finalizada correctamente.")
