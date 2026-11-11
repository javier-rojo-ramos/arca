"""Extractor de metadatos de IMÁGENES con ExifTool.

Es la pieza que une las tres cosas propias de las imágenes:

    fields.py    la lista de campos (qué etiqueta va a qué columna)   <- aquí se añaden campos
    rules.py     las reglas especiales (fecha, tamaño, flash, GPS)
    este módulo  el extractor, que se registra en 'core/metadata/registry.py'

Todo lo demás (leer por lotes, sidecars, aislar archivos problemáticos) lo hace
'ExifToolExtractor', común a todos los tipos de medio. Funciona con cualquier formato
que ExifTool entienda: JPEG, PNG, WebP, TIFF, HEIC y los RAW (DNG, NEF, CR2, CR3, ARW,
ORF, RW2, PEF, RAF...).

Prueba rápida (usa datos REALES de ExifTool y un ExifTool simulado):
    python -m core.metadata.image.extractor

1.0.3 Autoprueba: GPS con el XMP primero, con los casos comprobados en Lightroom.
1.0.2 Autoprueba: la dirección de la cámara está en 'media_items' (migración 3).
"""

__version__ = "1.0.3"
__all__ = ["ImageExtractor"]

# Librerías estándar
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.metadata.exiftool_extractor import ExifToolExtractor
from core.metadata.field_spec import FieldSpec
from core.metadata.image.fields import IMAGE_FIELDS, IMAGE_FIELDS_VERSION, IMAGE_USER_FIELDS
from core.metadata.image.rules import apply_image_rules


class ImageExtractor(ExifToolExtractor):
    """Lee los metadatos de las imágenes (fotos) con ExifTool."""

    media_type: ClassVar[MediaType] = MediaType.PHOTO
    version: ClassVar[int] = IMAGE_FIELDS_VERSION
    details_table: ClassVar[str | None] = "photo_details"
    fields: ClassVar[tuple[FieldSpec, ...]] = IMAGE_FIELDS
    user_fields: ClassVar[tuple[FieldSpec, ...]] = IMAGE_USER_FIELDS
    reads_keywords: ClassVar[bool] = True  # 'XMP-lr:HierarchicalSubject', 'dc:Subject'...

    def apply_rules(
        self,
        tags: Mapping[str, Any],
        common: dict[str, Any],
        details: dict[str, Any],
        path: Path,
    ) -> None:
        """Reglas especiales de imagen (ver 'rules.py')."""
        apply_image_rules(tags, common, details, path)


if __name__ == "__main__":
    # Autoprueba: (1) los datos REALES de ExifTool de un JPEG de iPhone exportado desde
    # Lightroom deben dar los mismos valores que muestra Lightroom; (2) las reglas
    # especiales con casos inventados.
    # Ejecutar desde la raíz del proyecto:  python -m core.metadata.image.extractor
    import json
    import os
    import sys
    import tempfile

    from core.metadata.exiftool_runner import ExifToolRunner
    from core.metadata.image._fixtures import REAL_JPEG_TAGS

    FAKE_EXIFTOOL = r'''
import json, os, sys
args = sys.argv[1:]
if "-ver" in args:
    print("13.59"); sys.exit(0)
files = open(args[args.index("-@") + 1], encoding="utf-8").read().splitlines()
tags = json.load(open(os.environ["FAKE_TAGS"], encoding="utf-8"))
sidecar_tags = json.load(open(os.environ["FAKE_SIDECAR_TAGS"], encoding="utf-8"))
out = [{"SourceFile": f, **(sidecar_tags if f.endswith(".xmp") else tags)} for f in files]
sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
'''

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fake = base / "fake_exiftool.py"
        fake.write_text(FAKE_EXIFTOOL, encoding="utf-8")
        (base / "tags.json").write_text(json.dumps(REAL_JPEG_TAGS), encoding="utf-8")
        (base / "sidecar.json").write_text(json.dumps({}), encoding="utf-8")
        os.environ["FAKE_TAGS"] = str(base / "tags.json")
        os.environ["FAKE_SIDECAR_TAGS"] = str(base / "sidecar.json")
        extractor = ImageExtractor(ExifToolRunner(command=[sys.executable, str(fake)]))

        photo = base / "IMG_5625-2.jpg"
        photo.write_bytes(b"x")

        # ---------- 1. Datos reales: lo que se ve en los paneles de Lightroom ----------
        result = extractor.extract(photo)
        common, details = result.common, result.details
        print("media_items :", {k: v for k, v in common.items() if v is not None})
        print("photo_details:", {k: v for k, v in details.items() if v is not None})

        # Panel "Ubicación"
        assert common["sublocation"] == "Paseo" and common["city"] == "Castro Urdiales"
        assert common["region"] == "Cantabria" and common["country"] == "España"
        assert common["country_code"] is None  # Lightroom lo muestra vacío
        assert common["title"] is None and common["description"] is None  # "Título" y "Pie" vacíos
        assert common["iptc_created_at"] == "2026-08-27 21:33:57"  # "Fecha de creación"
        assert (common["latitude"], common["longitude"], common["altitude"]) == (43.5, -3.25, 3.0)
        assert abs(common["gps_direction"] - 338.0218353) < 1e-9  # "Dirección": Norte
        assert "gps_direction" not in details
        # Panel "EXIF"
        assert (details["camera_make"], details["camera_model"]) == ("Apple", "iPhone 17 Pro")
        assert details["lens_model"] == "iPhone 17 Pro back triple camera 16.891mm f/2.8"
        assert details["exposure_time_s"] == 0.2 and details["f_number"] == 2.8  # "1/5 seg. en f/2,8"
        assert details["focal_length_mm"] == 16.890625 and details["focal_length_35mm"] == 200.0
        assert details["iso"] == 1000 and details["exposure_bias_ev"] == -0.2734375
        assert abs(details["brightness_value"] - (-3.571474374)) < 1e-9
        assert details["exposure_program"] == 2 and details["metering_mode"] == 5  # Normal, Matricial
        assert details["flash_code"] == 16 and details["flash_fired"] == 0  # "No disparado"
        assert details["software"] == "Adobe Photoshop Lightroom Classic 15.5.1 (Windows)"
        assert details["body_serial_number"] is None and details["user_comment"] is None
        assert common["creator"] is None and common["copyright"] == "Ana Autora"
        assert details["digitized_at"] == "2026-08-27 21:33:57"
        assert details["exif_modified_at"] == "2026-09-03 20:23:56"
        # Fecha de captura, con su zona horaria y origen
        assert common["content_created_at"] == "2026-08-27 21:33:57"
        assert common["timezone_offset"] == "+02:00" and common["content_date_source"] == "exif"
        assert common["content_date_precision"] == "second"
        # Tamaño y sidecar
        assert (common["width"], common["height"], common["orientation"]) == (4032, 2688, 1)
        assert common["has_xmp_sidecar"] == 0
        print("Datos reales: todos los campos coinciden con los paneles de Lightroom")

        # ---------- 2. Con sidecar: su XMP manda sobre el incrustado ----------
        (base / "IMG_5625-2.xmp").write_text("<x/>")
        (base / "sidecar.json").write_text(
            json.dumps({"XMP-photoshop:City": "Bilbao", "XMP-dc:Title": "Atardecer"}), encoding="utf-8"
        )
        with_sidecar = extractor.extract(photo)
        assert with_sidecar.common["city"] == "Bilbao" and with_sidecar.common["title"] == "Atardecer"
        assert with_sidecar.common["region"] == "Cantabria"  # lo no cambiado por el sidecar sigue igual
        assert with_sidecar.common["has_xmp_sidecar"] == 1
        print("Sidecar: ciudad y título del sidecar; el resto, del archivo")

        # ---------- 3. Reglas especiales con casos inventados ----------
        def run_rules(tags: dict, name: str = "x.jpg") -> tuple[dict, dict]:
            """Aplica solo la lista de campos y las reglas a unas etiquetas inventadas."""
            from core.metadata.field_spec import read_field

            common_values: dict = {}
            details_values: dict = {}
            for spec in IMAGE_FIELDS:
                (common_values if spec.target == "common" else details_values)[spec.column] = read_field(spec, tags)
            target = base / name
            target.write_bytes(b"x")
            os.utime(target, (1_700_000_000, 1_700_000_000))
            apply_image_rules(tags, common_values, details_values, target)
            return common_values, details_values

        # Imagen girada 90° (orientación 6): ancho y alto se intercambian
        rotated, _ = run_rules({"Composite:ImageSize": "4000 3000", "IFD0:Orientation": 6})
        assert (rotated["width"], rotated["height"], rotated["orientation"]) == (3000, 4000, 6)
        # Sin orientación: normal (1), sin intercambio
        straight, _ = run_rules({"Composite:ImageSize": "4000 3000"})
        assert (straight["width"], straight["height"], straight["orientation"]) == (4000, 3000, 1)
        # Alternativas para el tamaño cuando no hay Composite:ImageSize
        fallback, _ = run_rules({"File:ImageWidth": 640, "File:ImageHeight": 480})
        assert (fallback["width"], fallback["height"]) == (640, 480)

        # Fecha: EXIF original con la zona horaria de otra etiqueta
        dated, _ = run_rules(
            {"ExifIFD:DateTimeOriginal": "2026:01:02 03:04:05", "ExifIFD:OffsetTimeOriginal": "-05:00"}
        )
        assert dated["content_created_at"] == "2026-01-02 03:04:05" and dated["timezone_offset"] == "-05:00"
        # Fecha vacía de la cámara: se salta a la siguiente fuente (XMP, con zona en la propia fecha)
        skipped, _ = run_rules(
            {
                "ExifIFD:DateTimeOriginal": "0000:00:00 00:00:00",
                "XMP-photoshop:DateCreated": "2025:12:31 23:59:58.500+01:00",
            }
        )
        assert skipped["content_created_at"] == "2025-12-31 23:59:58"
        assert skipped["content_date_source"] == "xmp" and skipped["timezone_offset"] == "+01:00"
        # Solo fecha (sin hora): precisión 'day'
        only_day, _ = run_rules({"Composite:DateTimeCreated": "2024:07:09"})
        assert only_day["content_date_precision"] == "day" and only_day["content_date_source"] == "iptc"
        # Sin ninguna fecha: la de modificación del archivo
        by_file, _ = run_rules({}, name="sin_fecha.png")
        assert by_file["content_date_source"] == "file_mtime" and by_file["content_created_at"].startswith("2023-11-1")

        # Flash: código 9 (disparado, modo obligatorio) -> 1; sin código -> sin dato
        _, flash = run_rules({"ExifIFD:Flash": 9})
        assert flash["flash_fired"] == 1 and flash["flash_code"] == 9
        assert run_rules({})[1]["flash_fired"] is None

        # GPS imposible o (0, 0): se descarta; hemisferio sur y oeste con signo
        for bad in ({"Composite:GPSLatitude": 95.0, "Composite:GPSLongitude": 10.0},
                    {"Composite:GPSLatitude": 0.0, "Composite:GPSLongitude": 0.0},
                    {"Composite:GPSLatitude": 40.0}):
            no_gps, _ = run_rules(bad)
            assert no_gps["latitude"] is None and no_gps["longitude"] is None
        south, _ = run_rules({"Composite:GPSLatitude": -33.5, "Composite:GPSLongitude": -70.6, "Composite:GPSAltitude": -10})
        assert (south["latitude"], south["longitude"], south["altitude"]) == (-33.5, -70.6, -10.0)

        # GPS con el XMP primero (casos comprobados con Lightroom Classic 16 el 11/11/2026)
        exif = {"Composite:GPSLatitude": 40.4168, "Composite:GPSLongitude": -3.7038,
                "Composite:GPSAltitude": 650, "GPS:GPSAltitude": 650, "GPS:GPSImgDirection": 90}
        xmp = {"XMP-exif:GPSLatitude": 41.3874, "XMP-exif:GPSLongitude": 2.1686,
               "XMP-exif:GPSAltitude": 12, "XMP-exif:GPSAltitudeRef": 0,
               "XMP-exif:GPSImgDirection": 180}  # fmt: skip
        # EXIF y XMP distintos: manda el XMP, como en Lightroom (Barcelona, 12 m, Sur)
        both, _ = run_rules({**exif, **xmp})
        assert (both["latitude"], both["longitude"], both["altitude"], both["gps_direction"]) == (
            41.3874, 2.1686, 12.0, 180.0
        )
        # Solo el EXIF (una foto del móvil): como hasta ahora
        only_exif, _ = run_rules(exif)
        assert (only_exif["latitude"], only_exif["altitude"], only_exif["gps_direction"]) == (
            40.4168, 650.0, 90.0
        )
        # Altitud del XMP bajo el nivel del mar (referencia 1, también como texto) y sin
        # referencia (Lightroom no la escribe): sobre el nivel del mar
        for ref, expected in ((1, -430.0), ("1", -430.0), (0, 430.0), (None, 430.0)):
            sea, _ = run_rules({"XMP-exif:GPSLatitude": 31.559, "XMP-exif:GPSLongitude": 35.4732,
                                "XMP-exif:GPSAltitude": 430, "XMP-exif:GPSAltitudeRef": ref})
            assert sea["altitude"] == expected, (ref, sea["altitude"])
        # EXIF sin 'GPSAltitudeRef' (Lightroom la borra): sin compuesto, la de 'GPS:GPSAltitude'
        no_ref, _ = run_rules({"Composite:GPSLatitude": 41.3874, "Composite:GPSLongitude": 2.1686,
                               "GPS:GPSAltitude": 100})
        assert no_ref["altitude"] == 100.0
        # Sidecar de un NEF guardado por Lightroom: fracciones y sin referencias
        nef, _ = run_rules({**exif, "XMP-exif:GPSLatitude": 41.3874, "XMP-exif:GPSLongitude": 2.1686,
                            "XMP-exif:GPSAltitude": "1000000/10000", "XMP-exif:GPSImgDirection": "0/10000"})
        assert (nef["latitude"], nef["altitude"], nef["gps_direction"]) == (41.3874, 100.0, 0.0)
        # El XMP con una sola coordenada: la pareja entera sale del EXIF (nunca mezcladas)
        half, _ = run_rules({**exif, "XMP-exif:GPSLatitude": 41.3874})
        assert (half["latitude"], half["longitude"]) == (40.4168, -3.7038)
        # Un XMP imposible no se arregla con el EXIF: se descarta (es el que manda)
        bad_xmp, _ = run_rules({**exif, "XMP-exif:GPSLatitude": 95.0, "XMP-exif:GPSLongitude": 2.0})
        assert bad_xmp["latitude"] is None and bad_xmp["longitude"] is None
        print("Reglas especiales: orientación, fecha, flash y GPS correctos (XMP primero)")

        # Recorte de Lightroom, con los datos REALES de dos archivos del autor y las
        # «Dimensiones actuales» que muestra Lightroom Classic 15.6 para cada uno
        dng = {"SubIFD:DefaultCropSize": "3200 2128", "XMP-crs:HasCrop": True,
               "XMP-crs:CropTop": 0.003533, "XMP-crs:CropLeft": 0.004774,
               "XMP-crs:CropBottom": 0.901138, "XMP-crs:CropRight": 0.900135,
               "XMP-crs:CropAngle": 0, "XMP-crs:AlreadyApplied": False}
        _, cropped = run_rules(dng)
        assert (cropped["crop_width"], cropped["crop_height"]) == (2865, 1910), cropped
        jpg = {"File:ImageWidth": 4051, "File:ImageHeight": 2700, "XMP-crs:HasCrop": True,
               "XMP-crs:CropTop": 0.099223, "XMP-crs:CropLeft": 0.011913,
               "XMP-crs:CropBottom": 0.900777, "XMP-crs:CropRight": 0.956555,
               "XMP-crs:CropAngle": -4.2, "XMP-crs:AlreadyApplied": False}
        _, cropped = run_rules(jpg)
        assert (cropped["crop_width"], cropped["crop_height"]) == (3658, 2439), cropped
        # Girada 90° (orientación 6): el recorte también se gira
        rotated_crop, cropped = run_rules({**dng, "IFD0:Orientation": 6})
        assert (rotated_crop["width"], cropped["crop_width"], cropped["crop_height"]) == (2128, 1910, 2865)
        # Sin recorte, con 'HasCrop' falso o con el recorte ya aplicado: sin dato
        for no_crop in ({"File:ImageWidth": 4051, "File:ImageHeight": 2700},
                        {**jpg, "XMP-crs:HasCrop": False}, {**jpg, "XMP-crs:HasCrop": "False"},
                        {**jpg, "XMP-crs:AlreadyApplied": True}, {**jpg, "XMP-crs:CropTop": "x"}):
            _, cropped = run_rules(no_crop)
            assert cropped["crop_width"] is None and cropped["crop_height"] is None, no_crop
        print("Recorte de Lightroom: 2865 × 1910 (DNG) y 3658 × 2439 (JPG enderezado), como Lightroom")

    print("Autoprueba finalizada correctamente.")
