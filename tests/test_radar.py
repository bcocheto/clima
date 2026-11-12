import unittest

from clima import radar


class TestRadar(unittest.TestCase):
    def test_ida_e_volta_de_coordenadas(self):
        x, y = radar.mundo_px(-27.36, -53.18, 7)
        lat, lon = radar.px_para_latlon(x, y, 7)
        self.assertAlmostEqual(lat, -27.36, places=4)
        self.assertAlmostEqual(lon, -53.18, places=4)

    def test_tile_conhecido(self):
        x, y = radar.mundo_px(-27.36, -53.18, 7)
        self.assertEqual((int(x // 256), int(y // 256)), (45, 74))

    def test_quadros(self):
        host, q = radar.quadros_de({"host": "h", "radar": {
            "past": [{"time": 1, "path": "/a"}], "nowcast": [{"time": 2, "path": "/b"}]}})
        self.assertEqual(q, [(1, "/a", False), (2, "/b", True)])
        self.assertEqual(radar.url_radar(host, "/a", 7, 45, 74), "h/a/256/7/45/74/2/1_1.png")


if __name__ == "__main__":
    unittest.main()
