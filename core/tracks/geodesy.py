"""Distancias sobre la Tierra: el ÚNICO sitio donde se calculan.

Este módulo NO depende de Qt ni de la base de datos. Lo usan el lector de GPX
('core/metadata/track/gpx_reader.py': distancia de un track) y la simplificación de
recorridos ('simplify.py'); más adelante, el perfil de elevación y la correlación de
fotos con un track (docs/MAPA.md). Así todos dicen la misma distancia.

La Tierra se toma como una esfera (fórmula del haversine), como Wikiloc, Strava o Garmin:
en un track, el error frente al elipsoide es de unas décimas por ciento y siempre en el
mismo sentido. Sin la altitud (distancia en 2D).

1.0.0 Primera versión (docs/MAPA.md, paso 2.1): 'haversine_m', que antes estaba dentro
      de 'gpx_reader.py' (mismo cálculo y mismo radio: las distancias no cambian).

Prueba rápida (desde la raíz del proyecto):
    python -m core.tracks.geodesy
"""

__version__ = "1.0.0"
__all__ = ["EARTH_RADIUS_M", "haversine_m"]

# Librerías estándar
import math

# Radio medio de la Tierra (metros), el habitual para la fórmula del haversine
EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en metros entre dos puntos (en grados), sobre una esfera."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


if __name__ == "__main__":
    # Autoprueba. Ejecutar desde la raíz del proyecto:  python -m core.tracks.geodesy

    # Un grado de latitud: unos 111,2 km en cualquier sitio
    assert abs(haversine_m(42.0, 0.0, 43.0, 0.0) - 111_195) < 1
    # Un grado de longitud se acorta con la latitud (cos 60° = 0,5)
    assert abs(haversine_m(60.0, 0.0, 60.0, 1.0) - 111_195 * 0.5) < 50
    # Simétrica, cero en el mismo punto y sin errores en las antípodas
    assert haversine_m(42.6, 0.03, 42.7, 0.1) == haversine_m(42.7, 0.1, 42.6, 0.03)
    assert haversine_m(42.6, 0.03, 42.6, 0.03) == 0
    assert abs(haversine_m(0, 0, 0, 180) - math.pi * EARTH_RADIUS_M) < 1
    # Madrid - Barcelona, unos 505 km
    assert 500_000 < haversine_m(40.4168, -3.7038, 41.3874, 2.1686) < 510_000
    print("Autoprueba finalizada correctamente.")
