"""Actividades de un track: la lista, sus textos en español y el «traductor».

Este módulo NO depende de Qt ni de la base de datos: es una lista declarativa.

La actividad de un track (senderismo, ciclismo de montaña...) se GUARDA siempre como una
CLAVE en inglés y se MUESTRA en español (decidido por el autor el 14/11/2026):

    - Lo que ya traen los GPX se entiende solo: un '<type>hiking</type>' es «Senderismo».
    - Al exportar o crear un track, su '<type>' lleva la clave: es lo que leen otros
      programas.
    - El idioma queda solo en la interfaz: el catálogo, los filtros y el '.arca.json'
      guardan la clave.

Las claves son los nombres de DEPORTE del formato FIT de Garmin donde existen ('hiking',
'walking', 'running', 'cycling', 'mountaineering', 'paddling'...). FIT no distingue, como
deportes, el ciclismo de montaña del de carretera ni la carrera de montaña (son
«subdeportes»): para esos se usan claves del mismo estilo ('mountain_biking',
'road_biking', 'trail_running'...). Los números de FIT no se usan.

'normalize_activity' es el traductor de lo que llega escrito de fuera: reconoce la clave
(con mayúsculas, espacios o guiones), las variantes habituales ('hike', 'mtb', 'ride',
'kayak'...) y el propio texto en español («Senderismo»). Lo que NO reconoce lo devuelve
tal cual.

'activity_key' es lo que se GUARDA en el catálogo: siempre una clave de la lista. Una
actividad que no se reconoce pasa a ser «Otra actividad» ('GENERIC'; decidido por el autor
el 14/11/2026: así los filtros y el desplegable solo tienen las de la lista). El texto
original sigue en el GPX.

Uso:
    normalize_activity("Hike")            # 'hiking'
    normalize_activity("mountain biking") # 'mountain_biking'
    normalize_activity("Parapente")       # 'Parapente' (no está en la lista: tal cual)
    activity_key("Parapente")             # 'generic' (lo que se guarda: «Otra actividad»)
    activity_label("hiking")              # 'Senderismo'
    activity_label("Parapente")           # 'Parapente'
    ACTIVITIES                            # la lista, en el orden del desplegable
    is_known_activity("hiking")           # True

Añadir una actividad: una línea en 'ACTIVITIES' (la clave no se cambia nunca después:
está en los catálogos y en los '.arca.json') y, si tiene variantes, en '_ALIASES'.

1.1.0 'activity_key': lo que se guarda (lo que no se reconoce, «Otra actividad»); el texto
      de 'generic' pasa de «Otra» a «Otra actividad» (paso 4.6b).
1.0.0 Primera versión (14/11/2026; docs/MOD_TRACKS.md, paso 4.6a).

Prueba rápida (desde la raíz del proyecto):
    python -m core.tracks.activities
"""

__version__ = "1.1.0"
__all__ = [
    "ACTIVITIES",
    "GENERIC",
    "Activity",
    "activity_key",
    "activity_label",
    "is_known_activity",
    "normalize_activity",
]

# Librerías estándar
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Activity:
    """Una actividad de la lista.

    Attributes:
        key: Clave estable, en inglés (lo que se guarda y lo que va al '<type>' del GPX).
        label: Texto para el usuario.
    """

    key: str
    label: str


# Clave de «Otra actividad»: una actividad que no es ninguna de la lista
GENERIC = "generic"

# La lista, en el orden del desplegable: a pie, en bici, en la nieve, en el agua, a motor
ACTIVITIES: tuple[Activity, ...] = (
    Activity("hiking", "Senderismo"),
    Activity("walking", "Caminata"),
    Activity("running", "Carrera"),
    Activity("trail_running", "Carrera de montaña"),
    Activity("mountaineering", "Alpinismo"),
    Activity("rock_climbing", "Escalada"),
    Activity("cycling", "Ciclismo"),
    Activity("road_biking", "Ciclismo de carretera"),
    Activity("mountain_biking", "Ciclismo de montaña"),
    Activity("gravel_cycling", "Gravel"),
    Activity("e_biking", "Bicicleta eléctrica"),
    Activity("backcountry_skiing", "Esquí de travesía"),
    Activity("cross_country_skiing", "Esquí de fondo"),
    Activity("snowshoeing", "Raquetas de nieve"),
    Activity("paddling", "Piragua / remo"),
    Activity("swimming", "Natación"),
    Activity("driving", "Coche"),
    Activity("motorcycling", "Moto"),
    Activity(GENERIC, "Otra actividad"),
)

_LABELS: dict[str, str] = {activity.key: activity.label for activity in ACTIVITIES}

# Otras formas de escribir cada actividad que se encuentran en los GPX (ya «aplanadas»:
# en minúsculas, sin acentos y con '_' en lugar de espacios y guiones) -> su clave
_ALIASES: dict[str, str] = {
    "hike": "hiking",
    "trekking": "hiking",
    "trek": "hiking",
    "walk": "walking",
    "run": "running",
    "jogging": "running",
    "trail_run": "trail_running",
    "trail": "trail_running",
    "alpinism": "mountaineering",
    "mountaineer": "mountaineering",
    "climbing": "rock_climbing",
    "climb": "rock_climbing",
    "ride": "cycling",
    "bike": "cycling",
    "biking": "cycling",
    "bicycle": "cycling",
    "bicycling": "cycling",
    "road_cycling": "road_biking",
    "road_bike": "road_biking",
    "road": "road_biking",
    "mountain_bike": "mountain_biking",
    "mountain_cycling": "mountain_biking",
    "mtb": "mountain_biking",
    "btt": "mountain_biking",
    "gravel": "gravel_cycling",
    "gravel_biking": "gravel_cycling",
    "gravel_bike": "gravel_cycling",
    "ebike": "e_biking",
    "e_bike": "e_biking",
    "ebiking": "e_biking",
    "ski_touring": "backcountry_skiing",
    "backcountry_ski": "backcountry_skiing",
    "nordic_skiing": "cross_country_skiing",
    "xc_skiing": "cross_country_skiing",
    "cross_country_ski": "cross_country_skiing",
    "snowshoe": "snowshoeing",
    "kayak": "paddling",
    "kayaking": "paddling",
    "canoe": "paddling",
    "canoeing": "paddling",
    "rowing": "paddling",
    "paddle": "paddling",
    "swim": "swimming",
    "car": "driving",
    "drive": "driving",
    "motorbike": "motorcycling",
    "motorcycle": "motorcycling",
    "other": GENERIC,
    "unknown": GENERIC,
}


def _flatten(text: str) -> str:
    """Un texto «aplanado» para compararlo: minúsculas, sin acentos, y con '_' en lugar de
    espacios, guiones y barras (y sin '_' repetidos ni en los extremos)."""
    plain = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    words = "".join(char if char.isalnum() else " " for char in plain).split()
    return "_".join(words)


# Los textos en español, aplanados -> su clave (para reconocer «Senderismo» escrito a mano)
_BY_LABEL: dict[str, str] = {_flatten(activity.label): activity.key for activity in ACTIVITIES}


def normalize_activity(text: object) -> str | None:
    """La clave de una actividad escrita de cualquier forma (ver el docstring del archivo).

    Returns:
        La clave de la lista si se reconoce; el mismo texto (sin espacios en los extremos)
        si no; None si no es un texto o está vacío.
    """
    if not isinstance(text, str):
        return None
    value = text.strip()
    if not value:
        return None
    flat = _flatten(value)
    if flat in _LABELS:
        return flat
    return _ALIASES.get(flat) or _BY_LABEL.get(flat) or value


def activity_key(text: object) -> str | None:
    """La clave que se GUARDA de una actividad: la de la lista si se reconoce; 'GENERIC'
    («Otra actividad») si es un texto que no se reconoce; None si no hay actividad."""
    key = normalize_activity(text)
    if key is None:
        return None
    return key if key in _LABELS else GENERIC


def is_known_activity(value: object) -> bool:
    """True si es (o se reconoce como) una actividad de la lista."""
    return normalize_activity(value) in _LABELS


def activity_label(value: object) -> str:
    """El texto para el usuario de una actividad: el de la lista si se reconoce; si no, el
    texto tal cual; vacío si no hay actividad."""
    key = normalize_activity(value)
    if key is None:
        return ""
    return _LABELS.get(key, key)


if __name__ == "__main__":
    # Autoprueba (sin Qt). Desde la raíz del proyecto:  python -m core.tracks.activities

    keys = [activity.key for activity in ACTIVITIES]
    # La lista: claves únicas, ya «aplanadas» (lo que se guarda es lo que se compara)
    assert len(set(keys)) == len(keys) and all(key == _flatten(key) for key in keys)
    assert len({activity.label for activity in ACTIVITIES}) == len(ACTIVITIES)
    assert keys[0] == "hiking" and keys[-1] == GENERIC
    # Las variantes apuntan a claves que existen y no pisan ninguna clave
    assert set(_ALIASES.values()) <= set(keys) and not set(_ALIASES) & set(keys)
    assert all(alias == _flatten(alias) for alias in _ALIASES)

    # --- La clave, escrita de cualquier manera
    for written in ("hiking", "Hiking", " HIKING ", "hiking\n"):
        assert normalize_activity(written) == "hiking", written
    assert normalize_activity("mountain biking") == "mountain_biking"
    assert normalize_activity("Mountain-Biking") == "mountain_biking"
    assert normalize_activity("trail_running") == normalize_activity("Trail Running") == "trail_running"
    # --- Variantes habituales
    for written, key in (("hike", "hiking"), ("Walk", "walking"), ("Run", "running"),
                         ("MTB", "mountain_biking"), ("Ride", "cycling"), ("E-Bike", "e_biking"),
                         ("kayak", "paddling"), ("Ski touring", "backcountry_skiing"),
                         ("other", "generic")):  # fmt: skip
        assert normalize_activity(written) == key, written
    # --- El texto en español (con o sin acentos y mayúsculas)
    assert normalize_activity("Senderismo") == "hiking"
    assert normalize_activity("ciclismo de montana") == "mountain_biking"
    assert normalize_activity("ESQUÍ DE TRAVESÍA") == "backcountry_skiing"
    assert normalize_activity("Piragua / remo") == "paddling"
    # --- Lo que no se reconoce no se pierde: tal cual (sin los espacios de los extremos)
    assert normalize_activity("  Parapente ") == "Parapente"
    assert normalize_activity("9") == "9"
    # --- Sin actividad
    for nothing in (None, "", "   ", 7, ["hiking"]):
        assert normalize_activity(nothing) is None, nothing

    # --- Lo que se muestra
    assert activity_label("hiking") == "Senderismo" and activity_label("Hike") == "Senderismo"
    assert activity_label("mountain_biking") == "Ciclismo de montaña"
    assert activity_label("generic") == "Otra actividad"
    # Lo que se guarda: siempre una clave de la lista
    assert activity_key("Hike") == "hiking" and activity_key("mountain_biking") == "mountain_biking"
    assert activity_key("Parapente") == GENERIC and activity_key("9") == GENERIC
    assert activity_key(None) is None and activity_key("  ") is None
    assert activity_label("Parapente") == "Parapente" and activity_label(None) == ""
    assert is_known_activity("MTB") and is_known_activity("Senderismo")
    assert not is_known_activity("Parapente") and not is_known_activity(None)
    # Normalizar dos veces da lo mismo (lo guardado se puede volver a normalizar)
    for written in ("Hike", "Parapente", "ciclismo de montaña", "generic"):
        once = normalize_activity(written)
        assert normalize_activity(once) == once, written

    print("Autoprueba finalizada correctamente.")
