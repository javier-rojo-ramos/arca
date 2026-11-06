import shutil
from pathlib import Path

from qtpy.QtCore import QLibraryInfo

# 1. Crear el directorio de destino
destino_dir = Path("resources/locales")
destino_dir.mkdir(parents=True, exist_ok=True)

# 2. Obtener la ruta del archivo traducido desde la librería instalada
dir_traducciones = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
archivo_origen = dir_traducciones / "qtbase_es.qm"

# 3. Copiar el archivo
if archivo_origen.exists():
    shutil.copy(archivo_origen, destino_dir / "qtbase_es.qm")
    print(f"✅ Archivo copiado con éxito a: {destino_dir / 'qtbase_es.qm'}")
else:
    print(f"❌ No se encontró 'qtbase_es.qm' en: {dir_traducciones}")
