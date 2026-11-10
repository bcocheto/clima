from gi.repository import Adw, GObject, Gtk

from .config import cfg

TEMPERATURAS = [("C", "Celsius (°C)"), ("F", "Fahrenheit (°F)")]
VENTOS = [("kmh", "Quilômetros por hora (km/h)"), ("mph", "Milhas por hora (mph)"),
          ("ms", "Metros por segundo (m/s)")]
ANTECEDENCIAS = [(30, "30 minutos"), (60, "1 hora"), (120, "2 horas")]
INTERVALOS = [(5, "5 minutos"), (10, "10 minutos"), (30, "30 minutos")]


class Preferencias(Adw.PreferencesDialog):
    """As mudanças valem na hora; `ao_mudar` avisa a janela para redesenhar."""

    def __init__(self, ao_mudar):
        super().__init__(title="Preferências")
        self._ao_mudar = ao_mudar
        pagina = Adw.PreferencesPage()

        unidades = Adw.PreferencesGroup(title="Unidades")
        unidades.add(self._combo("Temperatura", "temperatura", TEMPERATURAS))
        unidades.add(self._combo("Vento", "vento", VENTOS))
        pagina.add(unidades)

        alertas = Adw.PreferencesGroup(
            title="Alertas de chuva",
            description="O app confere a previsão enquanto estiver aberto.",
        )
        ligado = Adw.SwitchRow(
            title="Avisar quando for chover",
            subtitle="Notificação do sistema",
            active=cfg.get("alertas"),
        )
        ligado.connect("notify::active", lambda r, _p: self._set("alertas", r.get_active()))
        alertas.add(ligado)
        for linha in (
            self._combo("Avisar com antecedência de", "antecedencia_min", ANTECEDENCIAS),
            self._combo("Atualizar a cada", "intervalo_min", INTERVALOS),
        ):
            ligado.bind_property("active", linha, "sensitive", GObject.BindingFlags.SYNC_CREATE)
            alertas.add(linha)
        pagina.add(alertas)
        self.add(pagina)

    def _combo(self, titulo, chave, opcoes):
        linha = Adw.ComboRow(title=titulo, model=Gtk.StringList.new([t for _, t in opcoes]))
        atual = cfg.get(chave)
        linha.set_selected(next((i for i, (v, _) in enumerate(opcoes) if v == atual), 0))
        linha.connect(
            "notify::selected", lambda r, _p: self._set(chave, opcoes[r.get_selected()][0])
        )
        return linha

    def _set(self, chave, valor):
        cfg.set(chave, valor)
        self._ao_mudar()
