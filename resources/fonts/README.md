# Arca Media — fuente de la aplicación

La aplicación usa **Inter** en toda la interfaz, para que se vea igual en Windows, macOS y
Linux (decidido el 24/11/2026: [DECISIONES.md](../../docs/DECISIONES.md); fase `GEN 21`, en
[HISTORIAL.md](../../docs/HISTORIAL.md); la regla, en [CLAUDE.md](../../CLAUDE.md)). La registra y la aplica
`ui_helpers/helpers/theme_fonts.py`, que también fija los tamaños, en px.

## Contenido

```
Inter-Regular.ttf     El texto normal.
Inter-SemiBold.ttf    La negrita (la Bold de Inter queda pesada a 12 px).
Inter-Italic.ttf      La cursiva (la de los textos de ayuda, <i>).
LICENSE.txt           SIL Open Font License 1.1: permite incluirla en la aplicación.
```

Origen: Inter 4.1, el paquete oficial (<https://github.com/rsms/inter/releases>,
`Inter-4.1.zip`, carpeta `extras/ttf/`). Solo las que se usan. Si se pide
`setBold(True)` (700), Qt elige la SemiBold, la más cercana. La cursiva va incluida para
que se vea igual en todos los sistemas: sin ella, cada uno inclinaría la Regular a su
manera.

Se leen del disco (no van en `recursos.qrc`): el empaquetado tiene que incluir esta carpeta
(`GEN 5`).
