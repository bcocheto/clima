from gi.repository import Adw, GLib, Gtk

from . import api


class DialogoBusca(Adw.Dialog):
    """Pesquisa de cidades (geocoding Open-Meteo)."""

    def __init__(self, ao_escolher):
        super().__init__(title="Adicionar cidade", content_width=420, content_height=480)
        self._ao_escolher = ao_escolher
        self._resultados = []
        self._debounce = None
        self._consulta = ""

        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            margin_top=12, margin_bottom=12, margin_start=12, margin_end=12,
        )
        self.entrada = Gtk.SearchEntry(placeholder_text="Nome da cidade")
        self.entrada.connect("search-changed", self._ao_digitar)
        box.append(self.entrada)

        self.status = Gtk.Label(css_classes=["dim-label"], wrap=True)
        box.append(self.status)

        self.lista = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        self.lista.connect("row-activated", self._ao_ativar)
        box.append(Gtk.ScrolledWindow(child=self.lista, vexpand=True))
        tv.set_content(box)
        self.set_child(tv)
        self.set_focus(self.entrada)

    def _ao_digitar(self, entrada):
        if self._debounce:
            GLib.source_remove(self._debounce)
        self._debounce = GLib.timeout_add(400, self._buscar)

    def _buscar(self):
        self._debounce = None
        texto = self.entrada.get_text().strip()
        self._consulta = texto
        if len(texto) < 2:
            self._limpar()
            self.status.set_label("")
            return False
        self.status.set_label("Buscando…")

        import threading

        def run():
            try:
                res = api.buscar_cidades(texto)
            except Exception as e:
                GLib.idle_add(lambda: (self._mostrar(texto, [], str(e)), False)[1])
                return
            GLib.idle_add(lambda: (self._mostrar(texto, res, None), False)[1])

        threading.Thread(target=run, daemon=True).start()
        return False

    def _limpar(self):
        self._resultados = []
        while (r := self.lista.get_row_at_index(0)) is not None:
            self.lista.remove(r)

    def _mostrar(self, texto, resultados, erro):
        if texto != self._consulta:  # resposta atrasada
            return
        self._limpar()
        self._resultados = resultados
        for c in resultados:
            self.lista.append(
                Adw.ActionRow(
                    title=c["nome"], subtitle=c["regiao"], activatable=True, use_markup=False
                )
            )
        if erro:
            self.status.set_label(f"Falha na busca: {erro}")
        else:
            self.status.set_label("" if resultados else "Nenhuma cidade encontrada.")

    def _ao_ativar(self, _lista, row):
        self._ao_escolher(self._resultados[row.get_index()])
        self.close()
