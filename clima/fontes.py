"""Fontes oficiais brasileiras: avisos e previsão do INMET, previsão do CPTEC/INPE
(via BrasilAPI) e o código IBGE do município (usado pelo INMET).

As funções `_parse_*`, `avisos_da_cidade` etc. são puras (testáveis sem rede).
"""
import json
import os
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

from .api import obter_json

INMET_AVISOS = "https://apiprevmet3.inmet.gov.br/avisos/ativos"
INMET_PREVISAO = "https://apiprevmet3.inmet.gov.br/previsao/{}"
IBGE_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
CPTEC_BUSCA = "https://brasilapi.com.br/api/cptec/v1/cidade/{}"
CPTEC_PREVISAO = "https://brasilapi.com.br/api/cptec/v1/clima/previsao/{}/{}"

UFS = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS",
    "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO",
    "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
    "tocantins": "TO",
}

_SEVERIDADE = {"Perigo Potencial": 1, "Perigo": 2, "Grande Perigo": 3}


def sem_acento(texto):
    base = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn").strip()


# ---------- localização ----------
def no_brasil(cidade):
    if cidade.get("pais"):
        return cidade["pais"] == "BR"
    return cidade.get("regiao", "").rstrip().endswith("Brasil")


def uf_da_cidade(cidade):
    """Sigla do estado a partir de 'Estado, Brasil' (ou None)."""
    estado = (cidade.get("regiao") or "").split(",")[0]
    return UFS.get(sem_acento(estado))


def _pasta_cache():
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "clima"


def carregar_municipios():
    """Lista [{id, nome, uf}] do IBGE; baixa uma vez e guarda em ~/.cache/clima."""
    caminho = _pasta_cache() / "municipios.json"
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    lista = []
    for m in obter_json(IBGE_MUNICIPIOS, timeout=60):
        uf = None
        for caminho_uf in (
            lambda: m["microrregiao"]["mesorregiao"]["UF"]["sigla"],
            lambda: m["regiao-imediata"]["regiao-intermediaria"]["UF"]["sigla"],
        ):
            try:
                uf = caminho_uf()
                break
            except (KeyError, TypeError):
                continue
        lista.append({"id": m["id"], "nome": m["nome"], "uf": uf})
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(lista, ensure_ascii=False), encoding="utf-8")
    return lista


def escolher_municipio(municipios, cidade):
    nome, uf = sem_acento(cidade["nome"]), uf_da_cidade(cidade)
    for m in municipios:
        if sem_acento(m["nome"]) == nome and (uf is None or m["uf"] == uf):
            return m["id"]
    return None


def achar_ibge(cidade):
    return cidade.get("ibge") or escolher_municipio(carregar_municipios(), cidade)


# ---------- avisos do INMET ----------
def baixar_avisos():
    dados = obter_json(INMET_AVISOS, timeout=30)
    return list(dados.get("hoje", [])) + list(dados.get("futuro", []))


def _lista(texto):
    """Os campos riscos/instrucoes chegam como texto de lista Python (às vezes malformado)."""
    if not texto:
        return []
    t = str(texto).strip()
    if t.startswith("[") and t.endswith("]"):
        t = t[1:-1]
    partes = re.split(r"""['"]\s*,\s*['"]""", t)
    return [p.strip().strip("'\"").strip() for p in partes if p.strip().strip("'\"").strip()]


def _anel_contem(anel, lon, lat):
    dentro = False
    j = len(anel) - 1
    for i, (xi, yi) in enumerate(anel):
        xj, yj = anel[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def no_poligono(geojson, lat, lon):
    """Ponto dentro de um Polygon/MultiPolygon GeoJSON (texto ou dict)?"""
    try:
        g = json.loads(geojson) if isinstance(geojson, str) else geojson
        polis = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poli in polis:
            if _anel_contem(poli[0], lon, lat) and not any(
                _anel_contem(b, lon, lat) for b in poli[1:]
            ):
                return True
    except (KeyError, TypeError, ValueError, IndexError):
        pass
    return False


def _fmt_data(txt):
    try:
        return datetime.strptime(txt, "%Y-%m-%d %H:%M").strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return txt or ""


def avisos_da_cidade(todos, cidade, ibge):
    """Avisos ativos que cobrem a cidade (por código IBGE; senão, pelo polígono)."""
    vistos, saida = set(), []
    for a in todos:
        if str(a.get("encerrado")).lower() in ("true", "1"):
            continue
        if ibge:
            casa = str(ibge) in str(a.get("geocodes", "")).split(",")
        else:
            casa = no_poligono(a.get("poligono"), cidade["lat"], cidade["lon"])
        ident = str(a.get("id_aviso") or a.get("id"))
        if not casa or ident in vistos:
            continue
        vistos.add(ident)
        saida.append(
            {
                "id": ident,
                "titulo": a.get("descricao") or "Aviso",
                "severidade": a.get("severidade") or "",
                "inicio": _fmt_data(a.get("inicio")),
                "fim": _fmt_data(a.get("fim")),
                "riscos": _lista(a.get("riscos")),
                "instrucoes": _lista(a.get("instrucoes")),
            }
        )
    saida.sort(key=lambda a: -_SEVERIDADE.get(a["severidade"], 0))
    return saida


# ---------- previsão do INMET ----------
def _int(valor):
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None


def parse_previsao_inmet(dados, ibge):
    """Dias [{data, max, min, resumo, umidade, nascer, ocaso, vento}] ordenados."""
    dias = []
    for data, periodos in dados.get(str(ibge), {}).items():
        try:
            dt = datetime.strptime(data, "%d/%m/%Y").date()
        except ValueError:
            continue
        if not isinstance(periodos, dict):
            continue
        if "temp_max" in periodos:  # dias mais distantes vêm sem divisão por período
            p = periodos
        else:
            p = periodos.get("tarde") or next(
                (v for v in periodos.values() if isinstance(v, dict)), None
            )
        if not p:
            continue
        vento = ", ".join(x for x in (p.get("dir_vento"), (p.get("int_vento") or "").lower()) if x)
        dias.append(
            {
                "data": dt,
                "max": _int(p.get("temp_max")),
                "min": _int(p.get("temp_min")),
                "resumo": p.get("resumo") or "",
                "umidade": (_int(p.get("umidade_min")), _int(p.get("umidade_max"))),
                "nascer": p.get("nascer"),
                "ocaso": p.get("ocaso"),
                "vento": vento,
            }
        )
    return sorted(dias, key=lambda d: d["data"])


def previsao_inmet(ibge):
    return parse_previsao_inmet(obter_json(INMET_PREVISAO.format(ibge), timeout=30), ibge)


# ---------- previsão do CPTEC/INPE (BrasilAPI) ----------
def escolher_cptec(resultados, cidade):
    nome, uf = sem_acento(cidade["nome"]), uf_da_cidade(cidade)
    do_estado = [r for r in resultados if uf is None or r.get("estado") == uf]
    for r in do_estado:
        if sem_acento(r.get("nome")) == nome:
            return r["id"]
    return do_estado[0]["id"] if do_estado else None


def parse_previsao_cptec(dados):
    return [
        {
            "data": date.fromisoformat(d["data"]),
            "max": _int(d.get("max")),
            "min": _int(d.get("min")),
            "resumo": d.get("condicao_desc") or "",
            "uv": _int(d.get("indice_uv")),
        }
        for d in dados.get("clima", [])
    ]


def previsao_cptec(cidade):
    """Devolve (id do CPTEC, dias); None se a cidade não for encontrada."""
    cid = cidade.get("cptec")
    if not cid:
        cid = escolher_cptec(obter_json(CPTEC_BUSCA.format(quote(cidade["nome"]))), cidade)
        if not cid:
            return None
    return cid, parse_previsao_cptec(obter_json(CPTEC_PREVISAO.format(cid, 4)))
