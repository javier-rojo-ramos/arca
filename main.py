# Librerías estándar
import sys
import types

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QTranslator
from qtpy.QtWidgets import QApplication

# Módulos del proyecto
from config import app_paths
from config.app_logging_manager import setup_logging
from controllers.main_window_controller import MainWindowController
from ui_helpers.helpers.ui_theme import apply_theme


def global_exception_handler(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: types.TracebackType | None,
) -> None:
    """Captura cualquier excepción no controlada en la aplicación, incluso las de Qt."""
    # Ignorar excepciones al presionar Ctrl+C en la consola
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Registrar el error completo en el log de 'loguru'
    logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical(
        "Excepción global no capturada:"
    )

    # ACLARACIÓN FUTURA: Al llegar aquí, el error queda registrado en el log
    # pero la interfaz (GUI) sigue funcionando. Si en algún momento se quiere
    # que un error no controlado cierre la aplicación por seguridad para evitar
    # estados inconsistentes, quita el # de la siguiente línea:

    # QApplication.quit()


def main():
    # Se inicializa la configuración del log con 'loguru'
    try:
        setup_logging(app_paths.APP_NAME)
    except Exception:  # noqa: BLE001
        # Por si el error ocurrió después de logger.remove() en setup_logging,
        # se fuerza una salida a stderr (solo si existe: con --noconsole es None)
        if sys.stderr is not None:
            logger.add(sys.stderr, level="ERROR")
        logger.opt(exception=True).error(
            "Fallo en setup_logging, posible problema de permisos. Usando consola."
        )

    logger.info(f"Iniciando {app_paths.APP_NAME.lower()}...")

    # Redirigir errores no controlados de PySide6 a nuestro logger, el módulo
    # app_logging_manager.py ya incorpora un hook propio para sys.excepthook
    # pero no hay conflicto, este sustituye al del módulo ya que se ejecuta después...
    # no obstante se podría quitar esta línea y la función global_exception_handler
    sys.excepthook = global_exception_handler

    try:
        # Se asegura el icono en la barra de tareas de Windows
        if sys.platform == "win32":
            import ctypes

            # Se da nombre a la aplicación
            myappid = f"{app_paths.APP_NAME.lower()}.app"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:  # noqa: BLE001
        logger.opt(exception=True).warning("Error configurando AppUserModelID Windows.")

    # Mapa: Qt exige registrar su esquema ('arca-map://') e importar QtWebEngine ANTES de
    # crear QApplication, aunque el mapa no llegue a abrirse (ver docs/TRAMPAS.md). El
    # motor web no arranca aquí: lo hace la primera vez que se muestra un mapa. Si en
    # este equipo falta QtWebEngine, la aplicación sigue adelante sin mapa.
    try:
        from ui_helpers.map.map_scheme import register_map_scheme

        register_map_scheme()
    except ImportError:
        logger.opt(exception=True).warning(
            "QtWebEngine no está disponible: la vista de mapa no funcionará."
        )

    try:
        # Se inicializa la aplicación
        app = QApplication(sys.argv)
        logger.info("QApplication instanciado correctamente (motor gráfico listo).")

        # Carga e instalación de traducciones nativas en español
        traductor = QTranslator()
        ruta_traduccion = app_paths.RESOURCES_DIR / "locales" / "qtbase_es.qm"

        if ruta_traduccion.exists() and traductor.load(str(ruta_traduccion)):
            app.installTranslator(traductor)
            logger.info("Traducción nativa de Qt (español) cargada con éxito.")
        else:
            logger.warning(
                f"No se pudo cargar la traducción nativa desde: {ruta_traduccion}"
            )

        # Para que el menú nativo de macOS muestre el nombre del programa en
        # lugar de "Python", es obligatorio definirlo antes de cargar la ventana
        app.setApplicationName(app_paths.APP_NAME_COMERCIAL)

        # Qt a menudo requiere que la "Organización" también esté definida para
        # que ciertas integraciones de macOS funcionen correctamente
        app.setOrganizationName(app_paths.ORG_NAME)

        # Estilo Fusion (igual en Windows, macOS y Linux) y, justo después, el tema: tiene
        # que aplicarse ANTES de crear la ventana, porque algunos widgets copian colores
        # de la paleta al construirse (p. ej. las etiquetas en gris del inspector)
        app.setStyle("Fusion")
        apply_theme()

        # Política de cierre: la app termina al cerrar la ventana principal
        app.setQuitOnLastWindowClosed(True)

        # Instanciar y mostrar controlador
        ventana = MainWindowController()
        ventana.iniciar()
        logger.info("Interfaz principal cargada correctamente.")

        # Entrar al bucle de eventos
        logger.info("Entrando en el bucle de eventos de Qt.")
        exit_code = app.exec()

        # Cierre limpio
        logger.info(f"Aplicación finalizada (exit_code={exit_code})")
        sys.exit(exit_code)

    except Exception:  # noqa: BLE001
        # Esto solo capturará errores de inicialización antes del app.exec()
        # (por ejemplo, si MainWindowController falla al instanciarse)
        logger.exception("Error fatal durante el arranque de la aplicación.")
        sys.exit(1)


if __name__ == "__main__":
    main()
