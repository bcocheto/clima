import unittest

from clima import observacao as o

ATUAL = {
    "temperature_2m": 24.2, "apparent_temperature": 28.7, "relative_humidity_2m": 83,
    "weather_code": 80, "precipitation": 0.4, "cloud_cover": 48,
}


def mod(temp, chuva, nuv, umid=70):
    return {"temperature_2m": temp, "relative_humidity_2m": umid,
            "precipitation": chuva, "cloud_cover": nuv}


class TestConsenso(unittest.TestCase):
    def test_modelo_sozinho_nao_basta_para_chuva(self):
        # caso real (Ametista do Sul): best_match dizia pancadas; 2 dos 3 outros, sem chuva
        modelos = {"icon": mod(27.0, 0.0, 86), "gfs": mod(26.7, 0.1, 0), "ecmwf": mod(24.8, 0.2, 96)}
        r = o.consenso(ATUAL, modelos)
        self.assertFalse(r["chovendo"])
        self.assertEqual(r["weather_code"], 3)  # nebulosidade mediana ~67% -> nublado
        self.assertGreater(r["temperature_2m"], 24.2)
        self.assertAlmostEqual(r["apparent_temperature"] - r["temperature_2m"], 4.5, places=0)

    def test_consenso_de_chuva(self):
        modelos = {"a": mod(22, 1.0, 100), "b": mod(21, 0.5, 100), "c": mod(22, 0.3, 100)}
        r = o.consenso(ATUAL, modelos)
        self.assertTrue(r["chovendo"])
        self.assertEqual(r["weather_code"], 80)

    def test_radar_confirma_chuva_com_um_voto(self):
        modelos = {"a": mod(22, 0.0, 90), "b": mod(22, 0.0, 90), "c": mod(22, 0.0, 90)}
        self.assertTrue(o.consenso(ATUAL, modelos, radar=True)["chovendo"])
        self.assertFalse(o.consenso(ATUAL, modelos, radar=False)["chovendo"])

    def test_metar_proximo_manda(self):
        metar = {"estacao": "SBPA", "km": 12, "temp": 28, "umidade": 55, "chuva": False, "nuvens": 15}
        modelos = {"a": mod(22, 1.0, 100), "b": mod(21, 1.0, 100), "c": mod(22, 1.0, 100)}
        r = o.consenso(ATUAL, modelos, metar=metar)
        self.assertEqual((r["temperature_2m"], r["relative_humidity_2m"]), (28, 55))
        self.assertFalse(r["chovendo"])
        self.assertEqual(r["weather_code"], 1)


class TestMetar(unittest.TestCase):
    def test_escolhe_o_mais_proximo_e_le_chuva(self):
        agora = 1_000_000
        lista = [
            {"icaoId": "LONGE", "lat": -29.0, "lon": -53.0, "obsTime": agora, "temp": 20, "rawOb": "x"},
            {"icaoId": "PERTO", "lat": -27.5, "lon": -53.2, "obsTime": agora, "temp": 22, "dewp": 21,
             "cover": "OVC", "rawOb": "METAR PERTO 121400Z 27007KT 9999 -RA OVC010 22/21 Q1016"},
        ]
        m = o.escolher_metar(lista, -27.36, -53.18, agora)
        self.assertEqual(m["estacao"], "PERTO")
        self.assertTrue(m["chuva"])
        self.assertGreater(m["umidade"], 90)

    def test_ignora_distante_ou_velho(self):
        lista = [{"icaoId": "A", "lat": -29, "lon": -53, "obsTime": 0, "temp": 20}]
        self.assertIsNone(o.escolher_metar(lista, -27.36, -53.18, 10_000))

    def test_vizinhanca_nao_e_chuva(self):
        lista = [{"icaoId": "A", "lat": -27.4, "lon": -53.2, "obsTime": 1, "temp": 20,
                  "rawOb": "METAR A 1Z 27007KT 9999 VCSH FEW040 20/10 Q1016"}]
        self.assertFalse(o.escolher_metar(lista, -27.36, -53.18, 2)["chuva"])


class TestModelos(unittest.TestCase):
    def test_parse(self):
        resp = {"current": {"temperature_2m": 27.0, "precipitation": 0.0, "cloud_cover": 86}}
        self.assertEqual(o.parse_modelo(resp)["temperature_2m"], 27.0)
        self.assertIsNone(o.parse_modelo({"current": {}}))


if __name__ == "__main__":
    unittest.main()
