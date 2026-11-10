"""Códigos WMO da Open-Meteo -> descrição em pt-BR e ícone simbólico do Adwaita."""

_WMO = {
    0: ("Céu limpo", "weather-clear"),
    1: ("Predominantemente limpo", "weather-few-clouds"),
    2: ("Parcialmente nublado", "weather-few-clouds"),
    3: ("Nublado", "weather-overcast"),
    45: ("Neblina", "weather-fog"),
    48: ("Neblina com geada", "weather-fog"),
    51: ("Garoa leve", "weather-showers-scattered"),
    53: ("Garoa", "weather-showers-scattered"),
    55: ("Garoa intensa", "weather-showers-scattered"),
    56: ("Garoa congelante", "weather-showers-scattered"),
    57: ("Garoa congelante intensa", "weather-showers-scattered"),
    61: ("Chuva fraca", "weather-showers"),
    63: ("Chuva", "weather-showers"),
    65: ("Chuva forte", "weather-showers"),
    66: ("Chuva congelante", "weather-showers"),
    67: ("Chuva congelante forte", "weather-showers"),
    71: ("Neve fraca", "weather-snow"),
    73: ("Neve", "weather-snow"),
    75: ("Neve forte", "weather-snow"),
    77: ("Grãos de neve", "weather-snow"),
    80: ("Pancadas de chuva fracas", "weather-showers"),
    81: ("Pancadas de chuva", "weather-showers"),
    82: ("Pancadas de chuva fortes", "weather-showers"),
    85: ("Pancadas de neve", "weather-snow"),
    86: ("Pancadas de neve fortes", "weather-snow"),
    95: ("Tempestade", "weather-storm"),
    96: ("Tempestade com granizo", "weather-storm"),
    99: ("Tempestade com granizo forte", "weather-storm"),
}


def descrever(codigo, dia=True):
    """Retorna (descrição, nome do ícone simbólico)."""
    nome, icone = _WMO.get(codigo, ("Indefinido", "weather-severe-alert"))
    if not dia and icone in ("weather-clear", "weather-few-clouds"):
        icone += "-night"
    return nome, f"{icone}-symbolic"
