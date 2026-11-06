"""Extractor de metadatos de VÍDEO con ExifTool.

Une las tres piezas propias de los vídeos (como 'core/metadata/image/extractor.py'):
    fields.py    la lista de campos (qué etiqueta va a qué columna)   <- aquí se añaden campos
    rules.py     las reglas especiales (fecha, tamaño con rotación, GPS)
    este módulo  el extractor, que se registra en 'core/metadata/registry.py'

Todo lo demás (lotes, sidecars, aislar archivos problemáticos) lo hace 'ExifToolExtractor'.
ExifTool lee la cabecera de MOV, MP4, M4V, MTS/M2TS, AVI, MKV, WMV... sin recorrer el
vídeo entero, así que es rápido aunque el archivo sea grande.

Datos del usuario (valoración, marca, color): los vídeos no los llevan dentro; viven en
el archivo de carpeta '.arca.json' (ver core/userdata/), así que 'user_fields' queda vacío.

Prueba rápida (con un ExifTool simulado):
    python -m core.metadata.video.extractor
"""

__version__ = "1.0.1"
__all__ = ["VideoExtractor"]

# Librerías estándar
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.metadata.exiftool_extractor import ExifToolExtractor
from core.metadata.field_spec import FieldSpec
from core.metadata.video.fields import VIDEO_FIELDS, VIDEO_FIELDS_VERSION
from core.metadata.video.rules import apply_video_rules


class VideoExtractor(ExifToolExtractor):
    """Lee los metadatos de los vídeos con ExifTool."""

    media_type: ClassVar[MediaType] = MediaType.VIDEO
    version: ClassVar[int] = VIDEO_FIELDS_VERSION
    details_table: ClassVar[str | None] = "video_details"
    fields: ClassVar[tuple[FieldSpec, ...]] = VIDEO_FIELDS

    def apply_rules(
        self,
        tags: Mapping[str, Any],
        common: dict[str, Any],
        details: dict[str, Any],
        path: Path,
    ) -> None:
        """Reglas especiales de vídeo (ver 'rules.py')."""
        apply_video_rules(tags, common, details, path)


if __name__ == "__main__":
    # Autoprueba con un ExifTool SIMULADO que devuelve las etiquetas de un vídeo de iPhone.
    # Ejecutar desde la raíz del proyecto:  python -m core.metadata.video.extractor
    import json
    import os
    import sys
    import tempfile

    from core.metadata.base import ExtractionResult
    from core.metadata.exiftool_runner import ExifToolRunner

    FAKE_EXIFTOOL = r'''
import json, os, sys
args = sys.argv[1:]
if "-ver" in args:
    print("13.59"); sys.exit(0)
files = open(args[args.index("-@") + 1], encoding="utf-8").read().splitlines()
tags = json.load(open(os.environ["FAKE_TAGS"], encoding="utf-8"))
out = [{"SourceFile": f, **tags} for f in files]
sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
'''
    IPHONE_TAGS = {
        "Keys:CreationDate": "2024:06:01 12:00:00+02:00",
        "Keys:Make": "Apple",
        "Keys:Model": "iPhone 15 Pro",
        "QuickTime:Duration": 12.5,
        "Composite:ImageSize": "1920 1080",
        "Composite:Rotation": 90,
        "Composite:GPSLatitude": 43.3,
        "Composite:GPSLongitude": -3.2,
    }
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fake = base / "fake_exiftool.py"
        fake.write_text(FAKE_EXIFTOOL, encoding="utf-8")
        (base / "tags.json").write_text(json.dumps(IPHONE_TAGS), encoding="utf-8")
        os.environ["FAKE_TAGS"] = str(base / "tags.json")
        extractor = VideoExtractor(ExifToolRunner(command=[sys.executable, str(fake)]))

        clips = [base / "IMG_0001.MOV", base / "IMG_0002.MOV"]
        for clip in clips:
            clip.write_bytes(b"x")
        results = extractor.extract_batch(clips)
        assert all(isinstance(result, ExtractionResult) for result in results), results
        result = results[0]
        assert result.common["content_created_at"] == "2024-06-01 12:00:00"
        assert (result.common["width"], result.common["height"]) == (1080, 1920)
        assert result.details["camera_model"] == "iPhone 15 Pro"
        assert result.common["has_xmp_sidecar"] == 0 and result.user_data == {}
        assert extractor.media_type == MediaType.VIDEO and extractor.details_table == "video_details"
    print("Autoprueba finalizada correctamente.")
