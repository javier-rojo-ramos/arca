"""Extractor de metadatos de CANCIONES (MP3, M4A, FLAC, Ogg, Opus, WAV, AIFF...).

Une el lector de audio ('core/audio/tag_reader.py', con mutagen) con el catálogo: decide en
qué columna va cada dato. Se registra en 'core/metadata/registry.py'. No usa ExifTool.

Qué guarda (docs/MOD_MUSICA.md §3; el mapa de campos, en docs/METADATOS.md, «Música»):

    media_items (columnas comunes a todos los tipos)
        title                   título (si no tiene, se conserva el nombre del archivo)
        creator                 artista
        description             comentario
        content_created_at      el año de la etiqueta (o la fecha, si la trae entera)
        content_date_precision  'year', 'month' o 'day'
        content_date_source     la familia de la etiqueta: 'id3', 'vorbis' o 'mp4'
        duration                segundos

    audio_details (tabla propia de las canciones)
        los campos de la canción (álbum, artista del álbum, pista, disco, género,
        compositor), los datos técnicos (códec, tasa de bits, frecuencia, canales, bits,
        tipo de etiqueta) y la carátula (cuántas imágenes hay y, de la carátula, su tipo,
        formato, tamaño, peso y huella)

Fechas (decidido con el autor el 25/11/2026):
    - «2001» se guarda como '2001-01-01 00:00:00' con precisión 'year'; «2001-05», 'month';
      «2001-05-04», con o sin hora, 'day': la hora de una etiqueta no es la de la grabación
      (iTunes pone la medianoche en UTC), así que no se guarda.
    - Sin año, o con uno que no se entiende: SIN fecha. No se usa la del archivo, como en
      las fotos: es cuándo se copió o se convirtió la canción, no el año del disco.

Errores: un formato que mutagen no abre (MKA) es 'UnsupportedFormatError' (se reintenta al
subir 'AUDIO_FIELDS_VERSION'); un archivo dañado, 'MetadataError' (va a la lista de errores).

Un extractor nunca escribe datos del usuario: la valoración, la marca, el color y las
palabras clave de una canción están en el '.arca.json' de su carpeta.

1.0.0 Primera versión (25/11/2026; docs/MOD_MUSICA.md, paso MUS 1.3).

Prueba rápida (desde la raíz del proyecto; crea un catálogo, un MP3 y un FLAC de prueba en
una carpeta temporal):
    python -m core.metadata.audio.extractor
"""

__version__ = "1.0.0"
__all__ = ["AUDIO_FIELDS_VERSION", "AudioExtractor", "parse_tag_date"]

# Librerías estándar
import re
from datetime import date
from pathlib import Path
from typing import Any, ClassVar

# Módulos del proyecto
from core.audio.tag_reader import AudioInfo, AudioReadError, UnsupportedAudioError, read_audio
from core.catalog.media_types import MediaType
from core.metadata.base import (
    ExtractionResult,
    MetadataError,
    MetadataExtractor,
    UnsupportedFormatError,
)

# Versión de los campos de audio. Se guarda en 'media_items.scan_version'. Súbela cada vez
# que el extractor lea campos nuevos o cambie una regla: las canciones se volverán a leer.
AUDIO_FIELDS_VERSION = 1
# Historial:
#   1  primera versión (25/11/2026, MUS 1.3)

# Una fecha de etiqueta: el año y, si los trae, el mes y el día («2001», «2001-05-04T...»)
_DATE_PATTERN = re.compile(r"\s*(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?")
# Un año menor no es un año («0000» es lo que escriben algunos programas sin dato)
_FIRST_YEAR = 1000


class AudioExtractor(MetadataExtractor):
    """Lee las canciones: etiquetas, datos técnicos y carátula (ver el docstring del archivo)."""

    media_type: ClassVar[MediaType] = MediaType.AUDIO
    version: ClassVar[int] = AUDIO_FIELDS_VERSION
    details_table: ClassVar[str | None] = "audio_details"

    def extract(self, path: Path) -> ExtractionResult:
        """Lee una canción. Ver 'MetadataExtractor.extract'.

        Raises:
            FileNotFoundError: Si el archivo ya no existe.
            UnsupportedFormatError: Si mutagen no reconoce el formato.
            MetadataError: Si el archivo está dañado o no se puede leer.
        """
        if not path.is_file():
            raise FileNotFoundError(path)
        try:
            info = read_audio(path)
        except UnsupportedAudioError as error:
            extension = path.suffix.lower() or "(sin extensión)"
            raise UnsupportedFormatError(f"Formato de audio sin soporte todavía: {extension}") from error
        except AudioReadError as error:
            raise MetadataError(str(error)) from error
        return ExtractionResult(common=_common_values(info), details=_detail_values(info))


def parse_tag_date(text: object) -> tuple[str | None, str | None]:
    """La fecha de una etiqueta, para el catálogo: (texto de la base de datos, precisión).

    «2001» -> ('2001-01-01 00:00:00', 'year'); «2001-05-04T08:00:00Z» ->
    ('2001-05-04 00:00:00', 'day'). Un mes o un día imposibles se quedan en el año; lo que
    no empieza por un año, (None, None).
    """
    if text is None:
        return None, None
    match = _DATE_PATTERN.match(str(text))
    if match is None or int(match[1]) < _FIRST_YEAR:
        return None, None
    year = int(match[1])
    month = int(match[2]) if match[2] else None
    day = int(match[3]) if match[3] and month else None
    try:
        date(year, month or 1, day or 1)
    except ValueError:
        month = day = None  # «2001-13»: solo vale el año
    precision = "day" if day else "month" if month else "year"
    return f"{year:04d}-{month or 1:02d}-{day or 1:02d} 00:00:00", precision


# -----------------------------------------------------------------------------
# De lo leído a las columnas
# -----------------------------------------------------------------------------


def _common_values(info: AudioInfo) -> dict[str, Any]:
    """Columnas de 'media_items' (comunes a todos los tipos de medio)."""
    tags = info.tags
    date_text, precision = parse_tag_date(tags.date)
    return {
        # None en 'title' conserva el nombre del archivo: el procesador nunca lo vacía
        "title": tags.title,
        "creator": tags.artist,
        "description": tags.comment,
        "content_created_at": date_text,
        "content_date_precision": precision,
        "content_date_source": info.tag_family if date_text else None,
        "timezone_offset": None,
        "duration": info.technical.duration,
    }


def _detail_values(info: AudioInfo) -> dict[str, Any]:
    """Columnas de 'audio_details' (propias de las canciones)."""
    tags = info.tags
    technical = info.technical
    cover = info.cover
    return {
        # Campos de la canción
        "album": tags.album,
        "album_artist": tags.album_artist,
        "track_number": tags.track_number,
        "track_total": tags.track_total,
        "disc_number": tags.disc_number,
        "disc_total": tags.disc_total,
        "genre": tags.genre,
        "composer": tags.composer,
        # Datos técnicos
        "codec": technical.codec,
        "codec_detail": technical.codec_detail,
        "bitrate": technical.bitrate,
        "bitrate_mode": technical.bitrate_mode,
        "sample_rate": technical.sample_rate,
        "channels": technical.channels,
        "bit_depth": technical.bit_depth,
        "lossless": 1 if technical.lossless else 0,
        "tag_type": info.tag_type or None,
        # La carátula (las demás imágenes no se guardan: se leen cuando hacen falta)
        "picture_count": len(info.pictures),
        "cover_type": cover.type_key if cover else None,
        "cover_mime": cover.mime if cover else None,
        "cover_width": cover.width if cover else None,
        "cover_height": cover.height if cover else None,
        "cover_bytes": cover.size_bytes if cover else None,
        "cover_hash": cover.digest if cover else None,
    }


if __name__ == "__main__":
    # Autoprueba: las fechas, de lo leído a las columnas, y de punta a punta con un catálogo
    # de prueba (un MP3 y un FLAC mínimos, leídos por el procesador). Desde la raíz:
    #     python -m core.metadata.audio.extractor
    import io
    import sqlite3
    import struct
    import tempfile
    from contextlib import closing

    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import APIC, COMM, ID3, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK
    from PIL import Image

    from core.audio.tag_reader import (
        FRONT_COVER,
        ID3_FAMILY,
        AudioPicture,
        AudioTags,
        AudioTechnical,
        picture_digest,
    )
    from core.catalog.catalog_builder import CatalogBuilder
    from core.catalog.catalog_schema import configure_connection
    from core.catalog.folder_importer import add_folder
    from core.metadata.processor import process_pending_metadata
    from core.metadata.registry import ExtractorRegistry

    # --- Fechas
    for text, expected in (
        ("2001", ("2001-01-01 00:00:00", "year")),
        (" 2001 ", ("2001-01-01 00:00:00", "year")),
        ("2001-05", ("2001-05-01 00:00:00", "month")),
        ("2001-05-04", ("2001-05-04 00:00:00", "day")),
        ("2001-01-01T08:00:00Z", ("2001-01-01 00:00:00", "day")),  # iTunes: sin la hora
        ("2001-13-40", ("2001-01-01 00:00:00", "year")),  # mes imposible: el año
        ("2001-02-30", ("2001-01-01 00:00:00", "year")),
        ("0000", (None, None)), ("c. 1999", (None, None)), ("", (None, None)), (None, (None, None)),
    ):  # fmt: skip
        assert parse_tag_date(text) == expected, (text, parse_tag_date(text))

    # --- De lo leído a las columnas (sin archivo)
    cover = AudioPicture(FRONT_COVER, "image/jpeg", 600, 600, 25_000, digest="ab" * 16)
    info = AudioInfo(
        tags=AudioTags(
            title="Vino Tinto", artist="Estopa", album="Destrangis", date="2001",
            track_number=1, track_total=13, genre="Pop Folk", comment="Primer disco",
        ),
        technical=AudioTechnical(
            codec="aac", codec_detail="AAC LC", duration=198.6, bitrate=118419,
            sample_rate=44100, channels=2,
        ),
        tag_type="MP4", tag_family="mp4",
        pictures=(AudioPicture("cover_back", "image/png", 10, 10, 99), cover),
    )  # fmt: skip
    common = _common_values(info)
    assert common == {
        "title": "Vino Tinto", "creator": "Estopa", "description": "Primer disco",
        "content_created_at": "2001-01-01 00:00:00", "content_date_precision": "year",
        "content_date_source": "mp4", "timezone_offset": None, "duration": 198.6,
    }, common  # fmt: skip
    details = _detail_values(info)
    assert (details["album"], details["track_number"], details["track_total"]) == ("Destrangis", 1, 13)
    assert (details["codec"], details["codec_detail"], details["lossless"]) == ("aac", "AAC LC", 0)
    assert details["picture_count"] == 2 and details["cover_type"] == FRONT_COVER  # la portada
    assert (details["cover_width"], details["cover_bytes"], details["cover_hash"]) == (600, 25_000, "ab" * 16)
    # Sin fecha, sin origen; sin imágenes, la carátula vacía
    bare = AudioInfo(AudioTags(), AudioTechnical(), tag_family="id3")
    assert _common_values(bare)["content_date_source"] is None
    assert _detail_values(bare)["picture_count"] == 0 and _detail_values(bare)["cover_hash"] is None

    # --- De punta a punta: un catálogo, una carpeta con un MP3 y un FLAC, el procesador
    def image_bytes() -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", (30, 20), "blue").save(buffer, "JPEG")
        return buffer.getvalue()

    JPEG = image_bytes()
    registry = ExtractorRegistry()
    registry.register(AudioExtractor())

    with tempfile.TemporaryDirectory(prefix="arca_audio_") as folder:
        base = Path(folder)
        music = base / "Música"
        music.mkdir()

        # Un MP3 de 40 tramas de silencio (MPEG-1 Layer III, 128 kbps, 44,1 kHz), con ID3v2.3
        mp3 = music / "01 - Rehab.mp3"
        mp3.write_bytes((b"\xff\xfb\x90\x00" + bytes(413)) * 40)
        id3 = ID3()
        id3.add(TIT2(encoding=1, text=["Rehab"]))
        id3.add(TPE1(encoding=1, text=["Amy Winehouse"]))
        id3.add(TPE2(encoding=1, text=["Amy Winehouse"]))
        id3.add(TALB(encoding=1, text=["Back To Black"]))
        id3.add(TDRC(encoding=1, text=["2006"]))
        id3.add(TRCK(encoding=1, text=["01/11"]))
        id3.add(TCON(encoding=1, text=["Soul"]))
        id3.add(COMM(encoding=1, lang="eng", desc="", text=["Primera"]))
        id3.add(APIC(encoding=1, mime="image/jpeg", type=3, desc="", data=JPEG))
        id3.save(mp3, v2_version=3)

        # Un FLAC con solo su STREAMINFO (2 s, 44,1 kHz, estéreo, 16 bits), sin año
        streaminfo = struct.pack(">HH", 4096, 4096) + bytes(6)
        streaminfo += ((44100 << 44) | (1 << 41) | (15 << 36) | 88200).to_bytes(8, "big") + bytes(16)
        flac_path = music / "02 - Misirlou.flac"
        flac_path.write_bytes(b"fLaC\x80" + len(streaminfo).to_bytes(3, "big") + streaminfo)
        flac = FLAC(flac_path)
        flac.add_tags()
        flac["ARTIST"] = "Dick Dale"
        flac["GENRE"] = ["BSO", "Surf"]
        picture = Picture()
        picture.type, picture.mime, picture.data = 4, "image/jpeg", JPEG
        flac.add_picture(picture)
        flac.save()

        db_path = CatalogBuilder(base / "Cat").build()
        with closing(sqlite3.connect(db_path)) as conn:
            configure_connection(conn)
            add_folder(conn, music)
            assert process_pending_metadata(conn, registry=registry).processed == 2

            def row(name: str) -> sqlite3.Row:
                conn.row_factory = sqlite3.Row
                return conn.execute(
                    "SELECT m.*, d.* FROM media_items AS m JOIN audio_details AS d "
                    "ON d.media_id = m.id WHERE m.file_name = ?", (name,),
                ).fetchone()  # fmt: skip

            song = row("01 - Rehab.mp3")
            assert (song["title"], song["creator"], song["description"]) == (
                "Rehab", "Amy Winehouse", "Primera")  # fmt: skip
            assert (song["content_created_at"], song["content_date_precision"]) == (
                "2006-01-01 00:00:00", "year")  # fmt: skip
            assert song["content_date_source"] == ID3_FAMILY and song["scan_version"] == 1
            assert (song["album"], song["album_artist"], song["genre"]) == (
                "Back To Black", "Amy Winehouse", "Soul")  # fmt: skip
            assert (song["track_number"], song["track_total"], song["disc_number"]) == (1, 11, None)
            assert (song["codec"], song["bitrate"], song["sample_rate"], song["channels"]) == (
                "mp3", 128000, 44100, 2)  # fmt: skip
            assert song["tag_type"] == "ID3v2.3" and song["lossless"] == 0
            assert (song["picture_count"], song["cover_type"], song["cover_width"]) == (1, FRONT_COVER, 30)
            assert song["cover_hash"] == picture_digest(JPEG) and song["duration"] > 0.9

            other = row("02 - Misirlou.flac")
            # Sin título, el nombre del archivo; sin año, sin fecha (no la del archivo)
            assert other["title"] == "02 - Misirlou" and other["creator"] == "Dick Dale"
            assert other["content_created_at"] is None and other["content_date_source"] is None
            assert other["genre"] == "BSO; Surf" and other["duration"] == 2.0
            assert (other["codec"], other["lossless"], other["bit_depth"]) == ("flac", 1, 16)
            # La única imagen es una contraportada: es la carátula
            assert (other["picture_count"], other["cover_type"]) == (1, "cover_back")
            assert other["cover_hash"] == song["cover_hash"]  # la misma imagen, la misma huella
            print("De punta a punta: 2 canciones leídas y guardadas")

        # --- Lo que no se puede leer
        unknown = base / "pista.mka"
        unknown.write_bytes(b"\x1a\x45\xdf\xa3" + bytes(60))
        damaged = base / "rota.flac"
        damaged.write_bytes(b"fLaC\x00\x00")
        for bad, error_type in (
            (unknown, UnsupportedFormatError),
            (damaged, MetadataError),
            (base / "no_existe.mp3", FileNotFoundError),
        ):
            try:
                AudioExtractor().extract(bad)
                raise AssertionError(f"debía fallar: {bad.name}")
            except error_type:
                pass
            except Exception as error:
                raise AssertionError(f"{bad.name}: {type(error).__name__}") from error

    print("Autoprueba finalizada correctamente.")
