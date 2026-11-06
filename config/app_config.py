"""Módulo de acceso a la configuración global de la aplicación.

Implementa el patrón Singleton a nivel de módulo proporcionando una única
instancia de 'ConfigManager'. Esto garantiza que cualquier parte de la
aplicación que importe este módulo interactúe exactamente con el mismo
estado y configuración, evitando desincronizaciones y accesos redundantes.

Uso recomendado:
    from config.app_config import config
"""

__version__ = "1.00"
__all__ = ["config"]

# Módulos del proyecto
from config.app_config_manager import ConfigManager

# Instancia única y permanente que se inicializa solo cuando se importa este módulo
config = ConfigManager()
