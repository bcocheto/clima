import unittest
from datetime import date

from clima import fontes

AVISO = {
    "id_aviso": "1", "descricao": "Tempestade", "severidade": "Perigo Potencial",
    "inicio": "2026-11-10 00:01", "fim": "2026-11-12 23:59", "encerrado": "False",
    "geocodes": "4300646,4314100",
    "riscos": "['Ventos de 60 km/h.', 'Queda de granizo.']",
    "instrucoes": "['Evite abrigar-se debaixo de \\u00e1rvores.']",
    "poligono": '{"type":"Polygon","coordinates":[[[-54,-28],[-52,-28],[-52,-27],[-54,-27],[-54,-28]]]}',
}
CIDADE = {"nome": "Ametista do Sul", "regiao": "Rio Grande do Sul, Brasil",
          "lat": -27.36, "lon": -53.03}


class TestFontes(unittest.TestCase):
    def test_localizacao(self):
        self.assertTrue(fontes.no_brasil(CIDADE))
        self.assertFalse(fontes.no_brasil({"nome": "Lisboa", "regiao": "Lisboa, Portugal"}))
        self.assertFalse(fontes.no_brasil({**CIDADE, "pais": "PT"}))
        self.assertEqual(fontes.uf_da_cidade(CIDADE), "RS")
        self.assertEqual(fontes.uf_da_cidade({"regiao": "São Paulo, Brasil"}), "SP")

    def test_municipio_por_nome_e_uf(self):
        lista = [{"id": 1, "nome": "Bom Jesus", "uf": "PB"},
                 {"id": 2, "nome": "Bom Jesus", "uf": "RS"},
                 {"id": 3, "nome": "São Paulo", "uf": "SP"}]
        rs = {"nome": "Bom Jesus", "regiao": "Rio Grande do Sul, Brasil"}
        self.assertEqual(fontes.escolher_municipio(lista, rs), 2)
        sp = {"nome": "Sao Paulo", "regiao": "São Paulo, Brasil"}
        self.assertEqual(fontes.escolher_municipio(lista, sp), 3)

    def test_avisos_por_codigo_ibge(self):
        r = fontes.avisos_da_cidade([AVISO, AVISO], CIDADE, 4300646)  # duplicado
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["titulo"], "Tempestade")
        self.assertEqual(r[0]["fim"], "12/11 23:59")
        self.assertEqual(r[0]["riscos"][1], "Queda de granizo.")
        self.assertEqual(fontes.avisos_da_cidade([AVISO], CIDADE, 9999999), [])

    def test_avisos_por_poligono_e_encerrados(self):
        self.assertEqual(len(fontes.avisos_da_cidade([AVISO], CIDADE, None)), 1)
        longe = {**CIDADE, "lat": -10.0, "lon": -40.0}
        self.assertEqual(fontes.avisos_da_cidade([AVISO], longe, None), [])
        self.assertEqual(
            fontes.avisos_da_cidade([{**AVISO, "encerrado": "True"}], CIDADE, 4300646), []
        )

    def test_ordena_por_severidade(self):
        grave = {**AVISO, "id_aviso": "2", "severidade": "Grande Perigo"}
        r = fontes.avisos_da_cidade([AVISO, grave], CIDADE, 4300646)
        self.assertEqual([a["severidade"] for a in r], ["Grande Perigo", "Perigo Potencial"])

    def test_previsao_inmet_com_e_sem_periodos(self):
        dados = {"4300646": {
            "10/11/2026": {"tarde": {"temp_max": "27", "temp_min": "14", "resumo": "Sol",
                                     "umidade_min": "30", "umidade_max": "90",
                                     "dir_vento": "NE", "int_vento": "Fracos",
                                     "nascer": "05h37", "ocaso": "18h50"}},
            "12/11/2026": {"temp_max": "25", "temp_min": "16", "resumo": "Nublado"},
        }}
        r = fontes.parse_previsao_inmet(dados, 4300646)
        self.assertEqual([(d["data"], d["max"], d["min"]) for d in r],
                         [(date(2026, 11, 10), 27, 14), (date(2026, 11, 12), 25, 16)])
        self.assertEqual(r[0]["vento"], "NE, fracos")

    def test_cptec(self):
        achados = [{"id": 5, "nome": "Ametista", "estado": "PR"},
                   {"id": 446, "nome": "Ametista do Sul", "estado": "RS"}]
        self.assertEqual(fontes.escolher_cptec(achados, CIDADE), 446)
        r = fontes.parse_previsao_cptec({"clima": [
            {"data": "2026-11-10", "min": 14, "max": 27, "condicao_desc": "Sol", "indice_uv": 11}]})
        self.assertEqual(r[0]["uv"], 11)


if __name__ == "__main__":
    unittest.main()
