"""Gráfico das próximas horas desenhado com GtkSnapshot (sem depender de cairo)."""
import gi

gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Graphene, Gsk, Gtk, Pango  # noqa: E402


def grau(t):
    return f"{round(t)}°"


class Grafico(Gtk.Widget):
    ALTURA = 170

    def __init__(self):
        super().__init__(hexpand=True)
        self.horas = []  # [(HH:MM, temperatura, prob. chuva %)]

    def set_horas(self, horas):
        self.horas = horas
        self.queue_draw()

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
        px, topo, base = 24, 30, 26
        alt = h - topo - base
        temps = [t for _, t, _ in self.horas]
        tmin, tmax = min(temps), max(temps)
        span = max(tmax - tmin, 1)

        def x(i):
            return px + (w - 2 * px) * i / (n - 1)

        def y(t):
            return topo + alt * (1 - (t - tmin) / span)

        # barras: probabilidade de chuva
        barra = ac.copy()
        barra.alpha = 0.22
        bw = (w - 2 * px) / n * 0.7
        for i, (_, _, p) in enumerate(self.horas):
            bh = alt * p / 100
            if bh > 0:
                snapshot.append_color(
                    barra, Graphene.Rect().init(x(i) - bw / 2, h - base - bh, bw, bh)
                )

        # linha de temperatura
        pb = Gsk.PathBuilder.new()
        for i, (_, t, _) in enumerate(self.horas):
            (pb.move_to if i == 0 else pb.line_to)(x(i), y(t))
        stroke = Gsk.Stroke.new(2.5)
        stroke.set_line_cap(Gsk.LineCap.ROUND)
        stroke.set_line_join(Gsk.LineJoin.ROUND)
        snapshot.append_stroke(pb.to_path(), stroke, ac)

        # rótulos a cada 3 h
        for i in range(0, n, 3):
            hora, t, _ = self.horas[i]
            self._texto(snapshot, hora, x(i), h - 6, fg_suave)
            self._texto(snapshot, grau(t), x(i), y(t) - 6, fg_suave)
