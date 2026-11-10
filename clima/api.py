"""Cliente da Open-Meteo (sem chave de API)."""
import gzip
import json
import urllib.parse
import urllib.request

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = "clima-gtk/0.1"


def obter_json(url, params=None, timeout=20):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        corpo = resp.read()
    if corpo[:2] == b"\x1f\x8b":  # alguns servidores (IBGE) respondem em gzip sem pedir
        corpo = gzip.decompress(corpo)
    return json.loads(corpo)


_get = obter_json


def buscar_cidades(nome, quantidade=8):
    dados = _get(
        GEOCODING_URL,
        {"name": nome, "count": quantidade, "language": "pt", "format": "json"},
    )
    return [
        {
            "nome": r["name"],
            "regiao": ", ".join(x for x in (r.get("admin1"), r.get("country")) if x),
            "pais": r.get("country_code"),
            "lat": r["latitude"],
            "lon": r["longitude"],
        }
        for r in dados.get("results", [])
    ]


def previsao(lat, lon):
    return _get(
        FORECAST_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
            "weather_code,wind_speed_10m,is_day",
            "hourly": "temperature_2m,precipitation_probability,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max",
            "minutely_15": "precipitation",
            "forecast_minutely_15": 12,
            "forecast_days": 7,
            "timezone": "auto",
        },
    )
