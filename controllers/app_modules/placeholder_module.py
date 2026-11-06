"""Módulo provisional: un botón de la toolbar cuyo módulo todavía no existe.

Sirve para que los botones de Imagen, Vídeo y Audio ya funcionen: muestran una página
"próximamente" en la barra lateral (la crea 'ModeToolbar') y no cambian lo que se ve en
la cuadrícula. Cuando un módulo tenga su propia clase, se sustituye en 'registry.py'.
"""

__version__ = "1.0.0"
__all__ = ["PlaceholderModule"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject
from qtpy.QtWidgets import QToolButton

# Módulos del proyecto
from controllers.app_modules.base import AppModule, ModuleContext


class PlaceholderModule(AppModule):
    """Módulo sin barra lateral ni cuadrícula propias (todo lo hereda de 'AppModule')."""

    def __init__(
        self,
        context: ModuleContext,
        *,
        key: str,
        title: str,
        icon: str | None,
        button: QToolButton,
        parent: QObject | None = None,
    ) -> None:
        """Prepara el módulo provisional.

        Args:
            context: Lo que comparte la ventana principal.
            key: Clave del módulo ('image', 'video'...).
            title: Nombre para el usuario.
            icon: Ruta del icono SVG del botón, o None (se ve su inicial).
            button: Botón de la toolbar que lo activa.
            parent: Objeto padre.
        """
        super().__init__(context, button=button, parent=parent)
        # Atributos de instancia: tapan los de la clase base (cada provisional tiene los suyos)
        self.key = key
        self.title = title
        self.icon = icon
