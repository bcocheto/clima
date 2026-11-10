"""Cidades favoritas em ~/.config/clima/cidades.json."""
import json
import os
from pathlib import Path

PADRAO = [
    {"nome": "São Paulo", "regiao": "São Paulo, Brasil", "lat": -23.5475, "lon": -46.6361}
]


def chave(cidade):
    return f"{cidade['lat']:.2f},{cidade['lon']:.2f}"


def pasta_config():
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "clima"


def _caminho_padrao():
    return pasta_config() / "cidades.json"


class Store:
    def __init__(self, caminho=None):
        self.caminho = Path(caminho) if caminho else _caminho_padrao()
        self.cidades = self._ler()

    def _ler(self):
        try:
            dados = json.loads(self.caminho.read_text(encoding="utf-8"))
            if isinstance(dados, list) and dados:
                return dados
        except (OSError, ValueError):
            pass
        return [dict(c) for c in PADRAO]

    def salvar(self):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(
            json.dumps(self.cidades, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def adicionar(self, cidade):
        """Adiciona se ainda não existir; devolve o índice da cidade."""
        for i, c in enumerate(self.cidades):
            if chave(c) == chave(cidade):
                return i
        self.cidades.append(cidade)
        self.salvar()
        return len(self.cidades) - 1

    def remover(self, cidade):
        self.cidades = [c for c in self.cidades if chave(c) != chave(cidade)]
        self.salvar()
