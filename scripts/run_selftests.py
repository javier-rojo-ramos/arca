"""Ejecuta de una vez todas las autopruebas del proyecto que no abren una ventana.

Cada módulo con lógica comprobable lleva su autoprueba en 'if __name__ == "__main__":', que
termina imprimiendo «Autoprueba finalizada correctamente.» (CLAUDE.md). Este guion las busca,
lanza cada una en su propio proceso ('python -m paquete.modulo', varias a la vez) y dice
cuáles han fallado. Es la red de seguridad antes y después de una refactorización
(docs/PENDIENTE.md, GEN 11).

Cómo las encuentra: recorre 'config/', 'controllers/', 'core/' y 'ui_helpers/' y se queda con
los '.py' que tienen el bloque '__main__' y el texto de fin de la autoprueba. No hay una lista
que mantener: una autoprueba nueva entra sola.

Las que se saltan ('WINDOWED'): las que abren una ventana y se quedan esperando a que alguien
la cierre (docs/PRUEBAS.md). ► Si una autoprueba nueva abre una ventana, añádela ahí. Por si
alguna se cuela, cada una tiene un tiempo máximo ('--timeout'): al pasarlo se cierra y cuenta
como fallo.

Una autoprueba se da por buena si su proceso termina con código 0 Y su salida contiene el
texto de fin. Las que dependen de lo instalado (ExifTool, pillow-heif) pueden fallar en un
equipo que no lo tenga: el resumen enseña el final de su salida para verlo.

Uso (desde la raíz del proyecto, con el Python de .venv):
    python scripts/run_selftests.py                 # todas
    python scripts/run_selftests.py core.tracks     # solo las que contienen ese texto
    python scripts/run_selftests.py --list          # qué ejecutaría, sin ejecutar nada
    python scripts/run_selftests.py -j 2 --timeout 300

Termina con código 0 si todas pasan y 1 si alguna falla.

1.0.0 Primera versión (16/11/2026).
"""

__version__ = "1.0.0"
__all__ = ["EXTRA_ARGS", "WINDOWED", "SelfTestResult", "discover", "main", "run_all", "run_one"]

# Librerías estándar
import argparse
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

# Raíz del proyecto (este archivo está en 'scripts/')
ROOT = Path(__file__).resolve().parent.parent

# Carpetas en las que se buscan autopruebas
PACKAGES: tuple[str, ...] = ("config", "controllers", "core", "ui_helpers")

# Texto con el que termina toda autoprueba (sin el punto final: alguna lo omite)
DONE_TEXT = "Autoprueba finalizada correctamente"
_MAIN_MARKS = ('if __name__ == "__main__":', "if __name__ == '__main__':")

# Autopruebas que abren una ventana y esperan a que alguien la cierre (docs/PRUEBAS.md):
# no se ejecutan aquí; las lanza el autor a mano
WINDOWED: dict[str, str] = {
    "ui_helpers.dialogs.folder_content_dialog": "abre la ventana «¿Qué contiene esta carpeta?»",
    "ui_helpers.dialogs.map_layer_dialog": "abre la ventana «Añadir capa»",
    "ui_helpers.dialogs.remove_dialog": "abre la ventana «Eliminar»",
    "ui_helpers.dialogs.settings_dialog": "abre la ventana de opciones",
    "ui_helpers.helpers.theme_style": "termina con una ventana con todos los estados",
    "ui_helpers.widgets.organize_bar": "termina con la barra en una ventana",
}

# Autopruebas que se piden con un argumento (sin él, el módulo hace otra cosa)
EXTRA_ARGS: dict[str, tuple[str, ...]] = {
    "core.metadata.inspect_cli": ("--autoprueba",),  # sin argumentos pide un archivo
}

DEFAULT_TIMEOUT_S = 180
_TAIL_LINES = 25  # líneas del final de la salida que se enseñan de una que falla

OK = "ok"
FAILED = "fallo"
TIMED_OUT = "tiempo"


@dataclass(frozen=True, slots=True)
class SelfTestResult:
    """Cómo ha ido una autoprueba.

    Attributes:
        module: Nombre del módulo ('core.tracks.profile').
        status: OK, FAILED (código distinto de 0 o sin el texto de fin) o TIMED_OUT.
        seconds: Lo que ha tardado.
        output: Su salida completa (la normal y la de errores, juntas).
        exit_code: Código de salida del proceso (None si se cerró por tiempo).
    """

    module: str
    status: str
    seconds: float
    output: str
    exit_code: int | None


def discover(root: Path = ROOT, packages: Sequence[str] = PACKAGES) -> list[str]:
    """Los módulos con autoprueba, por orden alfabético (también los de 'WINDOWED')."""
    found: list[str] = []
    for package in packages:
        for path in sorted((root / package).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue  # un archivo ilegible no tiene autoprueba que lanzar
            if DONE_TEXT in text and any(mark in text for mark in _MAIN_MARKS):
                found.append(".".join(path.relative_to(root).with_suffix("").parts))
    return found


def run_one(module: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> SelfTestResult:
    """Ejecuta una autoprueba en su propio proceso y dice cómo ha ido."""
    # La salida, siempre en UTF-8: las autopruebas imprimen flechas y otros caracteres que
    # la consola de Windows (cp1252) no admite al redirigirla
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    start = time.monotonic()
    try:
        done = subprocess.run(  # la orden la arma este guion, no un texto de fuera
            [sys.executable, "-m", module, *EXTRA_ARGS.get(module, ())],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        output = (error.stdout or b"").decode("utf-8", errors="replace")
        return SelfTestResult(module, TIMED_OUT, time.monotonic() - start, output, None)
    output = done.stdout.decode("utf-8", errors="replace")
    passed = done.returncode == 0 and DONE_TEXT in output
    return SelfTestResult(
        module, OK if passed else FAILED, time.monotonic() - start, output, done.returncode
    )


def run_all(
    modules: Sequence[str],
    *,
    jobs: int,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    on_result: Callable[[SelfTestResult], None] | None = None,
) -> list[SelfTestResult]:
    """Ejecuta varias autopruebas, 'jobs' a la vez; devuelve los resultados por módulo."""
    results: list[SelfTestResult] = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = [pool.submit(run_one, module, timeout_s) for module in modules]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if on_result is not None:
                on_result(result)
    return sorted(results, key=lambda result: result.module)


def _print_result(result: SelfTestResult) -> None:
    label = {OK: "ok    ", FAILED: "FALLO ", TIMED_OUT: "TIEMPO"}[result.status]
    print(f"  {label} {result.module}  ({result.seconds:.1f} s)", flush=True)


def _print_failure(result: SelfTestResult, timeout_s: float) -> None:
    if result.status == TIMED_OUT:
        reason = f"no ha terminado en {timeout_s:.0f} s (¿abre una ventana? Ver 'WINDOWED')"
    elif result.exit_code != 0:
        reason = f"código de salida {result.exit_code}"
    else:
        reason = f"ha terminado sin imprimir «{DONE_TEXT}»"
    print(f"\n--- {result.module}: {reason}")
    tail = result.output.rstrip().splitlines()[-_TAIL_LINES:]
    print("\n".join(f"    {line}" for line in tail) if tail else "    (sin salida)")


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada: devuelve el código de salida (0 = todas bien)."""
    parser = argparse.ArgumentParser(description="Ejecuta las autopruebas que no abren ventana.")
    parser.add_argument("filters", nargs="*", help="solo los módulos que contienen alguno de estos textos")
    parser.add_argument("-j", "--jobs", type=int, default=min(4, os.cpu_count() or 2),
                        help="autopruebas a la vez (por defecto, hasta 4)")  # fmt: skip
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S,
                        help=f"segundos como mucho por autoprueba (por defecto, {DEFAULT_TIMEOUT_S})")  # fmt: skip
    parser.add_argument("--list", action="store_true", help="enseña qué ejecutaría, sin ejecutar nada")
    args = parser.parse_args(argv)

    # La consola de Windows puede no admitir «» o las tildes al redirigir la salida
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    found = discover()
    if args.filters:
        found = [module for module in found if any(text in module for text in args.filters)]
    skipped = [module for module in found if module in WINDOWED]
    modules = [module for module in found if module not in WINDOWED]

    if args.list:
        for module in modules:
            print(module)
        for module in skipped:
            print(f"{module}    (no se ejecuta: {WINDOWED[module]})")
        print(f"\n{len(modules)} autopruebas; {len(skipped)} con ventana, que no se ejecutan.")
        return 0

    if not modules:
        print("No hay ninguna autoprueba que ejecutar con ese filtro.")
        return 1

    print(f"{len(modules)} autopruebas, {max(1, args.jobs)} a la vez:", flush=True)
    start = time.monotonic()
    results = run_all(modules, jobs=args.jobs, timeout_s=args.timeout, on_result=_print_result)
    failures = [result for result in results if result.status != OK]

    for result in failures:
        _print_failure(result, args.timeout)

    print(f"\n{len(results) - len(failures)} bien, {len(failures)} con fallo, "
          f"{len(skipped)} con ventana sin ejecutar ({time.monotonic() - start:.0f} s).")  # fmt: skip
    if failures:
        print("Han fallado: " + ", ".join(result.module for result in failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
