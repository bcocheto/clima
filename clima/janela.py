import threading

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from . import api, modelo
from .busca import DialogoBusca
from .codigos import descrever
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


class Janela(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(
            application=app, title="Clima", default_width=1000, default_height=720
        )
        self.store = Store()
        self.dados = {}  # cache por chave da cidade
        self.cidade = None
        self.avisados = set()
        self._linhas_dias = []
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
        self.lista = Gtk.ListBox(css_classes=["navigation-sidebar"])
        self.lista.connect("row-selected", self._ao_selecionar)
        sb.set_content(Gtk.ScrolledWindow(child=self.lista))
        self.split.set_sidebar(sb)

        # conteúdo
        tv = Adw.ToolbarView()
        head = Adw.HeaderBar()
        toggle = Gtk.ToggleButton(
            icon_name="sidebar-show-symbolic", tooltip_text="Mostrar cidades"
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
            orientation=Gtk.Orientation.VERTICAL, spacing=18,
            margin_top=18, margin_bottom=24, margin_start=18, margin_end=18,
        )

        self.lbl_cidade = Gtk.Label(xalign=0, css_classes=["title-1"])
        self.lbl_regiao = Gtk.Label(xalign=0, css_classes=["dim-label"])
        titulo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        titulo.append(self.lbl_cidade)
        titulo.append(self.lbl_regiao)
        box.append(titulo)

        hero = Gtk.Box(spacing=18)
        self.img_atual = Gtk.Image(pixel_size=96)
        hero.append(self.img_atual)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.lbl_temp = Gtk.Label(xalign=0, use_markup=True)
        self.lbl_desc = Gtk.Label(xalign=0, css_classes=["title-3"])
        col.append(self.lbl_temp)
        col.append(self.lbl_desc)
        hero.append(col)
        box.append(hero)

        agora = Adw.PreferencesGroup(title="Agora")
        self.row_sensacao = self._row_info("Sensação térmica")
        self.row_umidade = self._row_info("Umidade")
        self.row_vento = self._row_info("Vento")
        self.row_chuva = self._row_info("Chuva")
        for r in (self.row_sensacao, self.row_umidade, self.row_vento, self.row_chuva):
            agora.add(r)
        box.append(agora)

        horas = Adw.PreferencesGroup(title="Próximas 24 horas")
        self.grafico = Grafico()
        card = Gtk.Box(css_classes=["card"])
        card.append(self.grafico)
        horas.add(card)
        box.append(horas)

        self.grupo_dias = Adw.PreferencesGroup(title="Próximos 7 dias")
        box.append(self.grupo_dias)

        return Gtk.ScrolledWindow(child=Adw.Clamp(maximum_size=720, child=box))

    @staticmethod
    def _row_info(titulo):
        return Adw.ActionRow(title=titulo, subtitle="—", css_classes=["property"])

    # ---------- cidades ----------
    def _popular_cidades(self, selecionar):
        while (r := self.lista.get_row_at_index(0)) is not None:
            self.lista.remove(r)
        for c in self.store.cidades:
            row = Adw.ActionRow(title=c["nome"], subtitle=c["regiao"], use_markup=False)
            rm = Gtk.Button(
                icon_name="list-remove-symbolic", valign=Gtk.Align.CENTER,
                css_classes=["flat"], tooltip_text="Remover",
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
        self.lbl_cidade.set_label(cidade["nome"])
        self.lbl_regiao.set_label(cidade["regiao"])
        self.img_atual.set_from_icon_name(icone)
        self.lbl_temp.set_markup(
            f'<span size="64000" weight="bold">{grau(atual["temperature_2m"])}</span>'
        )
        self.lbl_desc.set_label(desc)
        self.row_sensacao.set_subtitle(grau(atual["apparent_temperature"]))
        self.row_umidade.set_subtitle(f'{atual["relative_humidity_2m"]:.0f}%')
        self.row_vento.set_subtitle(f'{atual["wind_speed_10m"]:.0f} km/h')
        self.row_chuva.set_subtitle(self._texto_chuva(modelo.chuva_em_minutos(d)))

        self.grafico.set_horas(modelo.horas_seguintes(d))

        for r in self._linhas_dias:
            self.grupo_dias.remove(r)
        self._linhas_dias = []
        for i, dia_d in enumerate(modelo.dias(d)):
            nome, ic = descrever(dia_d["codigo"])
            row = Adw.ActionRow(
                title=modelo.nome_dia(i, dia_d["data"]),
                subtitle=f'{nome} · chuva {dia_d["chuva"]}%',
            )
            row.add_prefix(Gtk.Image(icon_name=ic, pixel_size=24))
            row.add_suffix(
                Gtk.Label(label=f'{grau(dia_d["max"])} / {grau(dia_d["min"])}',
                          css_classes=["numeric"])
            )
            self.grupo_dias.add(row)
            self._linhas_dias.append(row)

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
