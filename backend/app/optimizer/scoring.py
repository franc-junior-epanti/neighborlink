from math import asin, cos, radians, sin, sqrt


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1r, lon1r, lat2r, lon2r = map(radians, (lat1, lon1, lat2, lon2))
    delta_lat = lat2r - lat1r
    delta_lon = lon2r - lon1r
    value = sin(delta_lat / 2) ** 2 + cos(lat1r) * cos(lat2r) * sin(delta_lon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(value))


def proximity_points(distance_km: float | None) -> int:
    if distance_km is None:
        return 0
    return max(0, 20 - round(distance_km))
