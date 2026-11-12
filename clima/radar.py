"""Radar de chuva: quadros do RainViewer sobre o mapa do OpenStreetMap.

Os tiles são baixados em threads e desenhados com GtkSnapshot (sem WebKit/libshumate).
`eco_no_ponto` amostra o radar na posição da cidade e alimenta a correção do "agora".
"""
import math
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Graphene, Gsk, Gtk, Pango  # noqa: E402

from .api import USER_AGENT  # noqa: E402

RAINVIEWER = "https://api.rainviewer.com/public/weather-maps.json"
BASE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TAM = 256
ZOOM_MIN, ZOOM_MAX = 4, 7  # o RainViewer só entrega tiles de radar até o zoom 7
ZOOM_PADRAO = 7
PASSO_MS = 650
PAUSA_FINAL_MS = 1500  # respiro no quadro mais recente antes de recomeçar o loop
ATUALIZAR_S = 600
CACHE_MAX = 220  # texturas de 256x256 (~256 KB cada na GPU)
FALHA_S = 60  # não repetir tile que falhou por um minuto

_CACHE = OrderedDict()  # url -> Gdk.Texture, compartilhado entre o mini-radar e o diálogo
_FALHAS = {}  # url -> instante da falha


def _cache_get(url):
    tex = _CACHE.get(url)
    if tex is not None:
        _CACHE.move_to_end(url)
    return tex


def _cache_put(url, tex):
    _CACHE[url] = tex
    _CACHE.move_to_end(url)
    while len(_CACHE) > CACHE_MAX:
        _CACHE.popitem(last=False)


# ---------- matemática de tiles (pura) ----------
def mundo_px(lat, lon, z):
    """Coordenadas em pixels no mapa mundial (projeção Web Mercator) no zoom z."""
    n = TAM * 2**z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def px_para_latlon(x, y, z):
    n = TAM * 2**z
    lon = x / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


def url_radar(host, caminho, z, x, y):
    return f"{host}{caminho}/{TAM}/{z}/{x}/{y}/2/1_1.png"  # esquema "Universal Blue", suave


def quadros_de(resposta):
    """(host, [(timestamp, caminho, previsto)]) a partir do weather-maps.json."""
    radar = resposta.get("radar", {})
    lista = [(q["time"], q["path"], False) for q in radar.get("past", [])]
    lista += [(q["time"], q["path"], True) for q in radar.get("nowcast", [])]
    return resposta.get("host", "https://tilecache.rainviewer.com"), lista


def baixar(url, timeout=15):
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def obter_quadros():
    import json

    return quadros_de(json.loads(baixar(RAINVIEWER)))


def eco_no_ponto(lat, lon):
    """True se o último quadro do radar mostra chuva em volta do ponto (None se sem dados)."""
    host, quadros = obter_quadros()
    passados = [q for q in quadros if not q[2]]
    if not passados:
        return None
    _, caminho, _ = passados[-1]
    z = 7
    px, py = mundo_px(lat, lon, z)
    tx, ty = int(px // TAM), int(py // TAM)
    loader = GdkPixbuf.PixbufLoader()
    loader.write(baixar(url_radar(host, caminho, z, tx, ty)))
    loader.close()
    pb = loader.get_pixbuf()
    if pb is None or not pb.get_has_alpha():
        return None
    dados, rs, canais = pb.get_pixels(), pb.get_rowstride(), pb.get_n_channels()
    cx, cy = int(px - tx * TAM), int(py - ty * TAM)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            x, y = cx + dx, cy + dy
            if 0 <= x < pb.get_width() and 0 <= y < pb.get_height():
                if dados[y * rs + x * canais + 3] > 40:
                    return True
    return False


# ---------- widget ----------
class RadarView(Gtk.Widget):
    def __init__(self, lat, lon, ao_mudar_quadro=None, interativo=True, altura=None, max_passados=None):
        # mini-radar: sem gestos (não briga com a rolagem da página), altura fixa, menos quadros
        super().__init__(hexpand=True, vexpand=altura is None, overflow=Gtk.Overflow.HIDDEN)
        self.lat, self.lon = lat, lon
        self.altura = altura
        self.max_passados = max_passados
        self.interativo = interativo
        self.automatico = not interativo  # o mini anima sozinho; o diálogo espera o play
        self._geracao = 0
        self._atualizando = None
        self.z = ZOOM_PADRAO
        self.cx, self.cy = mundo_px(lat, lon, self.z)
        self.host, self.quadros = "", []
        self.indice = 0
        self.ao_mudar_quadro = ao_mudar_quadro
        self.pedidos = set()
        self.tocando = False
        self._timer = None
        self._pool = ThreadPoolExecutor(max_workers=6)
        self._arraste = None
        self.add_css_class("clima-radar")

        if interativo:
            arrasto = Gtk.GestureDrag()
            arrasto.connect("drag-begin", lambda *_: setattr(self, "_arraste", (self.cx, self.cy)))
            arrasto.connect("drag-update", self._ao_arrastar)
            self.add_controller(arrasto)
            rolagem = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
            rolagem.connect(
                "scroll", lambda _c, _dx, dy: (self.mudar_zoom(-1 if dy > 0 else 1), True)[1]
            )
            self.add_controller(rolagem)
        # só gasta CPU/rede enquanto está na tela
        self.connect("map", lambda *_: self._ao_aparecer())
        self.connect("unmap", lambda *_: self._ao_sumir())
        self.connect("destroy", lambda *_: self.parar())

    # --- dados ---
    def carregar(self, ao_pronto, ao_erro):
        def trabalho():
            try:
                host, quadros = obter_quadros()
            except Exception as e:
                GLib.idle_add(lambda: (ao_erro(e), False)[1])
                return
            GLib.idle_add(lambda: (self._receber(host, quadros, ao_pronto), False)[1])

        threading.Thread(target=trabalho, daemon=True).start()

    def _receber(self, host, quadros, ao_pronto):
        if self.max_passados:
            passados = [q for q in quadros if not q[2]][-self.max_passados:]
            quadros = passados + [q for q in quadros if q[2]]
        self.host, self.quadros = host, quadros
        passados = [i for i, q in enumerate(quadros) if not q[2]]
        self.indice = passados[-1] if passados else 0
        self.queue_draw()
        ao_pronto()
        self._prefetch_todos()
        self._notificar()
        if self.automatico and self.get_mapped():
            self._agendar()

    # --- ciclo de vida ---
    def _animar_permitido(self):
        cfg = Gtk.Settings.get_default()
        return bool(cfg.get_property("gtk-enable-animations")) if cfg else True

    def _ao_aparecer(self):
        if self.automatico and self.quadros and self._animar_permitido():
            self._agendar()
        if self._atualizando is None:
            self._atualizando = GLib.timeout_add_seconds(ATUALIZAR_S, self._reatualizar)

    def _ao_sumir(self):
        self._parar_timer()
        if self._atualizando is not None:
            GLib.source_remove(self._atualizando)
            self._atualizando = None

    def _reatualizar(self):
        if self.quadros:
            self.carregar(lambda: None, lambda e: None)
        return True

    def definir_cidade(self, lat, lon):
        if (lat, lon) == (self.lat, self.lon):
            return
        self.lat, self.lon = lat, lon
        self._geracao += 1  # descarta respostas de tiles pedidos para a cidade anterior
        self.pedidos.clear()
        self.cx, self.cy = mundo_px(lat, lon, self.z)
        self.queue_draw()
        self._prefetch_todos()

    def _notificar(self):
        if self.ao_mudar_quadro and self.quadros:
            ts, _, previsto = self.quadros[self.indice]
            self.ao_mudar_quadro(self.indice, len(self.quadros), ts, previsto)

    # --- controle ---
    def ir_para(self, i):
        if not self.quadros:
            return
        i = max(0, min(len(self.quadros) - 1, int(i)))
        if i == self.indice and self.get_mapped():
            return
        self.indice = i
        self.queue_draw()
        self._notificar()

    def _parar_timer(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = None

    def _agendar(self):
        self._parar_timer()
        ultimo = self.quadros and self.indice == len(self.quadros) - 1
        self._timer = GLib.timeout_add(PAUSA_FINAL_MS if ultimo else PASSO_MS, self._avancar)

    def tocar(self, sim):
        self.tocando = sim
        self._parar_timer()
        if sim:
            self._agendar()

    def _avancar(self):
        self._timer = None
        if not self.quadros or not self.get_mapped():
            return False
        self.ir_para((self.indice + 1) % len(self.quadros))
        if self.tocando or self.automatico:
            self._agendar()
        return False

    def parar(self):
        self.tocando = False
        self.automatico = False
        self._ao_sumir()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def mudar_zoom(self, delta):
        z = max(ZOOM_MIN, min(ZOOM_MAX, self.z + delta))
        if z == self.z:
            return
        lat, lon = px_para_latlon(self.cx, self.cy, self.z)
        self.z = z
        self.cx, self.cy = mundo_px(lat, lon, z)
        self.queue_draw()
        self._prefetch_todos()

    def centralizar(self):
        self.cx, self.cy = mundo_px(self.lat, self.lon, self.z)
        self.queue_draw()
        self._prefetch_todos()

    def _ao_arrastar(self, _g, dx, dy):
        if self._arraste:
            self.cx, self.cy = self._arraste[0] - dx, self._arraste[1] - dy
            self.queue_draw()

    # --- tiles ---
    def _visiveis(self):
        w, h = max(self.get_width(), 1), max(self.get_height(), 1)
        x0, x1 = int((self.cx - w / 2) // TAM), int((self.cx + w / 2) // TAM)
        y0, y1 = int((self.cy - h / 2) // TAM), int((self.cy + h / 2) // TAM)
        n = 2**self.z
        return [(x % n, y, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) if 0 <= y < n]

    def _pedir(self, url):
        if url in self.pedidos or _cache_get(url) is not None:
            return
        if time.monotonic() - _FALHAS.get(url, -FALHA_S) < FALHA_S:
            return
        self.pedidos.add(url)
        geracao = self._geracao

        def trabalho():
            try:
                tex = Gdk.Texture.new_from_bytes(GLib.Bytes.new(baixar(url)))
            except Exception:
                tex = None
            GLib.idle_add(lambda: (self._chegou(url, tex, geracao), False)[1])

        try:
            self._pool.submit(trabalho)
        except RuntimeError:  # janela fechando
            pass

    def _chegou(self, url, tex, geracao):
        self.pedidos.discard(url)
        if tex is None:
            _FALHAS[url] = time.monotonic()
            return
        _cache_put(url, tex)  # vale para qualquer cidade: a URL já identifica o tile
        if geracao == self._geracao:
            self.queue_draw()

    def _prefetch_todos(self):
        # ordem importa (fila FIFO): mapa, depois o quadro atual, depois os demais quadros
        tiles = [(tx, ty) for tx, ty, *_ in self._visiveis()]
        for tx, ty in tiles:
            self._pedir(BASE_URL.format(z=self.z, x=tx, y=ty))
        atual = [self.indice] if self.quadros else []
        outros = [i for i in reversed(range(len(self.quadros))) if i != self.indice]
        for i in atual + outros:
            for tx, ty in tiles:
                self._pedir(url_radar(self.host, self.quadros[i][1], self.z, tx, ty))

    # --- desenho ---
    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.VERTICAL and self.altura:
            return self.altura, self.altura, -1, -1
        return (200 if self.altura else 320), (200 if self.altura else 320), -1, -1

    def do_size_allocate(self, w, h, baseline):
        self._prefetch_todos()

    def do_snapshot(self, snapshot):
        w, h = self.get_width(), self.get_height()
        escuro = Adw.StyleManager.get_default().get_dark()
        fundo = Gdk.RGBA()
        fundo.parse("#1c1c1e" if escuro else "#e6e6e6")
        snapshot.append_color(fundo, Graphene.Rect().init(0, 0, w, h))

        quadro = self.quadros[self.indice] if self.quadros else None
        for tx, ty, ux, uy in self._visiveis():
            x, y = ux * TAM - self.cx + w / 2, uy * TAM - self.cy + h / 2
            ret = Graphene.Rect().init(x, y, TAM, TAM)
            url = BASE_URL.format(z=self.z, x=tx, y=ty)
            self._pedir(url)
            base = _cache_get(url)
            if base:
                if escuro:  # mapa claro vira cinza-escuro para o eco do radar aparecer
                    snapshot.push_opacity(0.55)
                snapshot.append_texture(base, ret)
                if escuro:
                    snapshot.pop()
            if quadro:
                url_r = url_radar(self.host, quadro[1], self.z, tx, ty)
                self._pedir(url_r)
                tex = _cache_get(url_r)
                if tex:
                    snapshot.push_opacity(0.8)
                    snapshot.append_texture(tex, ret)
                    snapshot.pop()

        # marcador da cidade
        mx, my = mundo_px(self.lat, self.lon, self.z)
        px, py = mx - self.cx + w / 2, my - self.cy + h / 2
        branco = Gdk.RGBA()
        branco.parse("#ffffff")
        ac = Adw.StyleManager.get_default().get_accent_color_rgba()
        for raio, cor in ((8, branco), (5.5, ac)):
            pb = Gsk.PathBuilder.new()
            pb.add_circle(Graphene.Point().init(px, py), raio)
            snapshot.append_fill(pb.to_path(), Gsk.FillRule.WINDING, cor)

        # crédito exigido pelas licenças dos mapas e do radar
        layout = self.create_pango_layout("© OpenStreetMap · RainViewer")
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_scale_new(0.75))
        layout.set_attributes(attrs)
        tw, th = layout.get_pixel_size()
        sombra = Gdk.RGBA()
        sombra.parse("rgba(0,0,0,0.45)")
        snapshot.append_color(sombra, Graphene.Rect().init(w - tw - 12, h - th - 8, tw + 10, th + 6))
        snapshot.save()
        snapshot.translate(Graphene.Point().init(w - tw - 7, h - th - 5))
        snapshot.append_layout(layout, branco)
        snapshot.restore()


def hora_do_quadro(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")


class DialogoRadar(Adw.Dialog):
    def __init__(self, cidade):
        super().__init__(
            title=f'Radar · {cidade["nome"]}', content_width=900, content_height=640
        )
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())

        self.rotulo_hora = Gtk.Label(
            width_chars=14, xalign=0, css_classes=["numeric", "clima-meta"]
        )
        self.radar = RadarView(cidade["lat"], cidade["lon"], self._quadro_mudou)
        self.escala = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self.escala.set_hexpand(True)
        self.escala.set_draw_value(False)
        self.escala.set_sensitive(False)
        self.escala.connect("change-value", self._ao_escala)
        self.play = Gtk.ToggleButton(
            icon_name="media-playback-start-symbolic", tooltip_text="Animar",
            css_classes=["flat", "circular"], sensitive=False,
        )
        self.play.connect("toggled", self._ao_play)

        def botao(icone, dica, fn):
            b = Gtk.Button(icon_name=icone, tooltip_text=dica, css_classes=["flat", "circular"])
            b.connect("clicked", lambda *_: fn())
            return b

        barra = Gtk.Box(spacing=8, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
        for w in (
            self.play, self.escala, self.rotulo_hora,
            botao("zoom-out-symbolic", "Afastar", lambda: self.radar.mudar_zoom(-1)),
            botao("zoom-in-symbolic", "Aproximar", lambda: self.radar.mudar_zoom(1)),
            botao("find-location-symbolic", "Centralizar na cidade", self.radar.centralizar),
        ):
            barra.append(w)

        self.estado = Adw.StatusPage(
            icon_name="weather-showers-symbolic", title="Carregando radar…"
        )
        self.pilha = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.pilha.add_named(self.estado, "estado")
        corpo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        corpo.append(self.radar)
        corpo.append(barra)
        self.pilha.add_named(corpo, "radar")
        tv.set_content(self.pilha)
        self.set_child(tv)
        self.radar.carregar(self._pronto, self._erro)

    def _pronto(self):
        n = len(self.radar.quadros)
        if not n:
            self._erro("sem quadros")
            return
        self.escala.set_range(0, max(n - 1, 1))
        self.escala.set_sensitive(True)
        self.play.set_sensitive(True)
        self.pilha.set_visible_child_name("radar")

    def _erro(self, e):
        self.estado.set_title("Radar indisponível")
        self.estado.set_description(f"Não foi possível carregar o radar ({e}).")
        self.estado.set_icon_name("network-error-symbolic")

    def _quadro_mudou(self, i, n, ts, previsto):
        self.escala.set_value(i)
        self.rotulo_hora.set_label(hora_do_quadro(ts) + (" · previsão" if previsto else ""))

    def _ao_escala(self, _s, _tipo, valor):
        self.radar.ir_para(round(valor))
        return False

    def _ao_play(self, botao):
        self.radar.tocar(botao.get_active())
        botao.set_icon_name(
            "media-playback-pause-symbolic" if botao.get_active() else "media-playback-start-symbolic"
        )


class MiniRadar(Gtk.Overlay):
    """Radar compacto e sempre animado para a tela principal; clique abre o diálogo completo."""

    def __init__(self, abrir_dialogo):
        super().__init__(css_classes=["clima-radar-card"], overflow=Gtk.Overflow.HIDDEN)
        self.abrir_dialogo = abrir_dialogo
        self.cidade = None
        self._ok = False
        self.radar = RadarView(
            0, 0, self._quadro_mudou, interativo=False, altura=200, max_passados=6
        )
        self.set_child(self.radar)
        self.pilula = Gtk.Label(
            css_classes=["clima-radar-pilula", "numeric"], halign=Gtk.Align.START,
            valign=Gtk.Align.END, margin_start=10, margin_bottom=10,
        )
        self.add_overlay(self.pilula)
        self.add_overlay(Gtk.Image(
            icon_name="view-fullscreen-symbolic", css_classes=["clima-radar-pilula"],
            halign=Gtk.Align.END, valign=Gtk.Align.START, margin_end=10, margin_top=10,
        ))
        self.estado = Gtk.Label(
            css_classes=["clima-radar-pilula"], halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
        )
        self.add_overlay(self.estado)
        clique = Gtk.GestureClick()
        clique.connect("released", self._ao_clicar)
        self.add_controller(clique)
        self.set_cursor(Gdk.Cursor.new_from_name("pointer"))
        self.set_tooltip_text("Radar de chuva — clique para abrir em tela cheia")
        self._mostrar_estado("Carregando radar…")

    def _mostrar_estado(self, texto):
        self.estado.set_label(texto or "")
        self.estado.set_visible(bool(texto))
        self.pilula.set_visible(not texto)

    def definir_cidade(self, cidade):
        self.cidade = cidade
        self.radar.definir_cidade(cidade["lat"], cidade["lon"])
        if not self.radar.quadros and not self._ok:
            self._carregar()

    def _carregar(self):
        self._mostrar_estado("Carregando radar…")
        self.radar.carregar(self._pronto, self._erro)

    def _pronto(self):
        self._ok = bool(self.radar.quadros)
        self._mostrar_estado(None if self._ok else "Radar sem dados")

    def _erro(self, _e):
        self._ok = False
        self._mostrar_estado("Radar indisponível · clique para tentar de novo")

    def _quadro_mudou(self, _i, _n, ts, previsto):
        self.pilula.set_label(
            f"PREVISÃO · {hora_do_quadro(ts)}" if previsto else f"AO VIVO · {hora_do_quadro(ts)}"
        )
        self.pilula.set_css_classes(
            ["clima-radar-pilula", "numeric"] + (["previsao"] if previsto else [])
        )

    def _ao_clicar(self, *_):
        if not self._ok:
            self._carregar()
        elif self.cidade:
            self.abrir_dialogo(self.cidade)
