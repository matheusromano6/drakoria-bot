"""Atualizacao automatica: consulta a release mais recente no GitHub (API publica, sem token), baixa o
DrakoriaBot-windows.zip e troca o proprio .exe. So' faz sentido empacotado (.exe) e so' no Windows."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from . import VERSION

UPDATE_REPO = "matheusromano6/drakoria-bot"
UPDATE_API_URL = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
ASSET_NAME = "DrakoriaBot-windows.zip"     # nome FIXO em toda release


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def parse_version(text):
    """'1.10.2' ou 'v1.10.2' -> (1, 10, 2): compara numericamente ('1.9.0' < '1.10.0')."""
    parts = []
    for piece in (text or "").strip().lstrip("vV").split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            break
    return tuple(parts)


def check_for_update(log=print, current=VERSION, opener=urllib.request.urlopen):
    """Retorna {'version', 'asset_url'} se ha versao MAIOR publicada com o zip do Windows; None se ja esta na
    ultima, se nao ha release/asset ou se a rede falhou (nunca trava o bot: so' avisa no log)."""
    try:
        request = urllib.request.Request(
            UPDATE_API_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "DrakoriaBot"})
        with opener(request, timeout=8) as response:
            data = json.load(response)
    except Exception as error:
        log(f"Nao consegui checar atualizacoes: {error}")
        return None
    tag = data.get("tag_name") or ""
    latest = parse_version(tag)
    if not latest or latest <= parse_version(current):
        return None
    for asset in data.get("assets") or []:
        if asset.get("name") == ASSET_NAME and asset.get("browser_download_url"):
            return {"version": tag.lstrip("vV"), "asset_url": asset["browser_download_url"]}
    return None


def download_zip(asset_url, log, progress=None):
    """Baixa pra uma pasta temporaria e confere que e' um zip valido antes de mexer em qualquer coisa."""
    tmp_dir = tempfile.mkdtemp(prefix="drakoriabot_update_")
    zip_path = os.path.join(tmp_dir, "update.zip")

    def report(blocks, block_size, total_size):
        if progress and total_size > 0:
            progress(min(1.0, blocks * block_size / total_size))

    try:
        urllib.request.urlretrieve(asset_url, zip_path, report)
    except Exception as error:
        log(f"Erro ao baixar a atualizacao: {error}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None
    if not zipfile.is_zipfile(zip_path):
        log("O arquivo baixado nao e' um zip valido - atualizacao cancelada.")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None
    return zip_path


def build_swap_script(pid, current_exe, new_exe, update_log, task_name):
    """.bat que espera ESTE processo fechar (nao da pra sobrescrever um .exe em uso), guarda o antigo como
    .bak, coloca o novo, reabre e apaga o .bak e a propria tarefa agendada. Registra tudo em update_log."""
    return (
        "@echo off\n"
        f'echo %date% %time% iniciando, esperando PID {pid} fechar >> "{update_log}"\n'
        ":waitloop\n"
        f'tasklist /FI "PID eq {pid}" 2>NUL | find "{pid}" >NUL\n'
        "if not errorlevel 1 (\n"
        "    timeout /t 1 /nobreak >NUL\n"
        "    goto waitloop\n"
        ")\n"
        f'echo %date% %time% PID fechou, trocando exe >> "{update_log}"\n'
        f'move /Y "{current_exe}" "{current_exe}.bak" >> "{update_log}" 2>&1\n'
        f'move /Y "{new_exe}" "{current_exe}" >> "{update_log}" 2>&1\n'
        f'echo %date% %time% reabrindo o bot >> "{update_log}"\n'
        f'start "" "{current_exe}"\n'
        f'del "{current_exe}.bak"\n'
        f'schtasks /delete /tn "{task_name}" /f >NUL 2>&1\n'
        f'echo %date% %time% concluido >> "{update_log}"\n'
    )


def apply_update(asset_url, log, progress=None, current_exe=None, pid=None):
    """Baixa e agenda a troca. Quem chama precisa FECHAR o bot logo em seguida (libera o .exe pro .bat).
    O .bat roda por uma tarefa agendada de uso unico (schtasks): confirmado no bot do Baiak que um .bat
    'destacado' do processo nao e' confiavel (tasklist/find sem console). Retorna True se agendou."""
    if not is_frozen() and current_exe is None:
        log("A atualizacao automatica so funciona no executavel (DrakoriaBot.exe).")
        return False
    zip_path = download_zip(asset_url, log, progress)
    if zip_path is None:
        return False
    tmp_dir = os.path.dirname(zip_path)
    extract_dir = os.path.join(tmp_dir, "extracted")
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)
    new_exe = next((os.path.join(extract_dir, n) for n in os.listdir(extract_dir) if n.lower().endswith(".exe")), None)
    if new_exe is None:
        log("Nao achei o .exe dentro do zip baixado - atualizacao cancelada.")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return False

    current_exe = current_exe or sys.executable
    pid = pid or os.getpid()
    update_log = os.path.join(tmp_dir, "update_log.txt")
    task_name = f"DrakoriaBotUpdate_{pid}"
    bat_path = os.path.join(tmp_dir, "apply_update.bat")
    with open(bat_path, "w", encoding="utf-8") as file:
        file.write(build_swap_script(pid, current_exe, new_exe, update_log, task_name))
    try:
        subprocess.run(["schtasks", "/create", "/tn", task_name, "/tr", bat_path, "/sc", "once", "/st", "00:00",
                        "/sd", "01/01/2050", "/f"], creationflags=subprocess.CREATE_NO_WINDOW, check=True, capture_output=True)
        subprocess.run(["schtasks", "/run", "/tn", task_name],
                       creationflags=subprocess.CREATE_NO_WINDOW, check=True, capture_output=True)
    except (subprocess.CalledProcessError, OSError) as error:
        log(f"Erro ao agendar a troca: {error}")
        return False
    log("Atualizacao baixada - o bot vai fechar e reabrir sozinho na versao nova.")
    log(f"(se nao reabrir sozinho, o log da troca fica em: {update_log})")
    return True
