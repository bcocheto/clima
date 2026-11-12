"""Lógica pura sobre a resposta da Open-Meteo (sem GTK, fácil de testar)."""
from datetime import date, datetime

_DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def horas_seguintes(dados, n=24):
    """Lista de (HH:MM, temperatura, prob. de chuva %, código do tempo) a partir da hora atual."""
    inicio = dados["current"]["time"][:13] + ":00"
    h = dados["hourly"]
    saida = []
    for t, temp, prob, cod in zip(
        h["time"], h["temperature_2m"], h["precipitation_probability"], h["weather_code"]
    ):
        if t >= inicio:
            saida.append((t[11:16], temp, prob or 0, cod))
            if len(saida) == n:
                break
    return saida


def dias(dados):
    d = dados["daily"]
    return [
        {"data": date.fromisoformat(t), "codigo": c, "max": mx, "min": mn, "chuva": p or 0}
        for t, c, mx, mn, p in zip(
            d["time"],
            d["weather_code"],
            d["temperature_2m_max"],
            d["temperature_2m_min"],
            d["precipitation_probability_max"],
        )
    ]


def nome_dia(indice, data):
    if indice == 0:
        return "Hoje"
    if indice == 1:
        return "Amanhã"
    return _DIAS[data.weekday()]


def chuva_em_minutos(dados, limiar_mm=0.1, janela_min=120):
    """Minutos até a próxima chuva (0 = já chovendo) ou None se não houver na janela.

    Na Open-Meteo, cada passo de minutely_15 é a soma dos 15 min anteriores.
    """
    m = dados.get("minutely_15")
    if not m:
        return None
    agora = datetime.fromisoformat(dados["current"]["time"])
    for t, mm in zip(m["time"], m["precipitation"]):
        delta = (datetime.fromisoformat(t) - agora).total_seconds() / 60
        if delta < 0:
            continue
        if delta > janela_min:
            break
        if (mm or 0) >= limiar_mm:
            minutos = int(max(0, delta - 15))
            if minutos == 0 and dados.get("ajuste", {}).get("chovendo") is False:
                continue  # o modelo diz que chove agora, mas o consenso/radar/METAR dizem que não
            return minutos
    return None
