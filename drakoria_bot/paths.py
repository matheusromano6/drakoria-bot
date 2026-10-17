"""Onde ficam os arquivos do bot. Empacotado (PyInstaller --onefile) o codigo roda numa pasta
temporaria; config.json, memory.json e logs precisam ficar AO LADO do .exe pra nao se perderem."""
import os
import sys


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir():
    """Arquivos embutidos no executavel (icone)."""
    return getattr(sys, "_MEIPASS", None) or app_dir()
