# Clima

App de clima para GNOME (Python + GTK4 + libadwaita). Dados da [Open-Meteo](https://open-meteo.com) (sem chave).

- Clima atual e previsão de 7 dias
- Próximas 24 h com gráfico de temperatura e chance de chuva
- Várias cidades com busca (lista salva em `~/.config/clima/cidades.json`)
- Dicas ao passar o mouse: cada hora do gráfico, cada dia e cada card explicam o que significam
- Barra lateral com ícone e temperatura atual de cada cidade
- Preferências (Ctrl+, ou menu ⋮): °C/°F, km/h/mph/m/s, alerta de chuva ligado/desligado, antecedência (30 min a 2 h) e intervalo de atualização (salvas em `~/.config/clima/config.json`)
- Cidades no Brasil: avisos oficiais do INMET (severidade, riscos e o que fazer), comparação de máx/mín entre Open-Meteo, INMET e CPTEC/INPE, e notificação de aviso novo (pode ser desligado nas Preferências)
- Alerta de chuva por notificação do sistema enquanto o app está aberto

## Rodar

```bash
python3 -m clima
```

Para ter o atalho no menu, o ícone e as notificações do GNOME (o ID precisa casar com `io.github.bcocheto.Clima`):

```bash
make install     # make uninstall para remover
```

## Testes

```bash
make test
```

## Fontes

| Fonte | Uso |
|---|---|
| [Open-Meteo](https://open-meteo.com) | previsão principal e busca de cidades |
| [INMET](https://apiprevmet3.inmet.gov.br) | avisos ativos e previsão por município (Brasil) |
| [CPTEC/INPE](https://brasilapi.com.br) via BrasilAPI | previsão de 4 dias com índice UV (Brasil) |
| [IBGE](https://servicodados.ibge.gov.br) | código do município, guardado em `~/.cache/clima/municipios.json` |

## Licença

GPL-3.0, como o [Gavetta](https://github.com/bcocheto/gavetta) e a [Cadência](https://github.com/bcocheto/cadencia).
