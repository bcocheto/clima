"""Corrige o "agora" da Open-Meteo cruzando outros modelos, METAR de aeroportos e o radar.

O `current` da Open-Meteo vem de um modelo numérico em grade: pode errar a temperatura
em vários graus e dizer que chove quando não chove. Aqui o valor é refinado por consenso:

- temperatura: mediana de 4 modelos (ou o METAR, se houver aeroporto perto);
- chuva: só vale se pelo menos 3 de 4 modelos concordarem, ou se o radar confirmar;
- céu: nebulosidade mediana decide entre limpo, parcial e nublado.

As funções de decisão são puras (testáveis sem rede); a rede fica em `refinar`.
"""
import math
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import api

MODELOS = ("icon_seamless", "gfs_seamless", "ecmwf_ifs025")
CAMPOS_MODELO = ("temperature_2m", "relative_humidity_2m", "precipitation", "cloud_cover")
METAR_URL = "https://aviationweather.gov/api/data/metar"
LIMIAR_CHUVA_MM = 0.3  # abaixo disso é só 'traço' do modelo, ninguém sente como chuva
RAIO_METAR_KM = 80
RAIO_METAR_DECISIVO_KM = 40
CODIGOS_CHUVA = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
_COBERTURA = {"CLR": 0, "SKC": 0, "FEW": 15, "SCT": 40, "BKN": 75, "OVC": 100}
_RE_CHUVA = re.compile(r"^[+-]?(TS|SH|FZ)?(RA|DZ)|^[+-]?TS")  # VC* (vizinhança) não casa


# ---------- peças puras ----------
def distancia_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (
        math.sin((lat2 - lat1) * p / 2) ** 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    )
    return 12742 * math.asin(math.sqrt(a))


def umidade_relativa(temp, orvalho):
    """Fórmula de Magnus: umidade (%) a partir da temperatura e do ponto de orvalho."""
    def pv(t):
        return math.exp(17.625 * t / (243.04 + t))

    return max(0.0, min(100.0, 100 * pv(orvalho) / pv(temp)))


def codigo_do_ceu(nebulosidade):
    if nebulosidade < 10:
        return 0
    if nebulosidade < 30:
        return 1
    if nebulosidade < 60:
        return 2
    return 3


def parse_modelo(resposta):
    """Campos do `current` de uma resposta de modelo único (ou None se vier vazia)."""
    atual = resposta.get("current", {})
    valores = {c: atual.get(c) for c in CAMPOS_MODELO}
    return valores if any(v is not None for v in valores.values()) else None


def escolher_metar(metars, lat, lon, agora=None):
    """METAR mais próximo (até RAIO_METAR_KM) e recente (até 3 h), já interpretado."""
    agora = agora or datetime.now(timezone.utc).timestamp()
    melhor = None
    for m in metars:
        try:
            km = distancia_km(lat, lon, m["lat"], m["lon"])
            if km > RAIO_METAR_KM or agora - m["obsTime"] > 3 * 3600 or m.get("temp") is None:
                continue
        except (KeyError, TypeError):
            continue
        if melhor is None or km < melhor[0]:
            melhor = (km, m)
    if melhor is None:
        return None
    km, m = melhor
    chuva = any(_RE_CHUVA.match(t) for t in m.get("rawOb", "").split())
    dewp = m.get("dewp")
    return {
        "estacao": m.get("icaoId"),
        "nome": m.get("name") or m.get("icaoId"),
        "km": km,
        "temp": m["temp"],
        "umidade": umidade_relativa(m["temp"], dewp) if dewp is not None else None,
        "chuva": chuva,
        "nuvens": _COBERTURA.get(m.get("cover") or "", None),
    }


def consenso(atual, modelos, metar=None, radar=None):
    """Devolve o 'agora' ajustado: temperatura, umidade, sensação, código e explicação.

    atual: bloco `current` da Open-Meteo; modelos: saída de `parse_modelos`;
    metar: saída de `escolher_metar`; radar: True/False se houve eco no ponto, None se não sabe.
    """
    temps = [atual["temperature_2m"]] + [
        v["temperature_2m"] for v in modelos.values() if v["temperature_2m"] is not None
    ]
    umids = [atual["relative_humidity_2m"]] + [
        v["relative_humidity_2m"] for v in modelos.values() if v["relative_humidity_2m"] is not None
    ]
    nuvens = [atual.get("cloud_cover")] + [v["cloud_cover"] for v in modelos.values()]
    nuvens = [n for n in nuvens if n is not None]
    chuvas = [atual.get("precipitation")] + [v["precipitation"] for v in modelos.values()]
    votos = sum(1 for p in chuvas if p is not None and p >= LIMIAR_CHUVA_MM)
    tracos = sum(1 for p in chuvas if p is not None and p >= 0.1)
    total = sum(1 for p in chuvas if p is not None)

    fontes = [f"{len(temps)} modelos"] if len(temps) > 1 else []
    temp = statistics.median(temps)
    umidade = statistics.median(umids)
    nebulosidade = statistics.median(nuvens) if nuvens else None

    chovendo = votos >= 3 or (bool(radar) and tracos >= 1)
    if radar:
        fontes.append("radar")
    if metar:
        temp = metar["temp"]
        if metar["umidade"] is not None:
            umidade = metar["umidade"]
        if metar["nuvens"] is not None:
            nebulosidade = metar["nuvens"]
        fontes.append(f'METAR {metar["estacao"]} ({metar["km"]:.0f} km)')
        if metar["chuva"]:
            chovendo = True
        elif metar["km"] <= RAIO_METAR_DECISIVO_KM:
            chovendo = False

    codigo = atual["weather_code"]
    if chovendo and codigo not in CODIGOS_CHUVA:
        codigo = 61 if (nebulosidade or 100) >= 60 else 80
    elif not chovendo and codigo in CODIGOS_CHUVA:
        codigo = codigo_do_ceu(nebulosidade if nebulosidade is not None else 100)
    elif not chovendo and nebulosidade is not None and codigo in (0, 1, 2, 3):
        codigo = codigo_do_ceu(nebulosidade)

    # sensação: mantém o efeito do vento e da umidade do modelo, deslocado pela correção
    sensacao = atual["apparent_temperature"] + (temp - atual["temperature_2m"])
    return {
        "temperature_2m": round(temp, 1),
        "relative_humidity_2m": round(umidade),
        "apparent_temperature": round(sensacao, 1),
        "weather_code": codigo,
        "chovendo": chovendo,
        "votos_chuva": f"{votos}/{total}",
        "fontes": fontes,
    }


# ---------- rede ----------
def _um_modelo(lat, lon, modelo):
    resp = api.obter_json(
        api.FORECAST_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join(CAMPOS_MODELO),
            "models": modelo,  # a API só devolve `current` de um modelo por chamada
            "timezone": "auto",
        },
        timeout=10,
    )
    return parse_modelo(resp)


def modelos_atuais(lat, lon):
    """{modelo: campos} consultando os modelos em paralelo; os que falharem ficam de fora."""
    with ThreadPoolExecutor(max_workers=len(MODELOS)) as pool:
        futuros = {m: pool.submit(_tentar, _um_modelo, lat, lon, m) for m in MODELOS}
    return {m: v for m, f in futuros.items() if (v := f.result())}


def metar_proximo(lat, lon):
    d = 1.0  # ~110 km
    metars = api.obter_json(
        METAR_URL,
        {"bbox": f"{lat - d},{lon - d},{lat + d},{lon + d}", "format": "json"},
        timeout=10,
    )
    return escolher_metar(metars, lat, lon)


def _tentar(fn, *args):
    try:
        return fn(*args)
    except Exception:  # fonte extra fora do ar: o app segue com as demais
        return None


def refinar(dados, lat, lon):
    """Aplica o consenso em `dados["current"]` (guarda o original em `dados["current_modelo"]`)."""
    from . import radar

    modelos = _tentar(modelos_atuais, lat, lon) or {}
    metar = _tentar(metar_proximo, lat, lon)
    eco = _tentar(radar.eco_no_ponto, lat, lon)
    atual = dados["current"]
    ajuste = consenso(atual, modelos, metar, eco)
    dados["current_modelo"] = dict(atual)
    atual.update(
        {k: ajuste[k] for k in
         ("temperature_2m", "relative_humidity_2m", "apparent_temperature", "weather_code")}
    )
    dados["ajuste"] = {k: ajuste[k] for k in ("chovendo", "votos_chuva", "fontes")}
    return dados


def previsao_refinada(lat, lon):
    return refinar(api.previsao(lat, lon), lat, lon)
