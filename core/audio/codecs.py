"""Los formatos del audio (códecs): la clave que guarda el catálogo y su nombre.

Este módulo NO depende de Qt, de la base de datos ni de mutagen: es una lista, para que la
usen tanto la interfaz como las colecciones inteligentes ('core/' no importa de la
interfaz).

La clave es la de 'audio_details.codec' (la pone 'tag_reader.py'). El nombre es el que ve
el usuario en la fila «Formato» del inspector y en el campo «Formato» de las colecciones
inteligentes y de «Metadatos» (MUS 2.3). Están los formatos que se catalogan
(docs/FORMATOS.md); uno que no esté se enseña con su clave en mayúsculas ('codec_name').

Uso:
    CODEC_NAMES["vorbis"]   # 'Ogg Vorbis'
    codec_name("mp2")       # 'MP2' (uno que no está en la lista)

1.0.0 Primera versión (26/11/2026; MUS 2.3): los nombres, antes en
      'ui_helpers/inspector/formatting.py'.

Prueba rápida (desde la raíz del proyecto):
    python -m core.audio.codecs
"""

__version__ = "1.0.0"
__all__ = ["CODEC_NAMES", "codec_name"]

# Clave de 'audio_details.codec' -> nombre, en el orden de las listas (el del campo
# «Formato» de las colecciones inteligentes)
CODEC_NAMES: dict[str, str] = {
    "mp3": "MP3",
    "flac": "FLAC",
    "aac": "AAC",
    "alac": "ALAC",
    "vorbis": "Ogg Vorbis",
    "opus": "Opus",
}


def codec_name(codec: str) -> str:
    """El nombre de un formato ('vorbis' -> 'Ogg Vorbis'); uno que no esté en la lista, con
    su clave en mayúsculas ('mp2' -> 'MP2'); vacío, ''."""
    key = codec.strip()
    return CODEC_NAMES.get(key.lower(), key.upper())


if __name__ == "__main__":
    # Autoprueba. Ejecutar desde la raíz del proyecto:  python -m core.audio.codecs
    assert codec_name("mp3") == "MP3" and codec_name(" Vorbis ") == "Ogg Vorbis"
    assert codec_name("mp2") == "MP2" and codec_name("  ") == ""
    # Las claves, en minúsculas (como las guarda 'tag_reader.py')
    assert all(key == key.lower() for key in CODEC_NAMES)
    print("Autoprueba finalizada correctamente.")
