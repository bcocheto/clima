# Instala o Clima para o usuário atual (atalho no menu, ícone e notificações).
APP_ID  := io.github.bcocheto.Clima
DATA    := $(HOME)/.local/share

.PHONY: install uninstall test

install:
	install -Dm644 data/icons/hicolor/scalable/apps/$(APP_ID).svg $(DATA)/icons/hicolor/scalable/apps/$(APP_ID).svg
	install -Dm644 data/icons/hicolor/symbolic/apps/$(APP_ID)-symbolic.svg $(DATA)/icons/hicolor/symbolic/apps/$(APP_ID)-symbolic.svg
	mkdir -p $(DATA)/applications
	sed -e "s|^Exec=.*|Exec=python3 -m clima|" -e "/^Exec=/a Path=$(CURDIR)" data/$(APP_ID).desktop > $(DATA)/applications/$(APP_ID).desktop
	-gtk-update-icon-cache -q -t $(DATA)/icons/hicolor
	-update-desktop-database -q $(DATA)/applications

uninstall:
	rm -f $(DATA)/icons/hicolor/scalable/apps/$(APP_ID).svg $(DATA)/icons/hicolor/symbolic/apps/$(APP_ID)-symbolic.svg $(DATA)/applications/$(APP_ID).desktop
	-gtk-update-icon-cache -q -t $(DATA)/icons/hicolor

test:
	python3 -m unittest discover -s tests
