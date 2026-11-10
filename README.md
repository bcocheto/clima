<div align="center">

<img src="data/icons/hicolor/scalable/apps/io.github.bcocheto.Clima.svg" width="96" alt="Ícone do Clima">

# Clima

**Previsão do tempo para o GNOME, com cara de app nativo.**
Clima agora, próximas 24 horas, 7 dias, várias cidades — e, no Brasil, avisos oficiais do INMET e comparação entre previsões.

![GTK4](https://img.shields.io/badge/GTK-4-4a86cf?logo=gnome&logoColor=white)
![libadwaita](https://img.shields.io/badge/libadwaita-1.6%2B-3584e4)
![Python](https://img.shields.io/badge/Python-3-3776ab?logo=python&logoColor=white)
![Licença](https://img.shields.io/badge/licen%C3%A7a-GPL--3.0-blue)
![Status](https://img.shields.io/badge/status-beta-orange)
![Sem chave de API](https://img.shields.io/badge/API-sem%20chave-success)

<img src="docs/screenshots/01-principal.png" width="760" alt="Clima mostrando Ametista do Sul com avisos do INMET, detalhes e gráfico das próximas 24 horas">

</div>

---

## ✨ Funcionalidades

| | Recurso | Detalhe |
|---|---|---|
| 🌤️ | **Clima agora** | Temperatura grande, sensação térmica, umidade, vento e chance de chuva, com o fundo mudando conforme o tempo (céu limpo, noite, nublado, chuva, tempestade, neve, neblina) |
| 📈 | **Próximas 24 horas** | Gráfico de temperatura com a chance de chuva em barras; passe o mouse numa hora para ver os detalhes |
| 🗓️ | **7 dias** | Máxima, mínima e chance de chuva de cada dia, com dica ao passar o mouse |
| 🏙️ | **Várias cidades** | Busca por nome; a barra lateral mostra o ícone e a temperatura atual de cada uma |
| 🇧🇷 | **Avisos do INMET** | Alertas oficiais que cobrem a cidade, com severidade, riscos e o que fazer |
| ⚖️ | **Comparar fontes** | Máxima e mínima lado a lado: Open-Meteo, INMET e CPTEC/INPE |
| 🔔 | **Notificações** | Aviso de chuva nas próximas horas e de aviso novo do INMET |
| ⚙️ | **Preferências** | °C/°F, km/h, mph ou m/s, antecedência do alerta, intervalo de atualização e fontes oficiais |
| 🎨 | **Visual do Gavetta** | Cards translúcidos, cantos arredondados e chips em pílula, como no [Gavetta](https://github.com/bcocheto/gavetta) e na [Cadência](https://github.com/bcocheto/cadencia) |
| 🌗 | **Cores do sistema** | Segue o tema claro/escuro e a cor de destaque do GNOME |

## 📸 Capturas

<table>
  <tr>
    <td align="center"><img src="docs/screenshots/03-aviso-inmet.png" width="380" alt="Aviso do INMET expandido"><br><sub>Aviso oficial do INMET, com riscos e orientações</sub></td>
    <td align="center"><img src="docs/screenshots/02-comparar-fontes.png" width="380" alt="Comparação entre Open-Meteo, INMET e CPTEC"><br><sub>Previsão de 7 dias e comparação entre fontes</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/screenshots/04-tema-claro.png" width="380" alt="Tema claro, chovendo em Lisboa"><br><sub>Tema claro, com fundo de chuva</sub></td>
    <td align="center"><img src="docs/screenshots/05-preferencias.png" width="380" alt="Janela de preferências"><br><sub>Preferências: unidades, alertas e fontes oficiais</sub></td>
  </tr>
</table>

## 📦 Instalação

> Requer **GTK 4.14+**, **libadwaita 1.6+** e **PyGObject** (`python3-gi`). Testado no GNOME 50.

```bash
git clone https://github.com/bcocheto/clima.git
cd clima
python3 -m clima        # rodar direto
make install            # opcional: atalho no menu, ícone e notificações
```

`make uninstall` remove o atalho e os ícones. As cidades e as preferências ficam em `~/.config/clima/`.

### Flatpak

O manifesto está em [`packaging/flatpak`](packaging/flatpak/io.github.bcocheto.Clima.yaml). Para compilar e instalar localmente (precisa do `flatpak-builder` e do runtime `org.gnome.Sdk//50`):

```bash
flatpak-builder --user --install --force-clean build-flatpak packaging/flatpak/io.github.bcocheto.Clima.yaml
flatpak run io.github.bcocheto.Clima
```

## 🌐 Fontes de dados

| Fonte | Uso |
|---|---|
| [Open-Meteo](https://open-meteo.com) | Previsão principal e busca de cidades (sem chave de API) |
| [INMET](https://apiprevmet3.inmet.gov.br) | Avisos ativos e previsão por município — só cidades no Brasil |
| [CPTEC/INPE](https://brasilapi.com.br) via BrasilAPI | Previsão de 4 dias com índice UV — só cidades no Brasil |
| [IBGE](https://servicodados.ibge.gov.br) | Código do município (usado pelo INMET), guardado em `~/.cache/clima/` |

As fontes oficiais valem para cidades no Brasil e podem ser desligadas nas Preferências. O app só consulta essas APIs; nada é enviado além do nome ou das coordenadas da cidade.

## 🧩 Como funciona

```
Open-Meteo ──► modelo ──► janela (tempo agora, 24 h, 7 dias, cidades)
INMET / CPTEC / IBGE ──► fontes ──► avisos e comparação (cidades no Brasil)
config + store ──► preferências e cidades salvas
```

- `api.py`: Open-Meteo (previsão e busca de cidades).
- `fontes.py`: INMET, CPTEC/INPE e IBGE (funções puras testáveis, sem rede nos testes).
- `modelo.py`: horas, dias e chuva próxima a partir da resposta da API.
- `janela.py` e `busca.py`: a interface; `grafico.py` desenha o gráfico com GtkSnapshot.
- `estilo.css`: o visual, com as cores do tema do sistema.
- `config.py`, `prefs.py` e `store.py`: preferências e cidades.

## 🛠️ Desenvolvimento

| Comando | O que faz |
|---|---|
| `python3 -m clima` | Roda o app direto do código-fonte |
| `make test` | Roda os testes (`unittest`) |
| `make install` | Instala o atalho, os ícones e o `.desktop` para o seu usuário |
| `make uninstall` | Remove o que o `make install` instalou |
| `meson setup build && meson install -C build` | Instalação padrão (usada pelo Flatpak) |

## 🗺️ Próximos passos

- [x] Clima atual, 24 horas e 7 dias
- [x] Várias cidades, preferências e alerta de chuva
- [x] Avisos e previsões oficiais do Brasil (INMET, CPTEC/INPE)
- [ ] Dados observados das estações do INMET (a API pública está sem resposta)
- [ ] Localização automática
- [x] Tela Sobre, metadados AppStream e manifesto Flatpak
- [ ] Publicar no Flathub
- [ ] Tradução (gettext)
- [ ] Mais órgãos oficiais, além do Brasil

## 📄 Licença

[GPL-3.0](LICENSE) © Breno Cocheto
