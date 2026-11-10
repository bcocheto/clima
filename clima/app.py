import sys

from gi.repository import Adw

from . import APP_ID
from .janela import Janela


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        win = self.props.active_window or Janela(self)
        win.present()


def main():
    return App().run(sys.argv)
