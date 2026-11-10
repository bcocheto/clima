# Clima

App de clima para GNOME (Python + GTK4 + libadwaita). Dados da [Open-Meteo](https://open-meteo.com) (sem chave).

- Clima atual e previsão de 7 dias
- Próximas 24 h com gráfico de temperatura e chance de chuva
- Várias cidades com busca (lista salva em `~/.config/clima/cidades.json`)
- Alerta de chuva nas próximas 2 h (notificação do sistema, checagem a cada 10 min enquanto o app está aberto)

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
