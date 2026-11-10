# Clima

App de clima para GNOME (Python + GTK4 + libadwaita). Dados da [Open-Meteo](https://open-meteo.com) (sem chave).

- Clima atual e previsão de 7 dias
- Próximas 24 h com gráfico de temperatura e chance de chuva
- Várias cidades com busca (lista salva em `~/.config/clima/cidades.json`)
- Dicas ao passar o mouse: cada hora do gráfico, cada dia e cada card explicam o que significam
- Barra lateral com ícone e temperatura atual de cada cidade
- Preferências (Ctrl+, ou menu ⋮): °C/°F, km/h/mph/m/s, alerta de chuva ligado/desligado, antecedência (30 min a 2 h) e intervalo de atualização (salvas em `~/.config/clima/config.json`)
- Alerta de chuva por notificação do sistema enquanto o app está aberto

## Rodar

```bash
python3 -m clima
```

Para as notificações aparecerem no GNOME, instale o `.desktop` (o ID precisa casar com `io.github.bcocheto.Clima`):

```bash
cp data/io.github.bcocheto.Clima.desktop ~/.local/share/applications/
```

## Testes

```bash
python3 -m unittest discover -s tests
```
