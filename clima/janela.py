import threading
import time

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from . import APP_ID, __version__, api, fontes, modelo, observacao
from .busca import DialogoBusca
from .codigos import ambiente, descrever
from .config import cfg
from .grafico import Grafico
from .prefs import Preferencias
from .radar import DialogoRadar, MiniRadar
from .store import Store, chave


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
        self._linhas = {}  # chave da cidade -> (ícone, temperatura) na barra lateral
        self._timer = None
        self.oficiais = {}  # chave da cidade -> {"avisos", "inmet", "cptec"} (None/ausente = carregando, False = falhou)
        self._oficiais_t = {}  # quando as previsões oficiais foram pedidas
        self._avisos_cache = (0, [])
        self._avisos_vistos = {}  # chave -> ids de avisos já conhecidos
        self._lock = threading.Lock()

        acao = Gio.SimpleAction.new("preferencias", None)
        acao.connect("activate", lambda *_: Preferencias(self._ao_mudar_config).present(self))
        self.add_action(acao)
        sobre = Gio.SimpleAction.new("sobre", None)
        sobre.connect("activate", lambda *_: self._mostrar_sobre())
        self.add_action(sobre)
        app.set_accels_for_action("win.preferencias", ["<Ctrl>comma"])

        self._montar()
        self._popular_cidades(0)
        self._armar_timer()
        GLib.timeout_add_seconds(1, lambda: (self._buscar_todas(), False)[1])

    # ---------- interface ----------
    def _montar(self):
        self.toasts = Adw.ToastOverlay()
        self.split = Adw.OverlaySplitView(
            min_sidebar_width=240, max_sidebar_width=340, sidebar_width_fraction=0.28
        )
        self.toasts.set_child(self.split)
        self.set_content(self.toasts)

        # barra lateral
        sb = Adw.ToolbarView()
        head = Adw.HeaderBar(title_widget=Adw.WindowTitle(title="Cidades", subtitle=""))
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Adicionar cidade")
        add.connect("clicked", self._abrir_busca)
        head.pack_start(add)
        menu = Gio.Menu()
        menu.append("Preferências", "win.preferencias")
        menu.append("Sobre o Clima", "win.sobre")
        head.pack_end(
            Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu,
                           tooltip_text="Menu")
        )
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
        radar = Gtk.Button(icon_name="weather-showers-symbolic", tooltip_text="Radar de chuva")
        radar.connect("clicked", lambda *_: self.cidade and DialogoRadar(self.cidade).present(self))
        head.pack_end(radar)
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
        self.lbl_cidade = rotulo(classes=["title-2"])
        self.lbl_regiao = rotulo(classes=["clima-meta"])
        box.append(self.lbl_cidade)
        box.append(self.lbl_regiao)

        hero = Gtk.Box(spacing=20, margin_top=6, margin_bottom=6)
        self.img_atual = Gtk.Image(pixel_size=112)
        hero.append(self.img_atual)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, spacing=2)
        self.lbl_temp = rotulo(classes=["clima-temp"])
        self.lbl_desc = rotulo(classes=["title-3"])
        chips = Gtk.Box(spacing=6, margin_top=4)
        self.chip_minmax = rotulo(
            classes=["clima-chip"],
            tooltip_text="Temperaturas máxima e mínima previstas para hoje",
        )
        self.chip_sensacao = rotulo(
            classes=["clima-chip"],
            tooltip_text="Como a temperatura é sentida, considerando vento e umidade",
        )
        chips.append(self.chip_minmax)
        chips.append(self.chip_sensacao)
        for w in (self.lbl_temp, self.lbl_desc, chips):
            col.append(w)
        hero.append(col)
        box.append(hero)

        # avisos oficiais (INMET) — só para cidades no Brasil
        self.secao_avisos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.secao_avisos.append(rotulo("Avisos oficiais · INMET", ["clima-secao"]))
        self.avisos_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.secao_avisos.append(self.avisos_box)
        box.append(self.secao_avisos)

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
        self.val_sensacao = self._tile(
            tiles, "Sensação térmica",
            "Como a temperatura é sentida pelo corpo, considerando vento e umidade.",
        )
        self.val_umidade = self._tile(
            tiles, "Umidade",
            "Umidade relativa do ar. Valores altos deixam o calor mais abafado.",
        )
        self.val_vento = self._tile(
            tiles, "Vento", "Velocidade do vento a 10 metros do solo."
        )
        self.val_chuva = self._tile(
            tiles, "Chance de chuva hoje",
            "Maior probabilidade de chuva em qualquer momento do dia de hoje.",
        )
        box.append(tiles)

        # próximas horas
        box.append(rotulo("Próximas 24 horas", ["clima-secao"]))
        box.append(rotulo(
            "Linha: temperatura · Barras: chance de chuva · Passe o mouse sobre uma hora",
            ["clima-meta"], margin_start=4,
        ))
        card = Gtk.Box(css_classes=["clima-card"])
        self.grafico = Grafico()
        card.append(self.grafico)
        box.append(card)

        # radar (mini, sempre animado) — fica junto das horas, que respondem "vai chover?"
        box.append(rotulo("Radar de chuva", ["clima-secao"]))
        self.mini_radar = MiniRadar(lambda c: DialogoRadar(c).present(self))
        box.append(self.mini_radar)

        # próximos dias
        box.append(rotulo("Próximos 7 dias", ["clima-secao"]))
        self.dias_box = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
            min_children_per_line=2, max_children_per_line=7,
            column_spacing=8, row_spacing=8,
        )
        box.append(self.dias_box)

        # comparação entre fontes — só para cidades no Brasil
        self.secao_fontes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.secao_fontes.append(rotulo("Comparar fontes", ["clima-secao"]))
        card_fontes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                              css_classes=["clima-card"])
        self.grade_fontes = Gtk.Grid(column_spacing=12, row_spacing=10, column_homogeneous=True)
        card_fontes.append(self.grade_fontes)
        self.rodape_fontes = rotulo(classes=["clima-meta"], wrap=True)
        card_fontes.append(self.rodape_fontes)
        self.secao_fontes.append(card_fontes)
        box.append(self.secao_fontes)

        self.fundo = Gtk.ScrolledWindow(
            child=Adw.Clamp(maximum_size=960, child=box), css_classes=["clima-fundo"]
        )
        return self.fundo

    @staticmethod
    def _tile(flowbox, titulo, dica):
        tile = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=2,
            css_classes=["clima-card"], tooltip_text=dica,
        )
        tile.append(rotulo(titulo, ["clima-meta"]))
        valor = rotulo(classes=["clima-valor"])
        tile.append(valor)
        flowbox.append(tile)
        return valor

    @staticmethod
    def _tile_dia(i, d):
        nome, icone = descrever(d["codigo"])
        dica = (
            f'{modelo.nome_dia(i, d["data"]):s} — {nome}\n'
            f'Máxima: {cfg.fmt_temp(d["max"])}  ·  Mínima: {cfg.fmt_temp(d["min"])}\n'
            f'Chance de chuva: {d["chuva"]}%'
        )
        tile = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=4,
            css_classes=["clima-card", "clima-dia"], tooltip_text=dica,
        )
        rot = rotulo(modelo.nome_dia(i, d["data"]), ["heading"])
        rot.set_halign(Gtk.Align.CENTER)
        tile.append(rot)
        tile.append(Gtk.Image(icon_name=icone, pixel_size=32, margin_top=2, margin_bottom=2))
        for texto, classe in ((cfg.fmt_temp(d["max"]), "clima-valor"),
                              (cfg.fmt_temp(d["min"]), "clima-meta"),
                              (f'{d["chuva"]}%', "clima-chuva-pct")):
            r = rotulo(texto, [classe])
            r.set_halign(Gtk.Align.CENTER)
            tile.append(r)
        return tile

    # ---------- cidades ----------
    def _popular_cidades(self, selecionar):
        while (r := self.lista.get_row_at_index(0)) is not None:
            self.lista.remove(r)
        self._linhas = {}
        for c in self.store.cidades:
            row = Adw.ActionRow(title=c["nome"], subtitle=c["regiao"], use_markup=False)
            icone = Gtk.Image(pixel_size=24, visible=False)
            row.add_prefix(icone)
            temp = Gtk.Label(css_classes=["clima-valor", "numeric"])
            row.add_suffix(temp)
            rm = Gtk.Button(
                icon_name="list-remove-symbolic", valign=Gtk.Align.CENTER,
                css_classes=["flat", "circular"], tooltip_text="Remover cidade",
            )
            rm.connect("clicked", lambda _b, c=c: self._remover(c))
            row.add_suffix(rm)
            self.lista.append(row)
            self._linhas[chave(c)] = (icone, temp, row)
            self._atualizar_linha(c)
        if self.store.cidades:
            n = max(0, min(selecionar, len(self.store.cidades) - 1))
            self.lista.select_row(self.lista.get_row_at_index(n))
        else:
            self.cidade = None
            self.stack.set_visible_child_name("vazio")

    def _atualizar_linha(self, cidade):
        k = chave(cidade)
        if k not in self._linhas or k not in self.dados:
            return
        icone, temp, row = self._linhas[k]
        atual = self.dados[k]["current"]
        desc, nome_icone = descrever(atual["weather_code"], bool(atual.get("is_day", 1)))
        icone.set_from_icon_name(nome_icone)
        icone.set_visible(True)
        temp.set_label(cfg.fmt_temp(atual["temperature_2m"]))
        row.set_tooltip_text(f'{desc} agora em {cidade["nome"]}')

    def _abrir_busca(self, *_):
        DialogoBusca(self._adicionar).present(self)

    def _adicionar(self, cidade):
        self._popular_cidades(self.store.adicionar(cidade))
        self._buscar_todas()

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
        self._buscar_oficiais(cidade, previsoes=True, forcar=forcar)
        if k in self.dados and not forcar:
            self._mostrar(cidade, self.dados[k])
            return
        if k not in self.dados:
            self.stack.set_visible_child_name("carregando")

        def ok(d):
            self.dados[k] = d
            self._atualizar_linha(cidade)
            if self.cidade is cidade:
                self._mostrar(cidade, d)

        def erro(e):
            self.toasts.add_toast(Adw.Toast(title=f"Falha ao buscar previsão: {e}"))
            if self.cidade is cidade and k in self.dados:
                self._mostrar(cidade, self.dados[k])

        em_thread(lambda: observacao.previsao_refinada(cidade["lat"], cidade["lon"]), ok, erro)

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
        self.img_atual.set_tooltip_text(desc)
        self.lbl_temp.set_label(cfg.fmt_temp(atual["temperature_2m"]))
        self.lbl_desc.set_label(desc)
        fontes_aj = d.get("ajuste", {}).get("fontes")
        self.lbl_desc.set_tooltip_text(
            "Ajustado por consenso: " + ", ".join(fontes_aj) if fontes_aj else None
        )
        self.chip_minmax.set_label(
            f'Máx {cfg.fmt_temp(dias[0]["max"])} · Mín {cfg.fmt_temp(dias[0]["min"])}'
        )
        self.chip_sensacao.set_label(f'Sensação {cfg.fmt_temp(atual["apparent_temperature"])}')

        self.val_sensacao.set_label(cfg.fmt_temp(atual["apparent_temperature"]))
        self.val_umidade.set_label(f'{atual["relative_humidity_2m"]:.0f}%')
        self.val_vento.set_label(cfg.fmt_vento(atual["wind_speed_10m"]))
        self.val_chuva.set_label(f'{dias[0]["chuva"]}%')

        minutos = modelo.chuva_em_minutos(d, janela_min=cfg.get("antecedencia_min"))
        self.aviso_texto.set_label(self._texto_chuva(minutos))
        self.aviso_icone.set_from_icon_name(
            "weather-showers-symbolic" if minutos is not None else "weather-clear-symbolic"
        )
        if minutos is not None:
            self.aviso.add_css_class("chuva")
        else:
            self.aviso.remove_css_class("chuva")

        self.grafico.set_horas(modelo.horas_seguintes(d))
        self.mini_radar.definir_cidade(cidade)

        self.dias_box.remove_all()
        for i, dia_d in enumerate(dias):
            self.dias_box.append(self._tile_dia(i, dia_d))

        self.stack.set_visible_child_name("dados")
        self._mostrar_oficiais()

    @staticmethod
    def _texto_chuva(minutos):
        if minutos is None:
            return f"Sem chuva prevista nos próximos {cfg.texto_janela()}"
        if minutos <= 0:
            return "Chovendo agora"
        return f"Chuva prevista em cerca de {minutos} min"

    # ---------- sobre ----------
    def _mostrar_sobre(self):
        d = Adw.AboutDialog(
            application_name="Clima",
            application_icon=APP_ID,
            developer_name="Breno Cocheto",
            version=__version__,
            website="https://github.com/bcocheto/clima",
            issue_url="https://github.com/bcocheto/clima/issues",
            license_type=Gtk.License.GPL_3_0,
            copyright="© 2026 Breno Cocheto",
            comments="Previsão do tempo com avisos oficiais no Brasil.",
        )
        d.add_link("Dados meteorológicos: Open-Meteo.com", "https://open-meteo.com/")
        d.add_legal_section(
            "Fontes de dados",
            None,
            Gtk.License.CUSTOM,
            'Dados meteorológicos de <a href="https://open-meteo.com/">Open-Meteo.com</a> '
            '(licença <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).\n\n'
            "Para cidades no Brasil: avisos e previsões do INMET, previsão do CPTEC/INPE "
            "(via BrasilAPI) e códigos de município do IBGE.",
        )
        d.present(self)

    # ---------- preferências ----------
    def _ao_mudar_config(self):
        for c in self.store.cidades:
            self._atualizar_linha(c)
        if self.cidade is not None and chave(self.cidade) in self.dados:
            self._mostrar(self.cidade, self.dados[chave(self.cidade)])
        self._armar_timer()
        if self.cidade is not None:
            self._buscar_oficiais(self.cidade)

    def _armar_timer(self):
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add_seconds(cfg.get("intervalo_min") * 60, self._tick)

    def _tick(self):
        self._buscar_todas()
        return True

    # ---------- atualização em segundo plano e alerta de chuva ----------
    def _buscar_todas(self):
        cidades = list(self.store.cidades)

        def trabalho():
            for c in cidades:
                try:
                    d = observacao.previsao_refinada(c["lat"], c["lon"])
                except Exception:
                    continue
                main_thread(self._ao_receber, c, d)

        threading.Thread(target=trabalho, daemon=True).start()

    def _ao_receber(self, cidade, d):
        k = chave(cidade)
        if k not in self._linhas:  # cidade removida enquanto buscava
            return
        self.dados[k] = d
        self._atualizar_linha(cidade)
        if self.cidade is not None and chave(self.cidade) == k:
            self._mostrar(self.cidade, d)
        self._avisar_chuva(cidade, d)
        atual = self.cidade is not None and chave(self.cidade) == k
        self._buscar_oficiais(cidade, previsoes=atual)

    def _avisar_chuva(self, cidade, d):
        if not cfg.get("alertas"):
            return
        k = chave(cidade)
        minutos = modelo.chuva_em_minutos(d, janela_min=cfg.get("antecedencia_min"))
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

    # ---------- fontes oficiais (Brasil) ----------
    def _fontes_ativas(self, cidade):
        return bool(cfg.get("fontes_br")) and fontes.no_brasil(cidade)

    def _avisos_todos(self):
        """Lista de avisos do INMET; baixada no máximo a cada 5 min e compartilhada."""
        with self._lock:
            t, lista = self._avisos_cache
            if time.time() - t < 300:
                return lista
            lista = fontes.baixar_avisos()
            self._avisos_cache = (time.time(), lista)
            return lista

    def _buscar_oficiais(self, cidade, previsoes=True, forcar=False):
        if not self._fontes_ativas(cidade):
            return
        k = chave(cidade)
        agora = time.time()
        previsoes = previsoes and (forcar or agora - self._oficiais_t.get(k, 0) > 1800)
        if previsoes:
            self._oficiais_t[k] = agora

        def trabalho():
            res = {}
            try:
                res["ibge"] = fontes.achar_ibge(cidade)
            except Exception:
                res["ibge"] = None
            try:
                res["avisos"] = fontes.avisos_da_cidade(
                    self._avisos_todos(), cidade, res["ibge"]
                )
            except Exception:
                res["avisos"] = False
            if previsoes:
                try:
                    res["inmet"] = fontes.previsao_inmet(res["ibge"]) if res["ibge"] else []
                except Exception:
                    res["inmet"] = False
                try:
                    r = fontes.previsao_cptec(cidade)
                    res["cptec_id"], res["cptec"] = r if r else (None, [])
                except Exception:
                    res["cptec"] = False
            main_thread(self._ao_receber_oficiais, cidade, res)

        threading.Thread(target=trabalho, daemon=True).start()

    def _ao_receber_oficiais(self, cidade, res):
        k = chave(cidade)
        if k not in self._linhas:  # cidade removida enquanto buscava
            return
        mudou = False
        for campo, valor in (("ibge", res.get("ibge")), ("cptec", res.get("cptec_id"))):
            if valor and cidade.get(campo) != valor:
                cidade[campo] = valor
                mudou = True
        if mudou:
            self.store.salvar()
        of = self.oficiais.setdefault(k, {})
        for campo in ("avisos", "inmet", "cptec"):
            if campo in res:
                of[campo] = res[campo]

        avisos = res.get("avisos")
        if isinstance(avisos, list):
            conhecidos = self._avisos_vistos.get(k)
            if conhecidos is not None and cfg.get("alertas"):
                for a in avisos:
                    if a["id"] not in conhecidos:
                        self._notificar_aviso(cidade, a)
            self._avisos_vistos[k] = (conhecidos or set()) | {a["id"] for a in avisos}

        if self.cidade is not None and chave(self.cidade) == k:
            self._mostrar_oficiais()

    def _notificar_aviso(self, cidade, aviso):
        n = Gio.Notification.new(f"Aviso do INMET em {cidade['nome']}")
        n.set_body(f"{aviso['titulo']} — {aviso['severidade']} (até {aviso['fim']}).")
        n.set_icon(Gio.ThemedIcon.new("weather-severe-alert-symbolic"))
        self.get_application().send_notification(f"aviso-{chave(cidade)}-{aviso['id']}", n)

    def _mostrar_oficiais(self):
        self._mostrar_avisos()
        self._mostrar_fontes()

    @staticmethod
    def _limpar(container):
        while (filho := container.get_first_child()) is not None:
            container.remove(filho)

    def _mostrar_avisos(self):
        cidade = self.cidade
        ativo = cidade is not None and self._fontes_ativas(cidade)
        self.secao_avisos.set_visible(ativo)
        if not ativo:
            return
        self._limpar(self.avisos_box)
        avisos = self.oficiais.get(chave(cidade), {}).get("avisos")
        if avisos is None:
            self.avisos_box.append(self._card_simples("Consultando avisos do INMET…"))
        elif avisos is False:
            self.avisos_box.append(
                self._card_simples("Não foi possível consultar os avisos do INMET agora.")
            )
        elif not avisos:
            self.avisos_box.append(
                self._card_simples("Nenhum aviso oficial ativo para esta cidade.")
            )
        else:
            for a in avisos:
                self.avisos_box.append(self._card_aviso(a))

    @staticmethod
    def _card_simples(texto):
        card = Gtk.Box(css_classes=["clima-card", "clima-aviso"])
        card.append(rotulo(texto, ["clima-meta"], wrap=True))
        return card

    @staticmethod
    def _card_aviso(a):
        classe = {"Perigo Potencial": "sev-potencial", "Perigo": "sev-perigo",
                  "Grande Perigo": "sev-grande"}.get(a["severidade"], "sev-potencial")
        cab = Gtk.Box(spacing=10)
        cab.append(rotulo(a["severidade"], ["clima-chip", classe], valign=Gtk.Align.CENTER))
        cab.append(rotulo(a["titulo"], ["heading"], hexpand=True))
        cab.append(rotulo(f'até {a["fim"]}', ["clima-meta"], valign=Gtk.Align.CENTER))

        corpo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=10)
        corpo.append(rotulo(f'Vigente de {a["inicio"]} até {a["fim"]}', ["clima-meta"]))
        for titulo, itens in (("Riscos", a["riscos"]), ("O que fazer", a["instrucoes"])):
            if itens:
                corpo.append(rotulo(titulo, ["clima-secao"]))
                for item in itens:
                    corpo.append(rotulo(f"• {item}", wrap=True))
        corpo.append(rotulo("Fonte: INMET", ["clima-meta"], margin_top=4))

        exp = Gtk.Expander(label_widget=cab, child=corpo)
        card = Gtk.Box(css_classes=["clima-card", "clima-alerta", classe])
        card.append(exp)
        exp.set_hexpand(True)
        return card

    def _mostrar_fontes(self):
        cidade = self.cidade
        d = self.dados.get(chave(cidade)) if cidade is not None else None
        ativo = d is not None and self._fontes_ativas(cidade)
        self.secao_fontes.set_visible(ativo)
        if not ativo:
            return
        of = self.oficiais.get(chave(cidade), {})
        om = {x["data"]: x for x in modelo.dias(d)}
        datas = sorted(om)[:4]
        self._limpar(self.grade_fontes)

        def por_data(lista):
            if lista is None:
                return "carregando"
            if not lista:
                return "indisponivel"
            return {x["data"]: x for x in lista}

        def dica_om(x):
            return f'{descrever(x["codigo"])[0]}\nChance de chuva: {x["chuva"]}%'

        def dica_inmet(x):
            u = x["umidade"]
            return (f'{x["resumo"]}\nUmidade: {u[0]}–{u[1]}%\nVento: {x["vento"]}'
                    if u[0] is not None else f'{x["resumo"]}\nVento: {x["vento"]}')

        def dica_cptec(x):
            return f'{x["resumo"]}\nÍndice UV: {x["uv"]}'

        grade = self.grade_fontes
        grade.attach(rotulo("Fonte", ["clima-meta"]), 0, 0, 1, 1)
        for j, dt in enumerate(datas, start=1):
            r = rotulo(modelo.nome_dia(j - 1, dt), ["clima-meta"])
            r.set_halign(Gtk.Align.CENTER)
            grade.attach(r, j, 0, 1, 1)

        linhas = (
            ("Open-Meteo", om, dica_om),
            ("INMET", por_data(of.get("inmet")), dica_inmet),
            ("CPTEC/INPE", por_data(of.get("cptec")), dica_cptec),
        )
        for i, (nome, dados_f, dica) in enumerate(linhas, start=1):
            grade.attach(rotulo(nome, ["heading"]), 0, i, 1, 1)
            for j, dt in enumerate(datas, start=1):
                x = dados_f.get(dt) if isinstance(dados_f, dict) else None
                if dados_f == "carregando":
                    texto, tip = "…", "Consultando…"
                elif x is None or x["max"] is None or x["min"] is None:
                    texto, tip = "—", "Sem dados desta fonte para este dia"
                else:
                    texto, tip = f'{cfg.fmt_temp(x["max"])} / {cfg.fmt_temp(x["min"])}', dica(x)
                cel = rotulo(texto, ["clima-valor"], tooltip_text=tip)
                cel.set_halign(Gtk.Align.CENTER)
                grade.attach(cel, j, i, 1, 1)

        inmet = of.get("inmet")
        extra = ""
        if inmet:
            hoje = inmet[0]
            if hoje.get("nascer") and hoje.get("ocaso"):
                extra = f' Sol: nasce {hoje["nascer"]}, põe {hoje["ocaso"]} (INMET).'
        self.rodape_fontes.set_label(
            "Máxima / mínima de cada fonte; passe o mouse para ver o resumo." + extra
        )
