"""Módulo de definición de rutas y constantes globales del proyecto.

Este módulo centraliza la resolución de rutas de la aplicación de manera
multiplataforma (Windows, macOS y Linux). Gestiona tanto las carpetas de
configuración mutable del usuario como los recursos estáticos y bases de datos
de solo lectura que se distribuyen con el ejecutable.

Es totalmente compatible con entornos de desarrollo local y con ejecutables
empaquetados a través de PyInstaller.
"""

# ruff: noqa: RUF022
__all__ = [
    "APP_NAME",
    "APP_NAME_COMERCIAL",
    "APP_VERSION",
    "ORG_NAME",
    "CONFIG_DIR",
    "CONFIG_FILE",
    "CACHE_DIR",
    "TILE_CACHE_DIR",
    "RESOURCES_DIR",
    "DATA_DIR",
]

# Librerías estándar
import os
import sys
from pathlib import Path

# NOMBRE DEL PROGRAMA
# 'APP_NAME' da nombre a las carpetas de configuración y de logs: cambiarlo deja atrás
# el 'settings.json' y los logs anteriores (se cambió de "emc-manager" a "arca" el
# 05/11/2026, antes de usarse en producción, sin migrar nada)
APP_NAME = "arca"
APP_NAME_COMERCIAL = "Arca Media"
APP_VERSION = "26.11.001"
ORG_NAME = "RT"

# RUTAS DE CONFIGURACIÓN DEL USUARIO (mutables, por SO, en Windows con LOCALAPPDATA
# se usa la carpeta AppData, con APPDATA se usaría la carpeta Roaming)

# Detección automática de la carpeta de configuración según el SO
match sys.platform:
    case "win32":  # Windows
        BASE_CONFIG_DIR = Path(
            # Si no se encuentra, se crea AppData/Local en Path.home()
            os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        )
    case "darwin":  # macOS
        BASE_CONFIG_DIR = Path.home() / "Library" / "Application Support"
    case _:  # Linux / Unix (fallback)
        # Se intenta leer la variable XDG especificada por el sistema o el usuario
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            BASE_CONFIG_DIR = Path(xdg_config)
        else:
            # Si la variable no existe, se usa la ruta por defecto
            BASE_CONFIG_DIR = Path.home() / ".config"

# Se configura la ruta del archivo de configuración del programa
CONFIG_DIR = BASE_CONFIG_DIR / APP_NAME
CONFIG_FILE = CONFIG_DIR / "settings.json"

# Cachés de la aplicación (no de un catálogo): lo que hay aquí se puede borrar y volver a
# descargar. La de las teselas de los mapas es una sola para todos los catálogos
# (docs/DECISIONES.md, 13/11/2026); la usa core/maps/tile_store.py
CACHE_DIR = CONFIG_DIR / "cache"
TILE_CACHE_DIR = CACHE_DIR / "tiles"


# RUTAS DE DATOS DE LA APLICACIÓN (solo lectura, se distribuyen con el programa)

# Lógica de detección para ejecutable distribuido o entorno de desarrollo
if getattr(sys, "frozen", False):
    # Si la app está empaquetada, sys._MEIPASS apunta a la raíz del paquete de 'PyInstaller'
    # donde se habrán copiado las carpetas 'data' y 'resources'
    APP_DIR = Path(sys._MEIPASS)
else:
    # Si se ejecuta en modo desarrollo local, se mantiene la lógica original
    APP_DIR = Path(__file__).resolve().parent.parent

# Carpeta para recursos estáticos (como iconos)
RESOURCES_DIR = APP_DIR / "resources"

# Carpeta para archivos estáticos (como bases de datos)
DATA_DIR = APP_DIR / "data"

# Rutas de archivos: aquí se definen por ejemplo rutas de bases de datos,
# otros recursos estáticos del programa, etc.
