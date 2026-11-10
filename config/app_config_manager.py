"""Gestor de configuración basado en JSON (Thread-Safe).

Este módulo proporciona la clase 'ConfigManager', encargada de inicializar,
cargar, guardar y mantener la configuración de la aplicación en un archivo JSON.

En DEFAULTS se establecen las variables que se guardarán en el archivo JSON.

1.12 Se añade 'confirm_multi_edit' (aviso «Edición múltiple» del inspector).
1.11 Se añade 'filter_presets' (ajustes personalizados de la barra de filtros).
1.10 Se añade 'filter_metadata_height' (alto del panel «Metadatos» de la barra de filtros).
1.09 Se añade 'last_add_folder_parent' (dónde se abre «Añadir carpeta»).
1.08 Se añade 'active_module' (módulo activo al cerrar la aplicación).
1.07 Se añade 'inspector_sections' (secciones del inspector plegadas o desplegadas).
1.06 Se añade 'sidebar_state' (lo desplegado en la barra lateral, por catálogo).
1.05 Se añade 'show_subfolder_items' (carpetas con o sin sus subcarpetas).
1.04 Se añade 'main_splitter_state' (anchos de las barras laterales).
1.03 Se implementa 'threading.RLock' para garantizar la seguridad en entornos multihilo,
      previniendo colisiones de memoria al leer o escribir simultáneamente.
1.02 Se utiliza la librería estándar 'copy' para realizar copias profundas (copy.deepcopy()).
1.01 Se modifica el método 'set' para evitar restauraciones parciales.
"""

__version__ = "1.12"
__all__ = ["ConfigManager"]

# Librerías estándar
import copy
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, ClassVar

# Módulos del proyecto
from config.app_constants import (
    SETTING_ACTIVE_MODULE,
    SETTING_CONFIRM_MULTI_EDIT,
    SETTING_FILTER_METADATA_HEIGHT,
    SETTING_FILTER_PRESETS,
    SETTING_INSPECTOR_METADATA_PRESET,
    SETTING_INSPECTOR_SECTIONS,
    SETTING_LAST_ADD_FOLDER_PARENT,
    SETTING_MAIN_SPLITTER_STATE,
    SETTING_SHOW_SUBFOLDER_ITEMS,
    SETTING_SIDEBAR_STATE,
    SETTING_WRITE_USER_DATA_TO_FILES,
    THUMBNAIL_SIZE_DEFAULT,
)
from config.app_paths import CONFIG_DIR, CONFIG_FILE

logger = logging.getLogger(__name__)


class ConfigManager:
    """Maneja la persistencia y recuperación de los ajustes de forma segura para hilos."""

    # El uso de "ClassVar[dict[str, Any]] = " permite indicarle explícitamente
    # al analizador estático (ej: Pylance) que se trata de una variable de clase
    DEFAULTS: ClassVar[dict[str, Any]] = {
        "window_geometry": None,  # Guardará posición y tamaño en formato Hexadecimal
        # Anchos de las barras laterales y de la zona central ('splitter_main'), en
        # hexadecimal como 'window_geometry'. None = anchos por defecto
        SETTING_MAIN_SPLITTER_STATE: None,
        "catalogo_ruta": "",  # Ruta absoluta del catálogo multimedia activo
        "thumbnail_size": THUMBNAIL_SIZE_DEFAULT,  # Tamaño de miniaturas (slider_thumbnails)
        # Escribir valoración, marca y color en los archivos (Opciones > Metadatos)
        SETTING_WRITE_USER_DATA_TO_FILES: True,
        # Preguntar antes de poner el mismo metadato a varios archivos que lo tienen distinto
        # (aviso «Edición múltiple»; Opciones > Metadatos)
        SETTING_CONFIRM_MULTI_EDIT: True,
        # Al elegir una carpeta, mostrar también sus subcarpetas (Opciones > Catálogo)
        SETTING_SHOW_SUBFOLDER_ITEMS: True,
        # Lo desplegado en la barra lateral, por catálogo (ver CatalogSidebar.save_state)
        SETTING_SIDEBAR_STATE: {},
        # Vista de la sección «Metadatos» del inspector (desplegable de su cabecera)
        SETTING_INSPECTOR_METADATA_PRESET: "default",
        # Secciones del inspector plegadas o desplegadas ({clave: True/False}; las que no
        # aparecen, desplegadas)
        SETTING_INSPECTOR_SECTIONS: {},
        # Módulo activo al cerrar (se vuelve a él al arrancar)
        SETTING_ACTIVE_MODULE: "catalog",
        # Carpeta que contiene la última carpeta añadida: ahí se abre «Añadir carpeta»
        # ("" = la carpeta personal)
        SETTING_LAST_ADD_FOLDER_PARENT: "",
        # Alto del panel «Metadatos» de la barra de filtros (None = el de partida)
        SETTING_FILTER_METADATA_HEIGHT: None,
        # Ajustes personalizados de la barra de filtros (None = los de fábrica)
        SETTING_FILTER_PRESETS: None,
        # Aquí se añaden nuevas variables
    }

    def __init__(self) -> None:
        # RLock (Reentrant Lock) permite que el mismo hilo adquiera el cerrojo varias veces.
        # Esto previene bloqueos internos si un método de esta clase llama a otro.
        self._lock = threading.RLock()

        with self._lock:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            self.data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        """Carga el JSON y aplica mecanismos de seguridad y fusión de forma segura."""
        with self._lock:
            if not CONFIG_FILE.exists():
                self._save(self.DEFAULTS)
                return copy.deepcopy(self.DEFAULTS)

            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()

            # Si el archivo está vacío, se repara guardando el estado por defecto
            if not content:
                logger.warning(
                    "Archivo de configuración vacío. Restableciendo valores por defecto."
                )
                self._save(self.DEFAULTS)
                return copy.deepcopy(self.DEFAULTS)

            try:
                loaded = json.loads(content)
                if not isinstance(loaded, dict):
                    logger.error(
                        "El JSON no contiene un diccionario válido. Restableciendo configuración."
                    )
                    loaded = {}

                # Fusión inteligente asegurando aislamiento de memoria
                merged = copy.deepcopy(self.DEFAULTS)
                merged.update(loaded)

                if merged != loaded:
                    self._save(merged)
                return merged

            except json.JSONDecodeError as e:
                logger.error(f"Archivo de configuración corrupto detectado: {e}")

                # Intento de respaldo del archivo corrupto
                try:
                    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    corrupt_path = CONFIG_FILE.with_suffix(f".corrupt.{ts}")
                    CONFIG_FILE.replace(corrupt_path)
                    logger.warning(
                        f"Backup del archivo corrupto guardada: {corrupt_path}"
                    )
                except Exception as backup_error:  # noqa: BLE001
                    logger.error(f"No se pudo respaldar el archivo: {backup_error}")

                # Restauración de valores por defecto
                self._save(self.DEFAULTS)
                return copy.deepcopy(self.DEFAULTS)

    def _save(self, data: dict[str, Any]) -> None:
        """Guarda el diccionario en disco de forma atómica y protegida frente a otros hilos."""
        with self._lock:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            # Se añade el PID para aislar el temporal de cada instancia abierta
            temp_file = CONFIG_FILE.with_suffix(f".tmp.{os.getpid()}")
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)

                if sys.platform == "win32":
                    # Mitigación en Windows: reintentos ante bloqueos de EDR/Antivirus
                    for intento in range(3):
                        try:
                            os.replace(temp_file, CONFIG_FILE)
                            break
                        except PermissionError:
                            if intento == 2:  # Si falla en el último intento, se lanza
                                raise
                            time.sleep(0.05)
                else:
                    # POSIX (macOS/Linux): la sustitución es atómica nativamente
                    os.replace(temp_file, CONFIG_FILE)

            except Exception:
                logger.exception("Error al guardar el archivo de configuración.")
                if temp_file.exists():
                    temp_file.unlink(missing_ok=True)
                raise  # Se relanza para notificar al llamador que no se pudo guardar

    def get(self, key: str, default: Any = None) -> Any:
        """Devuelve un valor de la configuración protegiendo la lectura de modificaciones simultáneas."""
        with self._lock:
            return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Actualiza un valor sincronizando primero con el disco de forma aislada."""
        with self._lock:
            valor_anterior = self.data.get(key)

            if valor_anterior != value:
                # Respaldo atómico de todo el estado garantizando desvinculación de referencias
                estado_respaldo = copy.deepcopy(self.data)

                if CONFIG_FILE.exists():
                    self.data = self._load()

                self.data[key] = value
                try:
                    self._save(self.data)
                    logger.info(
                        f"Configuración actualizada [{key}]: '{valor_anterior}' -> '{value}'"
                    )
                except Exception:
                    # Restauración total para evitar inconsistencias
                    self.data = estado_respaldo
                    raise
