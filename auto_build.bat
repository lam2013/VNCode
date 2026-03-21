@echo off
cd /d "%~dp0"
pyinstaller --onedir --noconfirm --icon="icon_VNCode.ico" --add-data "fill_module.py;." --add-data "list_module.py;." --add-data "icon_VNCode.ico;." --add-data "close_hover.svg;." --add-data "close.svg;." run.py