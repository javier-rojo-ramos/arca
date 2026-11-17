# Arca Media — iconos de la aplicación

Diseño: cinco capas horizontales en ámbar `#ECA531` sobre fondo `#222222`, con tres
segmentos blancos que marcan los vértices de una «A» (Arca).

## Contenido

```
svg/
  arca-media.svg        Maestro (fondo casi a sangre). Base para Linux.
  arca-media-win.svg    Windows 48–256 px: contenido algo más grande.
  arca-media-mac.svg    macOS: retícula de Apple (cuerpo 824/1024) con sombra.
  arca-media-16.svg     Versión simplificada para 16 px (3 filas, ajustada a píxel).
  arca-media-24.svg     Versión simplificada para 24 px (4 filas, ajustada a píxel).
  arca-media-32.svg     Versión simplificada para 32 px (4 filas, ajustada a píxel).
windows/
  arca-media.ico        16, 24, 32 (versiones simplificadas) + 48, 64, 128, 256.
  png/                  Los mismos tamaños por separado.
macos/
  arca-media.icns       16 a 1024 px, normal y Retina.
  png/                  16, 32, 64, 128, 256, 512 y 1024 px.
linux/
  arca-media-256.png
  arca-media-512.png
preview.png             Hoja de prueba de todos los tamaños.
```

## PyInstaller

PyInstaller no compila para otro sistema: cada ejecutable se genera en su propio sistema.

```bash
# Windows
pyinstaller --windowed --icon windows/arca-media.ico main.py

# macOS (en un Mac)
pyinstaller --windowed --icon macos/arca-media.icns main.py
```

Si usas un `.spec`: en Windows, `EXE(..., icon='windows/arca-media.ico')`;
en macOS, `BUNDLE(..., icon='macos/arca-media.icns')`.

## Icono de la ventana (PySide6)

El icono que se ve en la barra de tareas de Windows es el de la **ventana**, no el
del `.exe`. Para que Qt use la versión adecuada en cada tamaño, carga el `.ico`
completo (en Windows) o añade cada PNG con su tamaño:

```python
import sys
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon


def build_app_icon(icons_dir: Path) -> QIcon:
    """Construye el icono de la aplicación según el sistema operativo.

    En Windows se usa el .ico, que ya contiene las versiones simplificadas
    de 16, 24 y 32 px. En el resto se añaden los PNG uno a uno para que Qt
    elija el más adecuado a cada tamaño.
    """
    if sys.platform == "win32":
        return QIcon(str(icons_dir / "windows" / "arca-media.ico"))

    icon = QIcon()
    png_dir = icons_dir / "macos" / "png" if sys.platform == "darwin" else icons_dir / "linux"
    for png in sorted(png_dir.glob("arca-media-*.png")):
        # El tamaño se toma del nombre del fichero (arca-media-256.png -> 256)
        size = int(png.stem.rsplit("-", 1)[1])
        icon.addFile(str(png), QSize(size, size))
    return icon


# app.setWindowIcon(build_app_icon(ICONS_DIR))
```

Si el acceso directo ya estaba anclado en la barra de tareas de Windows, desáncalo y
vuelve a anclarlo para que se refresque la caché de iconos.

## Linux

El ejecutable no lleva icono incrustado; se asocia mediante un fichero `.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Arca Media
Exec=/opt/arca-media/arca-media
Icon=/opt/arca-media/icons/arca-media-512.png
Categories=Graphics;AudioVideo;Office;
```
