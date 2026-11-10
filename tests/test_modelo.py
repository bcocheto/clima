import tempfile
import unittest
from pathlib import Path

from clima import modelo
from clima.codigos import descrever
from clima.store import Store

DADOS = {
    "current": {"time": "2026-11-10T12:15"},
    "hourly": {
        "time": [f"2026-11-10T{h:02d}:00" for h in range(10, 16)],
        "temperature_2m": [20, 21, 22, 23, 24, 25],
        "precipitation_probability": [0, 0, 10, None, 50, 80],
    },
    "daily": {
        "time": ["2026-11-10", "2026-11-11", "2026-11-12"],
        "weather_code": [0, 61, 95],
        "temperature_2m_max": [28, 26, 24],
        "temperature_2m_min": [18, 17, 16],
        "precipitation_probability_max": [0, 70, None],
    },
    "minutely_15": {
        "time": ["2026-11-10T12:00", "2026-11-10T12:15", "2026-11-10T12:30",
                 "2026-11-10T12:45", "2026-11-10T13:00"],
        "precipitation": [0.0, 0.0, 0.0, 0.4, 1.0],
    },
}


class TestModelo(unittest.TestCase):
    def test_horas_comecam_na_hora_atual(self):
        horas = modelo.horas_seguintes(DADOS)
        self.assertEqual(horas[0], ("12:00", 22, 10))
        self.assertEqual(horas[1][2], 0)  # None vira 0
        self.assertEqual(len(horas), 4)

    def test_dias_e_nomes(self):
        d = modelo.dias(DADOS)
        self.assertEqual([modelo.nome_dia(i, x["data"]) for i, x in enumerate(d)],
                         ["Hoje", "Amanhã", "Quinta"])
        self.assertEqual(d[2]["chuva"], 0)

    def test_chuva_em_minutos(self):
        self.assertEqual(modelo.chuva_em_minutos(DADOS), 15)

    def test_sem_chuva(self):
        sem = {**DADOS, "minutely_15": {"time": DADOS["minutely_15"]["time"],
                                        "precipitation": [0] * 5}}
        self.assertIsNone(modelo.chuva_em_minutos(sem))
        self.assertIsNone(modelo.chuva_em_minutos({"current": DADOS["current"]}))

    def test_codigos(self):
        self.assertEqual(descrever(0, dia=False)[1], "weather-clear-night-symbolic")
        self.assertEqual(descrever(95)[0], "Tempestade")
        self.assertEqual(descrever(999)[0], "Indefinido")


class TestStore(unittest.TestCase):
    def test_persistencia(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "x" / "cidades.json"
            s = Store(caminho)
            self.assertEqual(len(s.cidades), 1)  # padrão
            c = {"nome": "Recife", "regiao": "PE", "lat": -8.05, "lon": -34.88}
            self.assertEqual(s.adicionar(c), 1)
            self.assertEqual(s.adicionar(c), 1)  # sem duplicar
            self.assertEqual(len(Store(caminho).cidades), 2)
            s.remover(c)
            self.assertEqual(len(Store(caminho).cidades), 1)


if __name__ == "__main__":
    unittest.main()
