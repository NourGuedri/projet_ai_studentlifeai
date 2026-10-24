"""Météo du jour via Open-Meteo (gratuit, sans clé API) : https://open-meteo.com"""
import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CODES = {
    0: "Ciel dégagé", 1: "Plutôt dégagé", 2: "Partiellement nuageux", 3: "Couvert",
    45: "Brouillard", 48: "Brouillard givrant",
    51: "Bruine légère", 53: "Bruine", 55: "Bruine dense", 56: "Bruine verglaçante", 57: "Bruine verglaçante",
    61: "Pluie légère", 63: "Pluie", 65: "Forte pluie", 66: "Pluie verglaçante", 67: "Pluie verglaçante",
    71: "Neige légère", 73: "Neige", 75: "Forte neige", 77: "Grains de neige",
    80: "Averses légères", 81: "Averses", 82: "Fortes averses", 85: "Averses de neige", 86: "Fortes averses de neige",
    95: "Orage", 96: "Orage avec grêle", 99: "Orage avec forte grêle",
}
WET_CODES = set(range(51, 68)) | set(range(71, 78)) | {80, 81, 82, 85, 86, 95, 96, 99}


class WeatherError(Exception):
    pass


def get_weather(city: str) -> dict:
    try:
        geo = requests.get(GEOCODE_URL, params={"name": city, "count": 1, "language": "fr"}, timeout=8)
        geo.raise_for_status()
        results = geo.json().get("results")
        if not results:
            raise WeatherError(f"Ville introuvable : « {city} ».")
        place = results[0]
        resp = requests.get(FORECAST_URL, timeout=8, params={
            "latitude": place["latitude"], "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,precipitation,weather_code",
            "timezone": "auto"})
        resp.raise_for_status()
        cur = resp.json()["current"]
    except WeatherError:
        raise
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise WeatherError("Impossible de récupérer la météo pour le moment.") from exc

    code = int(cur.get("weather_code", 0))
    return {
        "city": place["name"],
        "country": place.get("country", ""),
        "temp": round(cur["temperature_2m"]),
        "feels_like": round(cur.get("apparent_temperature", cur["temperature_2m"])),
        "rain": code in WET_CODES or (cur.get("precipitation") or 0) > 0,
        "description": CODES.get(code, "Météo variable"),
        "code": code,
    }
