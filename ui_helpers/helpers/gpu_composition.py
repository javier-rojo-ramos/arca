"""Que la ventana principal se dibuje con la GPU desde que se abre.

Qué resuelve (visto por el autor el 12 y el 13/11/2026; docs/TRAMPAS.md):
    - Qt Widgets dibuja la ventana sin la GPU y, en Windows, sin esperar al refresco de la
      pantalla: al arrastrar deprisa una foto grande (vista individual a 1:1) se ven cortes
      horizontales.
    - El primer elemento que necesita la GPU (la vista web del mapa) obliga a Qt a crear
      OTRA ventana nativa, ya compuesta con la GPU: la ventana desaparece un instante y,
      con una tarjeta Nvidia, sale su aviso. Desde ese momento, todo va suave.

Cómo: antes de mostrar la ventana se le pone dentro un 'QQuickWidget' invisible de 1 px.
Basta con que exista para que Qt cree la ventana nativa directamente en modo GPU; así, al
abrir el mapa ya no se rehace. Es un 'QQuickWidget' (no un 'QOpenGLWidget') porque es lo
que usa por dentro la vista web del mapa: los dos piden a la GPU lo mismo (en Windows,
Direct3D 11) y no chocan. Comprobado el 13/11/2026 en Windows con la plataforma real: sin
él, la ventana nace sin GPU y al añadir uno de GPU se crea otra ventana nativa; con él,
nace con Direct3D y no se rehace.

Opción «Usar aceleración por GPU si está disponible» (Opciones > General; se aplica al
volver a abrir la aplicación). Mientras el usuario no la toque, depende del sistema
('default_gpu_setting'; decidido por el autor el 13/11/2026): activada en Windows
(Direct3D 11) y en macOS (Metal, en todos los Mac de los últimos años); desactivada en
Linux (OpenGL), donde depende mucho de los controladores, de X11 o Wayland y de si es
una máquina virtual, y aún no se ha probado. El código es el mismo en todos: el
'QQuickWidget' pide a la GPU la tecnología propia de cada sistema. Si con ella la
ventana no se viera (controladores gráficos
malos, algunas máquinas virtuales o escritorios remotos), se puede arrancar sin ella con
el argumento '--sin-gpu' (python main.py --sin-gpu) y desactivarla en Opciones.

Uso (en el constructor de la ventana principal, ANTES de mostrarla):
    if gpu_allowed(config.get(SETTING_GPU_RENDERING)):
        enable_gpu_composition(ventana)

1.1.0 Sin elegir, según el sistema ('default_gpu_setting'): sí en Windows y macOS, no en
      Linux.
1.0.0 Primera versión (paso suelto antes de la fase 3 de docs/MAPA.md).

Prueba rápida (desde la raíz del proyecto; crea ventanas que no se muestran en pantalla):
    python -m ui_helpers.helpers.gpu_composition
"""

__version__ = "1.1.0"
__all__ = ["NO_GPU_ARGUMENT", "default_gpu_setting", "enable_gpu_composition", "gpu_allowed"]

# Librerías estándar
import sys
from collections.abc import Sequence

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QCoreApplication, Qt
from qtpy.QtWidgets import QWidget

# Argumento de la línea de órdenes para arrancar sin GPU aunque la opción esté activada
NO_GPU_ARGUMENT = "--sin-gpu"

_PROBE_NAME = "gpu_composition_probe"


# Sistemas en los que la aceleración viene activada (ver el docstring del archivo)
_GPU_BY_DEFAULT = ("win32", "darwin")


def default_gpu_setting(platform: str | None = None) -> bool:
    """La opción mientras el usuario no la toca: sí en Windows y macOS, no en Linux.

    Args:
        platform: El sistema, como 'sys.platform' (por defecto, este).
    """
    return (sys.platform if platform is None else platform) in _GPU_BY_DEFAULT


def gpu_allowed(
    setting: object, arguments: Sequence[str] | None = None, platform: str | None = None
) -> bool:
    """True si se debe usar la GPU: según la opción (si no se ha elegido, según el sistema)
    y si no se ha arrancado con '--sin-gpu'.

    Args:
        setting: El valor de la opción en settings.json: True o False si el usuario la
            eligió; cualquier otra cosa (None, al empezar), lo del sistema.
        arguments: Argumentos de la línea de órdenes (por defecto, los de la aplicación).
        platform: El sistema, como 'sys.platform' (por defecto, este).
    """
    if arguments is None:
        arguments = QCoreApplication.arguments()
    if NO_GPU_ARGUMENT in arguments:
        return False
    return setting if isinstance(setting, bool) else default_gpu_setting(platform)


def enable_gpu_composition(window: QWidget) -> bool:
    """Hace que la ventana se cree ya en modo GPU (ver el docstring del archivo).

    Hay que llamarla ANTES de mostrar la ventana: si su ventana nativa ya existe, no hace
    nada (Qt tendría que rehacerla, justo lo que se quiere evitar).

    Returns:
        True si se ha preparado; False si no se ha podido (ya mostrada, o sin QtQuick).
    """
    if window.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
        logger.warning("La ventana ya está creada: no se puede pasar a la GPU sin rehacerla.")
        return False
    if window.findChild(QWidget, _PROBE_NAME) is not None:
        return True  # ya estaba
    try:
        from qtpy.QtQuickWidgets import QQuickWidget
    except ImportError:
        logger.warning("Sin QtQuickWidgets: la ventana se dibujará sin la GPU.")
        return False
    probe = QQuickWidget(window)
    probe.setObjectName(_PROBE_NAME)
    probe.resize(1, 1)
    probe.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    probe.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    probe.setVisible(False)  # no se dibuja nunca: basta con que exista
    logger.info("La ventana se dibujará con la GPU (aceleración por GPU activada).")
    return True


if __name__ == "__main__":
    # Autoprueba: ventanas que se crean pero NO se muestran en pantalla.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.helpers.gpu_composition
    import sys

    from qtpy.QtWidgets import QApplication, QLabel, QVBoxLayout

    app = QApplication(sys.argv[:1])

    # 1. La opción, el argumento y, sin elegir, el sistema
    for platform in ("win32", "darwin", "linux"):
        assert gpu_allowed(True, [], platform) and not gpu_allowed(False, [], platform)
        assert not gpu_allowed(True, ["main.py", NO_GPU_ARGUMENT], platform)
    assert gpu_allowed(None, [], "win32") and gpu_allowed(None, [], "darwin")
    assert not gpu_allowed(None, [], "linux") and not gpu_allowed("x", [], "linux")
    assert default_gpu_setting("win32") and not default_gpu_setting("freebsd")

    def window_with(prepared: bool) -> tuple[str, str, bool]:
        """(superficie al mostrarla, superficie tras añadirle algo de GPU, sin rehacerla)."""
        from qtpy.QtQuickWidgets import QQuickWidget

        window = QWidget()
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        QVBoxLayout(window).addWidget(QLabel("prueba"))
        window.resize(200, 100)
        if prepared:
            assert enable_gpu_composition(window) and enable_gpu_composition(window)
        window.show()
        app.processEvents()
        before = window.windowHandle()
        surface, native = before.surfaceType().name, int(before.winId())
        late = QQuickWidget(window)  # como la vista web del mapa, al abrirlo
        late.resize(10, 10)
        late.show()
        app.processEvents()
        after = window.windowHandle()
        same = after is before and int(after.winId()) == native
        result = (surface, after.surfaceType().name, same)
        assert not enable_gpu_composition(window)  # ya creada: no se toca
        window.close()
        window.deleteLater()
        app.processEvents()
        return result

    # 2. Con la ventana preparada, añadir algo de GPU después no la rehace (sin preparar,
    #    con la plataforma real, sí: es el parpadeo)
    plain = window_with(False)
    prepared = window_with(True)
    print(f"Plataforma: {QApplication.platformName()}")
    print(f"  sin preparar: nace con {plain[0]}, después {plain[1]}, misma ventana nativa: {plain[2]}")
    print(f"  preparada:    nace con {prepared[0]}, después {prepared[1]}, misma ventana nativa: {prepared[2]}")
    assert prepared[2], "la ventana preparada no debe rehacerse"
    if QApplication.platformName() not in ("offscreen", "minimal"):
        assert prepared[0] == prepared[1] != "RasterSurface", prepared

    print("Autoprueba finalizada correctamente.")
