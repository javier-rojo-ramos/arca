"""Configuración centralizada del sistema de registros (logging).

Este módulo unifica el subsistema de 'logging' estándar de Python con la librería
'loguru'. Proporciona un manejador de interceptación dinámico que preserva la
profundidad de la pila de llamadas (stack trace), configura salidas simultáneas
para consola (coloreada) y archivos rotativos, y resuelve las rutas de guardado
de forma nativa según el sistema operativo (Windows, macOS, Linux).

Características principales:
    - Los mensajes del 'logging' estándar (p. ej. de módulos desacoplados o de
      librerías de terceros) se redirigen a 'loguru', de modo que todo acaba en
      los mismos destinos y con el mismo formato.
    - Si el reenvío de un mensaje falla (p. ej. una llamada a 'logging' con
      argumentos mal formados), el error se delega en 'handleError', como hacen
      los manejadores estándar, y nunca rompe el programa.
    - La consola solo se activa si 'sys.stdout' existe (en ejecutables de
      PyInstaller con --noconsole vale None).
    - El archivo de log se codifica en UTF-8 y no incluye valores de variables
      en los tracebacks (diagnose=False) para no filtrar datos sensibles.
    - Cada instancia de la aplicación escribe en su propio archivo (el nombre
      incluye el PID del proceso). Así varias instancias abiertas a la vez no
      se pisan ni provocan errores de rotación (en Windows no se puede renombrar
      un archivo abierto por otro proceso). Al arrancar se eliminan los logs más
      antiguos para que la carpeta no crezca indefinidamente.
    - Las excepciones no controladas (hilo principal, hilos secundarios y errores
      "no propagables" de destructores o callbacks) se registran en el log. Así
      no se pierden en ejecutables sin consola (--noconsole). En PySide6 esto
      incluye las excepciones que se producen dentro de slots y eventos de Qt.
    - Los avisos de la librería 'warnings' de Python (DeprecationWarning,
      UserWarning, etc.) se registran en el log en lugar de ir a stderr.
    - Los mensajes internos de Qt (qDebug, qWarning, qCritical...) también se
      registran en el log. Se usa 'qtpy' y, si no está disponible, 'PySide6'; si
      no hay ninguna de las dos, esta parte se omite.
    - Las librerías de terceros que son muy verbosas en nivel DEBUG (las
      indicadas en NOISY_LOGGERS) se limitan a WARNING para que no llenen el
      archivo de log. IMPORTANTE: hay que actualizar NOISY_LOGGERS en función de
      las librerías que se usen en cada programa.
    - Si la ruta de logs del sistema no es accesible (permisos, disco de solo
      lectura, perfil de empresa restringido), se usa la carpeta temporal del
      sistema como alternativa en lugar de impedir el arranque de la aplicación.
    - (1.09) Los errores FATALES, los que tiran el proceso sin pasar por Python
      (acceso a memoria no válido, memoria dañada: en Windows, 0xc0000005 y
      0xc0000374), dejan la pila de cada hilo en un archivo aparte junto al log,
      '{app_name}_{PID}.crash.log', con 'faulthandler' de la librería estándar.
      Suelen venir de una librería nativa (Qt, una extensión en C, un controlador)
      y sin esto no dejan ningún rastro en el log. Los vacíos (sesiones sin
      errores) se borran al arrancar. Se desactiva con
      'setup_logging(capture_fatal_errors=False)'.
    - (1.10) En Windows, 'faulthandler' escribe también excepciones que Windows lanza y
      recoge él mismo (de COM: 0x8001010d), sin que el programa se cierre. Al cerrar
      bien, 'discard_recovered_crash_dump()' vacía el volcado si solo trae esas, y lo
      apunta en el log con una línea; si trae cualquier otra cosa, se queda tal cual.

Requiere importar el nombre de la aplicación (APP_NAME) desde el archivo
correspondiente.

1.10 'discard_recovered_crash_dump': al cerrar bien, el volcado se vacía si solo trae
     excepciones de COM recuperadas (RECOVERED_COM_CODES), con una línea en el log
     (añadido para Arca Media el 20/11/2026: dejaban un '.crash.log' que alarmaba sin
     ser un cierre). Hay que llamarla al salir del bucle de eventos; sin la llamada,
     todo sigue como en la 1.09.
1.09 Volcado de los errores fatales con 'faulthandler' (añadido para Arca Media, el
     18/11/2026, tras unos cierres con 0xc0000374 que no dejaban nada en el log).
     Todo lo nuevo está en la sección «Errores fatales» del final y en el parámetro
     'capture_fatal_errors' de 'setup_logging' (por defecto True); lo demás no cambia.
1.08 Qt solo a través de 'qtpy': se quita la alternativa de importar PySide6 directamente
     (regla del proyecto); sin 'qtpy', los mensajes de Qt no se capturan.
1.07 Se introcuce NOISY_LOGGERS como una lista de librerías que se limitan a WARNING.
1.06 InterceptHandler.emit delega los fallos en handleError (registrar un mensaje
    nunca rompe el programa). Las librerías de NOISY_LOGGERS se limitan a WARNING.
1.05 El módulo prueba primero con qtpy, y cae a PySide6 si no está disponible. Si
    no hay ninguna de las dos, se omite.
1.04 Las excepciones que ningún try/except captura (hilo principal, incluidos slots
    y eventos de Qt de PySide6, hilos secundarios y errores no propagables) quedan
    registradas en el log, en lugar de perderse. También se registran los avisos
    de 'warnings' y los mensajes internos de Qt (qInstallMessageHandler).
1.03 Cada instancia del programa escribe en su propio archivo, {app_name}_{PID}.log
1.02 No incluye valores de variables en los tracebacks (diagnose=False). Si la ruta
    de logs del sistema no es accesible, usa la carpeta temporal como alternativa.
1.01 Se preserva la profundidad de la pila de llamadas (stack trace)
"""

__version__ = "1.10"
__all__ = [
    "InterceptHandler",
    "discard_recovered_crash_dump",
    "setup_logging",
]

# Librerías estándar
import faulthandler
import logging
import os
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import TextIO

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from config.app_paths import APP_NAME

# Número máximo de archivos de log que se conservan en la carpeta (sumando los
# de todas las instancias, activas o ya cerradas)
MAX_LOG_FILES = 20

# Librerías de terceros muy verbosas en DEBUG: se limitan a WARNING para que no
# llenen el archivo de log (con rotación de 5 MB se perderían los mensajes útiles).
# IMPORTANTE: Actualizar esta lista en función de las librerías que use cada programa
NOISY_LOGGERS = ("PIL", "urllib3", "asyncio", "matplotlib")

# Equivalencia entre los tipos de mensaje de Qt y los niveles de 'loguru'. Se
# rellena en _install_qt_message_handler para no importar ninguna librería Qt al
# cargar este módulo (así sigue funcionando en programas que no usan Qt)
_QT_LEVELS: dict = {}

# (1.09) Volcado de los errores fatales: terminación del archivo, que va junto al log de
# la instancia ('arca_1234.log' -> 'arca_1234.crash.log'), y el archivo abierto, que
# tiene que seguir así mientras dure el programa (ver '_enable_crash_dump')
CRASH_SUFFIX = ".crash.log"
_crash_file: TextIO | None = None

# (1.10) Códigos de las excepciones de COM que Windows lanza y recoge él mismo, sin que el
# programa se cierre, y que 'faulthandler' escribe igual (las ve antes de que se recojan).
# 0x8001010d (RPC_E_CANTCALLOUT_ININPUTSYNCCALL): una llamada de COM rechazada mientras la
# ventana contesta a un mensaje que otro programa espera (accesibilidad, portapapeles,
# vistas previas de Alt+Tab...). Tal como los escribe 'faulthandler': en minúsculas
RECOVERED_COM_CODES: tuple[str, ...] = ("0x8001010d",)

# Cómo empieza cada volcado de 'faulthandler': el de un error de Windows y el de Python
_DUMP_HEADERS = ("Windows fatal exception:", "Fatal Python error:")

# Se define el formato base con colores para la consola
CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<magenta>{function}</magenta>:<yellow>{line}</yellow> - "
    "<level>{message}</level>"
)

# Se define el formato plano para el archivo
FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
)


class InterceptHandler(logging.Handler):
    """Intercepta logs estándar de Python y los redirige al pipeline de Loguru.

    Garantiza que el nombre del archivo, la función y la línea del código de
    origen se capturen correctamente en lugar de mostrar los metadatos internos
    del propio interceptor.

    Si el reenvío falla (p. ej. una llamada a 'logging' con argumentos mal
    formados), el error se delega en 'handleError', como hacen los manejadores
    estándar, de modo que registrar un mensaje nunca rompe el programa.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Un fallo al registrar nunca debe romper el programa: se delega en
        # handleError, que es lo que hacen los manejadores estándar. El cuerpo se
        # deja dentro de emit (sin método auxiliar) para no añadir un frame extra
        # a la pila y que la profundidad calculada siga siendo la misma.
        try:
            # Se obtiene el nivel de log correspondiente en 'loguru'
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            # Encontrar el origen real buscando de forma dinámica en el stack.
            # Se parte de la profundidad 6 (emit -> handle -> callHandlers ->
            # handle -> _log -> info/warning/... -> código del usuario). Si la
            # pila fuese más corta (p. ej. alguien llama a emit() directamente),
            # _getframe lanza ValueError: en ese caso se usa la profundidad por
            # defecto.
            try:
                frame, depth = sys._getframe(6), 6
            except ValueError:
                frame, depth = None, 0

            # Se saltan los frames internos del módulo 'logging' (p. ej. el extra
            # que añaden funciones de módulo como logging.info()). Además de
            # comparar la ruta del archivo, se compara el nombre del módulo, que
            # sigue siendo fiable aunque la ruta cambie al empaquetar con
            # PyInstaller.
            while frame and (
                frame.f_code.co_filename == logging.__file__
                or frame.f_globals.get("__name__") == logging.__name__
            ):
                frame = frame.f_back
                depth += 1

            # Se envía a 'loguru' con la profundidad exacta calculada
            logger.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )
        except Exception:  # noqa: BLE001
            self.handleError(record)


def setup_logging(
    app_name: str = APP_NAME,
    install_exception_hooks: bool = True,
    capture_warnings: bool = True,
    capture_qt_messages: bool = True,
    capture_fatal_errors: bool = True,
) -> Path | None:
    """Configura 'loguru' para el proyecto (consola y archivo rotativo).

    Se puede llamar más de una vez: cada llamada reinicia la configuración.

    Nota: antes de usar este módulo en un programa nuevo hay que revisar la
    constante NOISY_LOGGERS y ajustarla a las librerías que ese programa utilice.

    Args:
        app_name: Nombre de la aplicación; se usa para la carpeta y el archivo
            de log.
        install_exception_hooks: Si es True (por defecto), se redirigen al log
            las excepciones no controladas (ver '_install_exception_hooks').
            Poner False si otra parte del programa gestiona ya esos hooks.
        capture_warnings: Si es True (por defecto), los avisos de 'warnings' se
            envían al log mediante 'logging.captureWarnings'.
        capture_qt_messages: Si es True (por defecto), los mensajes internos de
            Qt se envían al log (ver '_install_qt_message_handler'). Debe
            llamarse a 'setup_logging' antes de crear la QApplication para no
            perder los mensajes del arranque.
        capture_fatal_errors: (1.09) Si es True (por defecto), un error fatal
            deja la pila de cada hilo en '<log>.crash.log' (ver
            '_enable_crash_dump'). Solo si hay archivo de log.

    Returns:
        Ruta del archivo de log en uso, o None si no se pudo crear ninguno
        (en ese caso solo queda activa la consola, si existe).
    """
    # Se limpia la configuración por defecto que trae 'loguru'
    logger.remove()

    # Se configura la consola (muestra desde INFO hacia arriba) sólo si sys.stdout
    # está disponible (así se evita que falle al usar --noconsole con PyInstaller)
    if sys.stdout is not None:
        logger.add(
            sys.stdout,
            level="INFO",
            format=CONSOLE_FORMAT,
        )

    # Se prueba primero la ruta nativa del SO y, si falla, la carpeta temporal.
    # Se registran los fallos para avisar cuando ya esté todo configurado.
    candidates = (
        _get_log_dir(app_name),
        Path(tempfile.gettempdir()) / app_name / "logs",
    )
    log_file: Path | None = None
    failures: list[str] = []

    for log_dir in candidates:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            # El PID en el nombre da un archivo distinto por instancia
            file_path = log_dir / f"{app_name}_{os.getpid()}.log"

            # Se configura el archivo log (guarda todo, desde DEBUG hacia arriba)
            logger.add(
                file_path,
                level="DEBUG",
                rotation="5 MB",  # Se corta al llegar a 5MB
                # Se queda solo con los últimos 3 archivos de backup (por instancia)
                retention=3,
                format=FILE_FORMAT,
                encoding="utf-8",  # Evita depender de la codificación del SO
                diagnose=False,  # No vuelca valores de variables en los tracebacks
            )
            log_file = file_path

            # Se eliminan los logs antiguos de instancias anteriores
            _cleanup_old_logs(log_dir, app_name)
            break
        except OSError as exc:
            failures.append(f"{log_dir}: {exc}")

    # Se activa la interceptación de logging estándar, force=True evita warnings
    # si ya está configurado. Al sustituir todos los manejadores del logger raíz
    # por InterceptHandler no hay logs duplicados: 'loguru' no reenvía nada al
    # 'logging' estándar, así que no hace falta tocar 'propagate' (en el logger
    # raíz, además, ese atributo no tiene ningún efecto).
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.DEBUG, force=True)

    # Se silencian los detalles (DEBUG/INFO) de las librerías ruidosas, que de lo
    # contrario llenarían el archivo de log al estar el logger raíz en DEBUG
    for noisy_name in NOISY_LOGGERS:
        logging.getLogger(noisy_name).setLevel(logging.WARNING)

    # Se registran también las excepciones no controladas, que de otro modo se
    # perderían en un ejecutable sin consola
    if install_exception_hooks:
        _install_exception_hooks()

    # Se redirigen los avisos de 'warnings' al sistema de logging (llegan al
    # logger 'py.warnings' y de ahí a InterceptHandler)
    if capture_warnings:
        logging.captureWarnings(True)

    # Se redirigen los mensajes internos de Qt (que por defecto van a stderr)
    if capture_qt_messages:
        _install_qt_message_handler()

    # (1.09) Los errores fatales se vuelcan en un archivo aparte, junto al log
    crash_path = None
    if capture_fatal_errors and log_file is not None:
        crash_path = _enable_crash_dump(log_file, app_name)

    # Se informa de los problemas con las rutas una vez el sistema está operativo
    if failures:
        if log_file is None:
            logger.warning("No se pudo crear ningún archivo de log: {}", failures)
        else:
            logger.warning("Ruta de logs por defecto no disponible: {}", failures)
    if crash_path is not None:
        logger.debug("Si hay un error fatal, su volcado irá a: {}", crash_path)

    return log_file


def _cleanup_old_logs(
    log_dir: Path, app_name: str, max_files: int = MAX_LOG_FILES
) -> None:
    """Elimina los logs más antiguos de la carpeta, conservando los más recientes.

    Al tener un archivo por instancia (con el PID en el nombre), la retención de
    'loguru' solo limpia los backups de cada archivo, no los de instancias ya
    cerradas. Esta función cubre ese hueco. Nunca lanza excepciones: limpiar
    logs no debe impedir que la aplicación arranque.

    Args:
        log_dir: Carpeta donde se guardan los logs.
        app_name: Nombre de la aplicación (prefijo de los archivos).
        max_files: Número de archivos a conservar (los de modificación más
            reciente).
    """
    try:
        files = sorted(
            log_dir.glob(f"{app_name}_*.log*"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        # Otra instancia pudo borrar un archivo mientras se ordenaba: se omite
        return

    for old_file in files[max_files:]:
        try:
            old_file.unlink()
        except OSError:
            # En uso por otra instancia (Windows) o sin permisos: se ignora
            pass


def _install_exception_hooks() -> None:
    """Redirige al log las excepciones que ningún 'try/except' ha capturado.

    Instala tres hooks de Python:
        - 'sys.excepthook': hilo principal. En PySide6 también recibe las
          excepciones lanzadas dentro de slots y eventos de Qt (la aplicación
          normalmente sigue funcionando después, por eso es importante verlas).
        - 'threading.excepthook': hilos secundarios (threading.Thread).
        - 'sys.unraisablehook': errores que no se pueden propagar (en
          destructores '__del__', callbacks, etc.).
    """
    sys.excepthook = _handle_uncaught_exception
    threading.excepthook = _handle_thread_exception
    sys.unraisablehook = _handle_unraisable


def _handle_uncaught_exception(exc_type, exc_value, exc_traceback) -> None:
    """Registra una excepción no controlada del hilo principal (CRITICAL)."""
    # Ctrl+C no es un fallo del programa: se deja el comportamiento por defecto
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical(
        "Excepción no controlada"
    )


def _handle_thread_exception(args: threading.ExceptHookArgs) -> None:
    """Registra una excepción no controlada de un hilo secundario (CRITICAL)."""
    # SystemExit en un hilo es una salida normal y Python ya la ignora
    if issubclass(args.exc_type, SystemExit):
        return

    thread_name = args.thread.name if args.thread else "desconocido"
    logger.opt(exception=(args.exc_type, args.exc_value, args.exc_traceback)).critical(
        "Excepción no controlada en el hilo '{}'", thread_name
    )


def _handle_unraisable(unraisable) -> None:
    """Registra una excepción que Python no ha podido propagar (ERROR)."""
    # Si no hay excepción asociada se registra solo el mensaje
    exception = (
        (unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback)
        if unraisable.exc_value is not None
        else None
    )
    logger.opt(exception=exception).error(
        "Excepción no propagable: {}", unraisable.err_msg or "sin descripción"
    )


def _install_qt_message_handler() -> None:
    """Redirige al log los mensajes internos de Qt (qDebug, qWarning, etc.).

    Por defecto Qt escribe esos mensajes en stderr, que en un ejecutable sin
    consola no existe. Usa 'qtpy' (igual que el resto del programa) para
    enlazar con el mismo binding de Qt que utiliza la aplicación y, si no está
    disponible, prueba con 'PySide6' directamente. Si no hay ninguna de las dos
    no hace nada.

    Notas:
        - Los filtros de la variable de entorno QT_LOGGING_RULES siguen
          funcionando: Qt los aplica antes de llamar al manejador.
        - El patrón QT_MESSAGE_PATTERN deja de tener efecto, porque el formato
          lo define ahora este módulo.
    """
    # Importación diferida: este módulo no debe depender de ninguna librería Qt.
    # Se prefiere 'qtpy' para instalar el manejador en el mismo binding que usa
    # la aplicación (si hubiese varios instalados, uno directo de PySide6 podría
    # no ser el que se está usando y los mensajes no se capturarían)
    try:
        from qtpy.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError:
        # Sin 'qtpy' no hay Qt que capturar: el proyecto solo usa Qt a través de él
        return

    _QT_LEVELS.update(
        {
            QtMsgType.QtDebugMsg: "DEBUG",
            QtMsgType.QtInfoMsg: "INFO",
            QtMsgType.QtWarningMsg: "WARNING",
            QtMsgType.QtCriticalMsg: "ERROR",
            QtMsgType.QtFatalMsg: "CRITICAL",
        }
    )
    qInstallMessageHandler(_qt_message_handler)


def _qt_message_handler(msg_type, context, message: str) -> None:
    """Recibe un mensaje de Qt y lo registra con el nivel equivalente.

    Args:
        msg_type: Tipo de mensaje de Qt (QtMsgType).
        context: Contexto del mensaje (QMessageLogContext). Solo se usa la
            categoría: el archivo y la línea de origen suelen estar vacíos en
            las compilaciones de Qt de producción.
        message: Texto del mensaje.
    """
    level = _QT_LEVELS.get(msg_type, "WARNING")
    category = context.category or "default"

    # Los argumentos se pasan a 'loguru' por separado para que las llaves que
    # pueda contener el mensaje de Qt no se interpreten como formato
    logger.log(level, "[Qt {}] {}", category, message)


def _get_log_dir(app_name: str) -> Path:
    """Devuelve la ruta correcta para guardar los logs según el SO."""
    match sys.platform:
        case "win32":  # Windows
            base_dir = Path(
                os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
            )
            # Se añade la subcarpeta /logs para mantener la raíz limpia
            return base_dir / app_name / "logs"

        case "darwin":  # macOS
            # macOS tiene una carpeta de sistema dedicada exclusivamente a los logs del usuario
            return Path.home() / "Library" / "Logs" / app_name

        case _:  # Linux / Unix (fallback)
            # El estándar XDG moderno define XDG_STATE_HOME para archivos de log / historial
            xdg_state = os.environ.get("XDG_STATE_HOME")
            if xdg_state:
                base_dir = Path(xdg_state)
            else:
                # Fallback estándar si la variable no existe
                base_dir = Path.home() / ".local" / "state"
            return base_dir / app_name


# -----------------------------------------------------------------------------
# Errores fatales (añadido en la versión 1.09)
# -----------------------------------------------------------------------------


def _enable_crash_dump(log_file: Path, app_name: str) -> Path | None:
    """Activa 'faulthandler': si el proceso cae por un error fatal, deja la pila de cada hilo.

    Un error fatal tira el proceso sin pasar por Python (un acceso a memoria no válido,
    la memoria dañada...), así que ningún 'except' ni ningún hook llega a ejecutarse y el
    log se corta sin más. 'faulthandler' (librería estándar) escribe en ese momento qué
    estaba haciendo cada hilo de Python, y en Windows, el código de la excepción.

    El volcado va a un archivo aparte, '<log>.crash.log', y no al propio log: 'loguru'
    renombra el log al rotarlo, y en Windows no podría hacerlo con otro manejador abierto
    sobre él. El archivo se crea vacío al arrancar y se queda abierto hasta que termina el
    proceso (así recoge también los fallos al cerrar, después de 'atexit'); los vacíos de
    sesiones anteriores se borran al arrancar ('_cleanup_empty_crash_files').

    Nota (Windows): 'faulthandler' escribe también algunas excepciones que el programa
    recupera después (las de COM o de algún controlador, p. ej.); un '.crash.log' con algo
    no siempre es un cierre: hay que comprobar si el log termina ahí. Las de COM conocidas
    las descarta 'discard_recovered_crash_dump' al cerrar bien (1.10).

    Args:
        log_file: Log de esta instancia (el volcado va a su lado, con su nombre).
        app_name: Nombre de la aplicación (prefijo de los archivos).

    Returns:
        La ruta del archivo de volcado, o None si no se pudo crear (no impide arrancar).
    """
    global _crash_file

    # Si se vuelve a llamar a 'setup_logging', se cierra el archivo anterior
    _disable_crash_dump()
    _cleanup_empty_crash_files(log_file.parent, app_name)

    crash_path = log_file.with_name(log_file.stem + CRASH_SUFFIX)
    try:
        # Sin 'with' a propósito: tiene que seguir abierto mientras dure el programa
        _crash_file = open(crash_path, "a", encoding="utf-8")  # noqa: SIM115
    except OSError:
        return None
    faulthandler.enable(file=_crash_file, all_threads=True)
    return crash_path


def _disable_crash_dump() -> None:
    """Desactiva 'faulthandler' y cierra su archivo, si estaba activo."""
    global _crash_file
    if _crash_file is None:
        return
    faulthandler.disable()
    _crash_file.close()
    _crash_file = None


def discard_recovered_crash_dump() -> int:
    """Al cerrar bien: vacía el volcado de esta sesión si solo trae excepciones recuperadas.

    En Windows, 'faulthandler' escribe también excepciones de COM que Windows lanza y
    recoge él mismo (RECOVERED_COM_CODES): la sesión sigue y termina bien, pero deja un
    '.crash.log' que parece un cierre. Si el volcado solo trae esas, se vacía y se apunta
    en el log cuántas eran y la hora de la última (la de la última escritura del archivo).
    Si trae cualquier otra cosa, se queda tal cual.

    El archivo se vacía pero sigue abierto, con 'faulthandler' activo: un fallo de verdad
    durante el resto del cierre se sigue escribiendo. El vacío se borra al arrancar la
    próxima vez ('_cleanup_empty_crash_files').

    Se llama al salir del bucle de eventos (en Arca Media, 'main.py', tras 'app.exec()').
    Nunca lanza excepciones.

    Returns:
        Cuántas excepciones recuperadas se descartaron: 0 si no hay volcado, si está vacío
        o si trae algo más.
    """
    if _crash_file is None:
        return 0
    path = Path(_crash_file.name)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        last_write = datetime.fromtimestamp(path.stat().st_mtime)
        count = _count_recovered_exceptions(text)
        if count:
            _crash_file.truncate(0)
    except (OSError, ValueError):
        return 0  # no se pudo leer o vaciar: se queda como está
    if count:
        codes = ", ".join(RECOVERED_COM_CODES)
        at = last_write.strftime("%H:%M:%S")
        if count == 1:
            text = f"1 excepción de COM recuperada ({codes}, a las {at}); no es un cierre"
        else:
            text = (
                f"{count} excepciones de COM recuperadas ({codes}; la última, a las {at}); "
                "no son un cierre"
            )
        logger.info("Volcado: {} de la aplicación", text)
    return count


def _count_recovered_exceptions(text: str) -> int:
    """Cuántos volcados trae 'text' si TODOS son de excepciones recuperadas; si no, 0.

    Cada volcado de 'faulthandler' empieza con una línea de _DUMP_HEADERS; uno recuperado,
    con «Windows fatal exception: code <código>» y un código de RECOVERED_COM_CODES. Un
    texto que no sea de volcados (p. ej. cortado o escrito por otro) cuenta como «algo
    más»: 0.
    """
    recovered = {f"Windows fatal exception: code {code}" for code in RECOVERED_COM_CODES}
    headers = [line.strip() for line in text.splitlines() if line.startswith(_DUMP_HEADERS)]
    if not headers or any(header not in recovered for header in headers):
        return 0
    # Antes del primer volcado no puede haber nada
    if not text.lstrip().startswith(_DUMP_HEADERS):
        return 0
    return len(headers)


def _cleanup_empty_crash_files(log_dir: Path, app_name: str) -> None:
    """Borra los volcados vacíos de sesiones anteriores (terminaron sin ningún error fatal).

    Los que tienen algo se conservan (cuentan entre los MAX_LOG_FILES de
    '_cleanup_old_logs'). El de una instancia que sigue abierta no se borra: en Windows,
    porque su archivo está abierto (el borrado falla y se ignora); en macOS y Linux,
    porque se comprueba que su proceso ya no existe. Nunca lanza excepciones.
    """
    try:
        candidates = list(log_dir.glob(f"{app_name}_*{CRASH_SUFFIX}"))
    except OSError:
        return

    for path in candidates:
        try:
            if path.stat().st_size == 0 and not _crash_owner_alive(path, app_name):
                path.unlink()
        except OSError:
            # En uso por otra instancia (Windows), ya borrado o sin permisos: se ignora
            pass


def _crash_owner_alive(crash_path: Path, app_name: str) -> bool:
    """En macOS y Linux, si sigue en marcha el proceso de un volcado (el PID de su nombre).

    En Windows devuelve siempre False: allí 'os.kill' no sirve para preguntar (TERMINA el
    proceso), y no hace falta, porque el archivo de una instancia abierta no se puede borrar.
    """
    if sys.platform == "win32":
        return False
    pid_text = crash_path.name.removeprefix(f"{app_name}_").removesuffix(CRASH_SUFFIX)
    if not pid_text.isdigit():
        return False
    try:
        os.kill(int(pid_text), 0)  # la señal 0 no hace nada: solo comprueba que existe
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existe, aunque sea de otro usuario
    return True
