import sys
from pathlib import Path

from gi.repository import Adw, Gdk, Gtk

from . import APP_ID
from .janela import Janela


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Adw.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_string(Path(__file__).with_name("estilo.css").read_text(encoding="utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_activate(self):
        win = self.props.active_window or Janela(self)
        win.present()


def main():
    return App().run(sys.argv)
