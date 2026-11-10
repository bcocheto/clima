project('clima',
  version: '0.1.1',
  meson_version: '>= 0.62.0',
  license: 'GPL-3.0-or-later',
)

app_id = 'io.github.bcocheto.Clima'
py = import('python').find_installation('python3')

py.install_sources(
  files(
    'clima/__init__.py',
    'clima/__main__.py',
    'clima/api.py',
    'clima/app.py',
    'clima/busca.py',
    'clima/codigos.py',
    'clima/config.py',
    'clima/fontes.py',
    'clima/grafico.py',
    'clima/janela.py',
    'clima/modelo.py',
    'clima/prefs.py',
    'clima/store.py',
    'clima/estilo.css',
  ),
  subdir: 'clima',
)

install_data('bin/clima',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)
install_data('data/@0@.desktop'.format(app_id),
  install_dir: get_option('datadir') / 'applications',
)
install_data('data/@0@.metainfo.xml'.format(app_id),
  install_dir: get_option('datadir') / 'metainfo',
)
install_data('data/icons/hicolor/scalable/apps/@0@.svg'.format(app_id),
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps',
)
install_data('data/icons/hicolor/symbolic/apps/@0@-symbolic.svg'.format(app_id),
  install_dir: get_option('datadir') / 'icons/hicolor/symbolic/apps',
)
