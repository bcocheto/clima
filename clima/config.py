"""Preferências do usuário em ~/.config/clima/config.json."""
import json
from pathlib import Path

from .store import pasta_config

PADRAO = {
    "temperatura": "C",  # C | F
    "vento": "kmh",  # kmh | mph | ms
    "alertas": True,  # notificação de chuva
    "antecedencia_min": 120,  # quão cedo avisar da chuva (30 | 60 | 120)
    "intervalo_min": 10,  # de quanto em quanto tempo atualizar (5 | 10 | 30)
}

_UNIDADE_VENTO = {"kmh": ("km/h", 1.0), "mph": ("mph", 0.621371), "ms": ("m/s", 1 / 3.6)}


class Config:
    def __init__(self, caminho=None):
        self.caminho = Path(caminho) if caminho else pasta_config() / "config.json"
        self.valores = dict(PADRAO)
        try:
            salvo = json.loads(self.caminho.read_text(encoding="utf-8"))
            for k, v in salvo.items():
                if k in PADRAO and type(v) is type(PADRAO[k]):
                    self.valores[k] = v
        except (OSError, ValueError, AttributeError):
            pass

    def get(self, chave):
        return self.valores[chave]

    def set(self, chave, valor):
        self.valores[chave] = valor
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(json.dumps(self.valores, indent=2), encoding="utf-8")

    # ---- formatação conforme as unidades escolhidas ----
    def fmt_temp(self, celsius):
        t = celsius * 9 / 5 + 32 if self.valores["temperatura"] == "F" else celsius
        return f"{round(t)}°"

    def fmt_vento(self, kmh):
        nome, fator = _UNIDADE_VENTO[self.valores["vento"]]
        return f"{kmh * fator:.0f} {nome}"

    def texto_janela(self):
        m = self.valores["antecedencia_min"]
        return f"{m} minutos" if m < 60 else ("1 hora" if m == 60 else f"{m // 60} horas")


cfg = Config()
