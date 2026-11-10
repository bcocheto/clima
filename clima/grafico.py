"""Gráfico das próximas horas desenhado com GtkSnapshot (sem depender de cairo).

Passar o mouse sobre uma coluna destaca a hora e abre uma dica com os detalhes.
"""
import gi

gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Graphene, Gsk, Gtk, Pango  # noqa: E402

from .codigos import descrever  # noqa: E402
from .config import cfg  # noqa: E402

PX, TOPO, BASE = 24, 30, 26


class Grafico(Gtk.Widget):
    ALTURA = 170

    def __init__(self):
        super().__init__(hexpand=True, has_tooltip=True)
        self.horas = []  # [(HH:MM, temperatura, prob. chuva %, código do tempo)]
        self.hover = None
        mov = Gtk.EventControllerMotion()
        mov.connect("motion", self._ao_mover)
        mov.connect("leave", self._ao_sair)
        self.add_controller(mov)
        self.connect("query-tooltip", self._dica)

    def set_horas(self, horas):
        self.horas = horas
        self.hover = None
        self.queue_draw()

    # ---------- geometria ----------
    def _indice(self, x):
        n = len(self.horas)
        if n < 2:
            return None
        passo = (self.get_width() - 2 * PX) / (n - 1)
        i = round((x - PX) / passo)
        return max(0, min(n - 1, i))

    def _x(self, i):
        return PX + (self.get_width() - 2 * PX) * i / (len(self.horas) - 1)

    def _y(self, t):
        temps = [h[1] for h in self.horas]
        tmin, tmax = min(temps), max(temps)
        alt = self.get_height() - TOPO - BASE
        return TOPO + alt * (1 - (t - tmin) / max(tmax - tmin, 1))

    # ---------- interação ----------
    def _ao_mover(self, _ctl, x, _y):
        i = self._indice(x)
        if i != self.hover:
            self.hover = i
            self.queue_draw()
            self.trigger_tooltip_query()

    def _ao_sair(self, _ctl):
        self.hover = None
        self.queue_draw()

    def _dica(self, _w, _x, _y, _teclado, tooltip):
        if self.hover is None:
            return False
        hora, temp, prob, cod = self.horas[self.hover]
        desc, _ = descrever(cod, dia=6 <= int(hora[:2]) < 18)
        tooltip.set_text(
            f"{hora} — {desc}\n"
            f"Temperatura: {cfg.fmt_temp(temp)}\n"
            f"Chance de chuva: {prob}% (probabilidade de chover nessa hora)"
        )
        return True

    # ---------- desenho ----------
    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.VERTICAL:
            return self.ALTURA, self.ALTURA, -1, -1
        return 240, 240, -1, -1

    def _texto(self, snapshot, texto, cx, base_y, cor):
        layout = self.create_pango_layout(texto)
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_scale_new(0.85))
        layout.set_attributes(attrs)
        tw, th = layout.get_pixel_size()
        snapshot.save()
        snapshot.translate(Graphene.Point().init(cx - tw / 2, base_y - th))
        snapshot.append_layout(layout, cor)
        snapshot.restore()

    def do_snapshot(self, snapshot):
        n = len(self.horas)
        if n < 2:
            return
        w, h = self.get_width(), self.get_height()
        fg = self.get_color()
        ac = Adw.StyleManager.get_default().get_accent_color_rgba()
        fg_suave = fg.copy()
        fg_suave.alpha = 0.85
        alt = h - TOPO - BASE
        passo = (w - 2 * PX) / (n - 1)

        # faixa da coluna sob o mouse
        if self.hover is not None:
            faixa = fg.copy()
            faixa.alpha = 0.08
            snapshot.append_color(
                faixa, Graphene.Rect().init(self._x(self.hover) - passo / 2, 4, passo, h - 8)
            )

        # barras: probabilidade de chuva
        barra = ac.copy()
        barra.alpha = 0.22
        bw = passo * 0.7
        for i, (_, _, p, _) in enumerate(self.horas):
            bh = alt * p / 100
            if bh > 0:
                snapshot.append_color(
                    barra, Graphene.Rect().init(self._x(i) - bw / 2, h - BASE - bh, bw, bh)
                )

        # linha de temperatura
        pb = Gsk.PathBuilder.new()
        for i, (_, t, _, _) in enumerate(self.horas):
            (pb.move_to if i == 0 else pb.line_to)(self._x(i), self._y(t))
        stroke = Gsk.Stroke.new(2.5)
        stroke.set_line_cap(Gsk.LineCap.ROUND)
        stroke.set_line_join(Gsk.LineJoin.ROUND)
        snapshot.append_stroke(pb.to_path(), stroke, ac)

        # ponto na hora destacada
        if self.hover is not None:
            cx, cy = self._x(self.hover), self._y(self.horas[self.hover][1])
            pb = Gsk.PathBuilder.new()
            pb.add_circle(Graphene.Point().init(cx, cy), 5)
            snapshot.append_fill(pb.to_path(), Gsk.FillRule.WINDING, ac)

        # rótulos a cada 3 h (e na hora destacada)
        for i in range(n):
            if i % 3 and i != self.hover:
                continue
            hora, t, _, _ = self.horas[i]
            cor = fg if i == self.hover else fg_suave
            self._texto(snapshot, hora, self._x(i), h - 6, cor)
            self._texto(snapshot, cfg.fmt_temp(t), self._x(i), self._y(t) - 8, cor)
