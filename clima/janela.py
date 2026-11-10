import threading

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from . import api, modelo
from .busca import DialogoBusca
from .codigos import ambiente, descrever
from .grafico import Grafico, grau
from .store import Store, chave

INTERVALO_CHUVA_S = 600


def main_thread(fn, *args):
    GLib.idle_add(lambda: (fn(*args), False)[1])


def em_thread(trabalho, ok, erro):
    def run():
        try:
            resultado = trabalho()
        except Exception as e:  # rede, JSON, etc.
            main_thread(erro, e)
            return
        main_thread(ok, resultado)

    threading.Thread(target=run, daemon=True).start()


def rotulo(texto="", classes=(), **kw):
    return Gtk.Label(label=texto, xalign=0, css_classes=list(classes), **kw)


class Janela(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(
            application=app, title="Clima", default_width=1000, default_height=720
        )
        self.store = Store()
        self.dados = {}  # cache por chave da cidade
        self.cidade = None
        self.avisados = set()
        self._ambiente = None
        self._montar()
        self._popular_cidades(0)
        GLib.timeout_add_seconds(INTERVALO_CHUVA_S, self._tick_chuva)
        GLib.timeout_add_seconds(5, lambda: (self._tick_chuva(), False)[1])

    # ---------- interface ----------
    def _montar(self):
        self.toasts = Adw.ToastOverlay()
        self.split = Adw.OverlaySplitView(
            min_sidebar_width=220, max_sidebar_width=320, sidebar_width_fraction=0.28
        )
        self.toasts.set_child(self.split)
        self.set_content(self.toasts)

        # barra lateral
        sb = Adw.ToolbarView()
        head = Adw.HeaderBar(title_widget=Adw.WindowTitle(title="Cidades", subtitle=""))
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Adicionar cidade")
        add.connect("clicked", self._abrir_busca)
        head.pack_start(add)
        sb.add_top_bar(head)
        self.lista = Gtk.ListBox(css_classes=["clima-cidades"])
        self.lista.connect("row-selected", self._ao_selecionar)
        sb.set_content(Gtk.ScrolledWindow(child=self.lista))
        self.split.set_sidebar(sb)

        # conteúdo
        tv = Adw.ToolbarView(extend_content_to_top_edge=True)
        head = Adw.HeaderBar(show_title=False)
        head.add_css_class("flat")
        toggle = Gtk.ToggleButton(
            icon_name="view-sidebar-start-symbolic", tooltip_text="Mostrar cidades", active=True
        )
        toggle.bind_property(
            "active",
            self.split,
            "show-sidebar",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )
        head.pack_start(toggle)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Atualizar")
        refresh.connect("clicked", lambda *_: self._carregar(forcar=True))
        head.pack_end(refresh)
        tv.add_top_bar(head)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(
            Adw.StatusPage(
                icon_name="weather-clear-symbolic",
                title="Nenhuma cidade",
                description="Adicione uma cidade para ver a previsão.",
            ),
            "vazio",
        )
        self.stack.add_named(
            Gtk.Spinner(
                spinning=True, width_request=32, height_request=32,
                halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
            ),
            "carregando",
        )
        self.stack.add_named(self._montar_dados(), "dados")
        tv.set_content(self.stack)
        self.split.set_content(tv)

    def _montar_dados(self):
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=10,
            margin_top=56, margin_bottom=24, margin_start=18, margin_end=18,
        )

        # topo: cidade + clima atual (estilo app Clima do Windows)
        box.append(rotulo(classes=["title-2"]))
        self.lbl_cidade = box.get_last_child()
        self.lbl_regiao = rotulo(classes=["clima-meta"])
        box.append(self.lbl_regiao)

        hero = Gtk.Box(spacing=20, margin_top=6, margin_bottom=6)
        self.img_atual = Gtk.Image(pixel_size=112)
        hero.append(self.img_atual)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, spacing=2)
        self.lbl_temp = rotulo(classes=["clima-temp"])
        self.lbl_desc = rotulo(classes=["title-3"])
        chips = Gtk.Box(spacing=6, margin_top=4)
        self.chip_minmax = rotulo(classes=["clima-chip"])
        self.chip_sensacao = rotulo(classes=["clima-chip"])
        chips.append(self.chip_minmax)
        chips.append(self.chip_sensacao)
        for w in (self.lbl_temp, self.lbl_desc, chips):
            col.append(w)
        hero.append(col)
        box.append(hero)

        # aviso de chuva
        self.aviso = Gtk.Box(spacing=10, css_classes=["clima-card", "clima-aviso"])
        self.aviso_icone = Gtk.Image(pixel_size=20)
        self.aviso_texto = rotulo(wrap=True, hexpand=True)
        self.aviso.append(self.aviso_icone)
        self.aviso.append(self.aviso_texto)
        box.append(self.aviso)

        # detalhes em tiles
        tiles = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
            min_children_per_line=2, max_children_per_line=4,
            column_spacing=8, row_spacing=8,
        )
        self.val_sensacao = self._tile(tiles, "Sensação térmica")
        self.val_umidade = self._tile(tiles, "Umidade")
        self.val_vento = self._tile(tiles, "Vento")
        self.val_chuva = self._tile(tiles, "Chance de chuva hoje")
        box.append(tiles)

        # próximas horas
        box.append(rotulo("Próximas 24 horas", ["clima-secao"]))
        card = Gtk.Box(css_classes=["clima-card"])
        self.grafico = Grafico()
        card.append(self.grafico)
        box.append(card)

        # próximos dias
        box.append(rotulo("Próximos 7 dias", ["clima-secao"]))
        self.dias_box = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
            min_children_per_line=2, max_children_per_line=7,
            column_spacing=8, row_spacing=8,
        )
        box.append(self.dias_box)

        self.fundo = Gtk.ScrolledWindow(
            child=Adw.Clamp(maximum_size=960, child=box), css_classes=["clima-fundo"]
        )
        return self.fundo

    @staticmethod
    def _tile(flowbox, titulo):
        tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["clima-card"])
        tile.append(rotulo(titulo, ["clima-meta"]))
        valor = rotulo(classes=["clima-valor"])
        tile.append(valor)
        flowbox.append(tile)
        return valor

    @staticmethod
    def _tile_dia(i, d):
        nome, icone = descrever(d["codigo"])
        tile = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=4,
            css_classes=["clima-card", "clima-dia"], tooltip_text=nome,
        )
        rot = rotulo(modelo.nome_dia(i, d["data"]), ["heading"])
        rot.set_halign(Gtk.Align.CENTER)
        tile.append(rot)
        tile.append(Gtk.Image(icon_name=icone, pixel_size=32, margin_top=2, margin_bottom=2))
        for texto, classe in ((grau(d["max"]), "clima-valor"), (grau(d["min"]), "clima-meta"),
                              (f'{d["chuva"]}%', "clima-chuva-pct")):
            r = rotulo(texto, [classe])
            r.set_halign(Gtk.Align.CENTER)
            tile.append(r)
        return tile

    # ---------- cidades ----------
    def _popular_cidades(self, selecionar):
        while (r := self.lista.get_row_at_index(0)) is not None:
            self.lista.remove(r)
        for c in self.store.cidades:
            row = Adw.ActionRow(title=c["nome"], subtitle=c["regiao"], use_markup=False)
            rm = Gtk.Button(
                icon_name="list-remove-symbolic", valign=Gtk.Align.CENTER,
                css_classes=["flat", "circular"], tooltip_text="Remover",
            )
            rm.connect("clicked", lambda _b, c=c: self._remover(c))
            row.add_suffix(rm)
            self.lista.append(row)
        if self.store.cidades:
            n = max(0, min(selecionar, len(self.store.cidades) - 1))
            self.lista.select_row(self.lista.get_row_at_index(n))
        else:
            self.cidade = None
            self.stack.set_visible_child_name("vazio")

    def _abrir_busca(self, *_):
        DialogoBusca(self._adicionar).present(self)

    def _adicionar(self, cidade):
        self._popular_cidades(self.store.adicionar(cidade))

    def _remover(self, cidade):
        self.store.remover(cidade)
        self._popular_cidades(0)

    def _ao_selecionar(self, _lista, row):
        if row is None:
            return
        self.cidade = self.store.cidades[row.get_index()]
        self._carregar()

    # ---------- dados ----------
    def _carregar(self, forcar=False):
        cidade = self.cidade
        if cidade is None:
            return
        k = chave(cidade)
        if k in self.dados and not forcar:
            self._mostrar(cidade, self.dados[k])
            return
        if k not in self.dados:
            self.stack.set_visible_child_name("carregando")

        def ok(d):
            self.dados[k] = d
            if self.cidade is cidade:
                self._mostrar(cidade, d)

        def erro(e):
            self.toasts.add_toast(Adw.Toast(title=f"Falha ao buscar previsão: {e}"))
            if self.cidade is cidade and k in self.dados:
                self._mostrar(cidade, self.dados[k])

        em_thread(lambda: api.previsao(cidade["lat"], cidade["lon"]), ok, erro)

    def _mostrar(self, cidade, d):
        atual = d["current"]
        dia = bool(atual.get("is_day", 1))
        desc, icone = descrever(atual["weather_code"], dia)
        dias = modelo.dias(d)

        # fundo conforme o tempo
        novo = ambiente(atual["weather_code"], dia)
        if novo != self._ambiente:
            if self._ambiente:
                self.fundo.remove_css_class(self._ambiente)
            self.fundo.add_css_class(novo)
            self._ambiente = novo

        self.lbl_cidade.set_label(cidade["nome"])
        self.lbl_regiao.set_label(cidade["regiao"])
        self.img_atual.set_from_icon_name(icone)
        self.lbl_temp.set_label(grau(atual["temperature_2m"]))
        self.lbl_desc.set_label(desc)
        self.chip_minmax.set_label(f'Máx {grau(dias[0]["max"])} · Mín {grau(dias[0]["min"])}')
        self.chip_sensacao.set_label(f'Sensação {grau(atual["apparent_temperature"])}')

        self.val_sensacao.set_label(grau(atual["apparent_temperature"]))
        self.val_umidade.set_label(f'{atual["relative_humidity_2m"]:.0f}%')
        self.val_vento.set_label(f'{atual["wind_speed_10m"]:.0f} km/h')
        self.val_chuva.set_label(f'{dias[0]["chuva"]}%')

        minutos = modelo.chuva_em_minutos(d)
        self.aviso_texto.set_label(self._texto_chuva(minutos))
        self.aviso_icone.set_from_icon_name(
            "weather-showers-symbolic" if minutos is not None else "weather-clear-symbolic"
        )
        if minutos is not None:
            self.aviso.add_css_class("chuva")
        else:
            self.aviso.remove_css_class("chuva")

        self.grafico.set_horas(modelo.horas_seguintes(d))

        self.dias_box.remove_all()
        for i, dia_d in enumerate(dias):
            self.dias_box.append(self._tile_dia(i, dia_d))

        self.stack.set_visible_child_name("dados")

    @staticmethod
    def _texto_chuva(minutos):
        if minutos is None:
            return "Sem chuva prevista nas próximas 2 horas"
        if minutos <= 0:
            return "Chovendo agora"
        return f"Chuva prevista em cerca de {minutos} min"

    # ---------- alerta de chuva ----------
    def _tick_chuva(self):
        cidades = list(self.store.cidades)

        def trabalho():
            for c in cidades:
                try:
                    d = api.previsao(c["lat"], c["lon"])
                except Exception:
                    continue
                main_thread(self._avisar, c, d)

        threading.Thread(target=trabalho, daemon=True).start()
        return True

    def _avisar(self, cidade, d):
        k = chave(cidade)
        self.dados[k] = d
        minutos = modelo.chuva_em_minutos(d)
        if minutos is None:
            self.avisados.discard(k)
            return
        if k in self.avisados:
            return
        self.avisados.add(k)
        n = Gio.Notification.new(f"Chuva em {cidade['nome']}")
        n.set_body(self._texto_chuva(minutos) + ".")
        n.set_icon(Gio.ThemedIcon.new("weather-showers-symbolic"))
        self.get_application().send_notification(f"chuva-{k}", n)
