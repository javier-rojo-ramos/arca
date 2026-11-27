"""Página «Música» de la ventana de opciones: la etiqueta preferida de los MP3.

    Etiquetas de los MP3
        (•) ID3v2.3 UTF-16      ( ) ID3v2.4 UTF-8
            La versión de la etiqueta que se crea en las canciones que no tienen ID3v2...
        [ ] Crear también ID3v1
            Junto al ID3v2 nuevo. Es una etiqueta antigua y limitada...

- La etiqueta preferida (docs/MOD_MUSICA.md §5, acordado con el autor el 27/11/2026, a la
  vista de su configuración de Mp3tag) es la que se crea en un MP3 al que le falta el ID3v2
  y la que dejará la herramienta «Reescribir etiquetas…» (MUS 8.4; la página la nombrará
  cuando exista). Al editar una canción que ya tiene etiquetas, se escriben en las que
  tiene: esta opción no las cambia.
- Cada opción, con su ayuda debajo (la variante C de tres que vio el autor el 27/11/2026):
  una sola ayuda bajo la casilla se leía como si fuera del ID3v1.
- La versión lleva su codificación, como en Mp3tag (v2.3, UTF-16; v2.4, UTF-8); la
  «ID3v2.3 ISO-8859-1» de Mp3tag no se ofrece (no cabe cualquier carácter).
- De partida, ID3v2.3 y sin ID3v1 ('tag_set.DEFAULT_MP3_TAGS'). Lo guardado se lee con
  'tag_set.mp3_tags_from_settings', que también usará el trabajo de escritura (MUS 6.2): lo
  que no valga, la de partida.
- Como el resto de la ventana, se guarda al pulsar «Aceptar» ('save'), y solo lo que
  cambia: settings.json, 'audio_id3_version' (3 o 4) y 'audio_include_id3v1'. Hasta MUS 6.2
  no tiene efecto (nada escribe todavía en las canciones).

1.0.0 Primera versión (27/11/2026; docs/MOD_MUSICA.md, paso MUS 6.1d). Textos acordados con
      el autor (la variante C).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.dialogs.music_settings_page
La página se ve en la prueba de la ventana de opciones ('settings_dialog', abre una ventana).
"""

__version__ = "1.0.0"
__all__ = ["MusicSettingsPage"]

# Librerías estándar
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtWidgets import QButtonGroup, QCheckBox, QHBoxLayout, QLabel, QRadioButton, QWidget

# Módulos del proyecto
from config.app_constants import SETTING_AUDIO_ID3_VERSION, SETTING_AUDIO_INCLUDE_ID3V1, AppIcons
from core.audio.tag_set import TagSet, mp3_tags_from_settings
from ui_helpers.dialogs.settings_dialog import SettingsPage
from ui_helpers.helpers.theme_fonts import rich_text

# Textos de la página (acordados con el autor el 27/11/2026: la variante C)
_TAGS_TITLE = "Etiquetas de los MP3"
# Cada versión de ID3v2 que se ofrece, con su codificación (los nombres de Mp3tag)
_VERSION_LABELS: dict[int, str] = {3: "ID3v2.3 UTF-16", 4: "ID3v2.4 UTF-8"}
_VERSION_HELP = (
    "La versión de la etiqueta que se crea en las canciones que no tienen ID3v2. Las que ya "
    "lo tienen conservan su versión: al editarlas, solo cambia lo editado."
)
_INCLUDE_ID3V1 = "Crear también ID3v1"
_ID3V1_HELP = (
    "Junto al ID3v2 nuevo. Es una etiqueta antigua y limitada (30 caracteres por campo), "
    "solo para reproductores muy antiguos. Si una canción ya tiene ID3v1, se mantiene al día."
)


class MusicSettingsPage(SettingsPage):
    """Sección «Música»: la etiqueta preferida de los MP3 (ver el docstring del archivo)."""

    title = "Música"
    icon = AppIcons.LIB_AUDIO

    def __init__(self, config: Any, context: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(config, context, parent)

        # --- Etiquetas de los MP3 ---
        self.body.addWidget(QLabel(rich_text(f"<b>{_TAGS_TITLE}</b>")))
        # Los botones de la versión, con la versión como id ('checkedId')
        self.group_version = QButtonGroup(self)
        version_row = QHBoxLayout()
        for version, label in _VERSION_LABELS.items():
            button = QRadioButton(label)
            self.group_version.addButton(button, version)
            version_row.addWidget(button)
        version_row.addStretch(1)
        self.body.addLayout(version_row)
        # Cada opción, con su ayuda justo debajo (alineada con el texto del botón)
        self.body.addWidget(self.make_help_label(_VERSION_HELP))
        self.check_id3v1 = QCheckBox(_INCLUDE_ID3V1)
        self.body.addWidget(self.check_id3v1)
        self.body.addWidget(self.make_help_label(_ID3V1_HELP))

    def chosen_tags(self) -> TagSet:
        """La etiqueta preferida que dicen los controles."""
        return TagSet(id3v2=self.group_version.checkedId(), id3v1=self.check_id3v1.isChecked())

    def _saved_tags(self) -> TagSet:
        """La etiqueta preferida guardada (lo que no valga, la de partida)."""
        return mp3_tags_from_settings(
            self.config.get(SETTING_AUDIO_ID3_VERSION), self.config.get(SETTING_AUDIO_INCLUDE_ID3V1)
        )

    # --- Cargar y guardar ---

    def load(self) -> None:
        tags = self._saved_tags()
        self.group_version.button(tags.id3v2).setChecked(True)
        self.check_id3v1.setChecked(tags.id3v1)

    def save(self) -> set[str]:
        changed: set[str] = set()
        saved, chosen = self._saved_tags(), self.chosen_tags()
        if chosen.id3v2 != saved.id3v2:
            self.config.set(SETTING_AUDIO_ID3_VERSION, chosen.id3v2)
            changed.add(SETTING_AUDIO_ID3_VERSION)
        if chosen.id3v1 != saved.id3v1:
            self.config.set(SETTING_AUDIO_INCLUDE_ID3V1, chosen.id3v1)
            changed.add(SETTING_AUDIO_INCLUDE_ID3V1)
        return changed


if __name__ == "__main__":
    # Autoprueba sin ventana: la página con una configuración en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.dialogs.music_settings_page
    import sys

    from qtpy.QtWidgets import QApplication

    from core.audio.tag_set import DEFAULT_MP3_TAGS

    app = QApplication.instance() or QApplication(sys.argv[:1])

    class _Config(dict):
        def set(self, key: str, value: Any) -> None:
            self[key] = value

    # --- Sin nada guardado: ID3v2.3 sin ID3v1; «Aceptar» sin tocar nada no guarda nada
    config = _Config()
    page = MusicSettingsPage(config, {})
    page.load()
    assert page.chosen_tags() == DEFAULT_MP3_TAGS
    assert page.group_version.button(3).isChecked() and not page.check_id3v1.isChecked()
    assert [button.text() for button in page.group_version.buttons()] == [
        "ID3v2.3 UTF-16", "ID3v2.4 UTF-8"
    ]  # fmt: skip
    assert page.check_id3v1.text() == "Crear también ID3v1"
    assert page.title == "Música" and page.save() == set() and config == {}

    # --- Otra versión y con ID3v1: se guardan las dos; otra vez, nada
    page.group_version.button(4).setChecked(True)
    assert not page.group_version.button(3).isChecked()  # solo uno a la vez
    page.check_id3v1.setChecked(True)
    assert page.save() == {SETTING_AUDIO_ID3_VERSION, SETTING_AUDIO_INCLUDE_ID3V1}
    assert config == {SETTING_AUDIO_ID3_VERSION: 4, SETTING_AUDIO_INCLUDE_ID3V1: True}
    assert page.save() == set()

    # --- Abrir de nuevo: lo guardado; volver a lo de partida se guarda (un 3 y un no)
    page = MusicSettingsPage(config, {})
    page.load()
    assert page.chosen_tags() == TagSet(id3v2=4, id3v1=True)
    page.group_version.button(3).setChecked(True)
    page.check_id3v1.setChecked(False)
    assert page.save() == {SETTING_AUDIO_ID3_VERSION, SETTING_AUDIO_INCLUDE_ID3V1}
    assert config == {SETTING_AUDIO_ID3_VERSION: 3, SETTING_AUDIO_INCLUDE_ID3V1: False}

    # --- Algo raro guardado: la de partida, sin errores (y «Aceptar» no lo toca)
    odd = _Config({SETTING_AUDIO_ID3_VERSION: "4", SETTING_AUDIO_INCLUDE_ID3V1: "sí"})
    page = MusicSettingsPage(odd, {})
    page.load()
    assert page.chosen_tags() == DEFAULT_MP3_TAGS and page.save() == set()
    print("Autoprueba finalizada correctamente.")
