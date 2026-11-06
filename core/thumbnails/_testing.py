"""Utilidades SOLO para las autopruebas de 'core/thumbnails' (no se usan en la aplicación).

Contiene:
    - 'build_rgb_profile' / 'display_p3_profile': fabrican un perfil ICC de verdad (los
      números de Display P3 son los del HEIC del iPhone 17 Pro) para comprobar que la
      conversión a sRGB funciona. Un fallo en esa conversión no daría error: las fotos
      solo se verían apagadas, por eso se prueba con un perfil real.
    - 'FAKE_EXIFTOOL': un ExifTool simulado que devuelve, en el formato JSON con base64
      de '-b', las vistas previas que cada prueba prepare.
    - 'jpeg_bytes': crea un JPEG pequeño en memoria, con orientación EXIF y una marca roja
      en la esquina superior izquierda para saber hacia dónde se ha girado.
"""

__all__ = ["FAKE_EXIFTOOL", "build_rgb_profile", "display_p3_profile", "jpeg_bytes"]

# Librerías estándar
import io
import struct

# Librerías de terceros
from PIL import Image


def _s15(value: float) -> bytes:
    """Número ICC 's15Fixed16' (entero con signo de 32 bits, escala 1/65536)."""
    return struct.pack(">i", round(value * 65536))


def build_rgb_profile(
    description: str,
    white: tuple[float, float, float],
    red: tuple[float, float, float],
    green: tuple[float, float, float],
    blue: tuple[float, float, float],
    gamma: float,
) -> bytes:
    """Construye un perfil ICC v2 de matriz y curva mínimo (colores XYZ ya adaptados a D50)."""

    def xyz(x: float, y: float, z: float) -> bytes:
        return b"XYZ " + bytes(4) + _s15(x) + _s15(y) + _s15(z)

    curve = b"curv" + bytes(4) + struct.pack(">IH", 1, round(gamma * 256))
    text = description.encode("ascii") + b"\0"
    desc = (
        b"desc" + bytes(4) + struct.pack(">I", len(text)) + text
        + struct.pack(">II", 0, 0) + struct.pack(">HB", 0, 0) + bytes(67)
    )  # fmt: skip
    tags = {
        b"desc": desc,
        b"cprt": b"text" + bytes(4) + b"prueba\0",
        b"wtpt": xyz(*white),
        b"rXYZ": xyz(*red),
        b"gXYZ": xyz(*green),
        b"bXYZ": xyz(*blue),
        b"rTRC": curve,
        b"gTRC": curve,
        b"bTRC": curve,
    }
    first_data = 128 + 4 + 12 * len(tags)
    table, body = struct.pack(">I", len(tags)), b""
    for signature, data in tags.items():
        table += signature + struct.pack(">II", first_data + len(body), len(data))
        body += data + bytes((-len(data)) % 4)
    header = (
        struct.pack(">I", first_data + len(body)) + b"lcms" + struct.pack(">I", 0x02400000)
        + b"mntr" + b"RGB " + b"XYZ " + bytes(12) + b"acsp" + bytes(4 * 4) + bytes(8)
        + struct.pack(">I", 0) + _s15(0.9642) + _s15(1.0) + _s15(0.8249) + b"lcms"
        + bytes(16) + bytes(28)
    )  # fmt: skip
    assert len(header) == 128
    return header + table + body


def display_p3_profile() -> bytes:
    """Perfil 'Display P3' con los valores del HEIC de un iPhone 17 Pro (gamma 2,2 simplificada)."""
    return build_rgb_profile(
        "Display P3",
        (0.96419, 1, 0.82489),
        (0.51512, 0.2412, -0.00105),
        (0.29198, 0.69225, 0.04189),
        (0.1571, 0.06657, 0.78407),
        2.2,
    )


def jpeg_bytes(
    size: tuple[int, int],
    *,
    orientation: int | None = None,
    marker: bool = False,
    icc_profile: bytes | None = None,
) -> bytes:
    """Crea un JPEG gris en memoria.

    Args:
        size: (ancho, alto) tal como queda GUARDADO.
        orientation: Código EXIF de orientación a incluir (None = ninguno).
        marker: Si es True, pinta un cuadrado rojo en la esquina superior izquierda.
        icc_profile: Perfil ICC a incrustar.
    """
    image = Image.new("RGB", size, (120, 120, 120))
    if marker:
        side = max(4, min(size) // 5)
        image.paste((255, 0, 0), (0, 0, side, side))
    options: dict = {"quality": 90}
    if orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = orientation
        options["exif"] = exif
    if icc_profile is not None:
        options["icc_profile"] = icc_profile
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", **options)
    return buffer.getvalue()


# ExifTool simulado. Lee de la variable de entorno FAKE_EXIFTOOL_DATA un JSON
# {"nombre_de_archivo": {etiquetas...}}. Los valores "base64:..." solo se entregan si
# la llamada lleva '-b' (como el ExifTool de verdad); sin él devuelve el texto
# "(Binary data N bytes...)", así la prueba falla si el origen olvida pedir '-b'.
FAKE_EXIFTOOL = r'''
import json, os, sys
args = sys.argv[1:]
if "-ver" in args:
    print("13.59"); sys.exit(0)
files = open(args[args.index("-@") + 1], encoding="utf-8").read().splitlines()
if any("explota" in f for f in files):
    sys.stderr.write("caída simulada"); sys.exit(1)
data = json.load(open(os.environ["FAKE_EXIFTOOL_DATA"], encoding="utf-8"))
out = []
for f in files:
    tags = dict(data.get(os.path.basename(f), {}))
    if "-b" not in args:
        tags = {k: (f"(Binary data {len(v)} bytes, use -b option to extract)"
                    if isinstance(v, str) and v.startswith("base64:") else v)
                for k, v in tags.items()}
    out.append({"SourceFile": f.replace("\\", "/"), **tags})
sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
'''
