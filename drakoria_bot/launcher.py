"""Abre o IdleDeck (app da Microsoft Store) COM a depuracao remota ligada.

CONFIRMADO ao vivo (bot do Baiak): o IdleDeck so' aceita '--remote-debugging-port' se for aberto pela
ATIVACAO DO PACOTE (abrir o .exe direto perde a pasta de dados). E NUNCA matar os processos dele a forca:
deixa um subprocesso 'fantasma' que impede de reabrir (0x8000001A) ate reiniciar o PC. Por isso, se ele ja
estiver aberto SEM a porta, o bot so' pede pra fechar (CloseMainWindow) e espera VOCE confirmar 'Sair'.
"""
import base64
import os
import platform
import subprocess
import time
import urllib.parse

CLOSE_WAIT_SECONDS = 120        # tempo pro usuario confirmar 'Sair' no dialogo do app
LAUNCH_TIMEOUT_SECONDS = 40

# so' os processos da versao da Store (a copia do IdleDeck do perfil VPN do bot do Baiak nunca e' tocada)
PACKAGE_LIKE = "*" + os.sep + "WindowsApps" + os.sep + "*"

_PS_COMMON = """
$ErrorActionPreference = 'Stop'
function Get-IdleDeckProcs { param($like) @(Get-Process IdleDeck -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited -and ($like -eq $null -or $_.Path -like $like) }) }
"""

_PS_ACTIVATE = """
Add-Type @"
using System;
using System.Runtime.InteropServices;
[ComImport, Guid("2e941141-7f97-4756-ba1d-9decde894a3d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IApplicationActivationManager {
    int ActivateApplication([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId, [MarshalAs(UnmanagedType.LPWStr)] string arguments, int options, out uint processId);
    int ActivateForFile([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId, IntPtr itemArray, [MarshalAs(UnmanagedType.LPWStr)] string verb, out uint processId);
    int ActivateForProtocol([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId, IntPtr itemArray, out uint processId);
}
[ComImport, Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C"), ClassInterface(ClassInterfaceType.None)]
public class ApplicationActivationManager : IApplicationActivationManager {
    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.InternalCall, MethodCodeType = System.Runtime.CompilerServices.MethodCodeType.Runtime)]
    public extern int ActivateApplication([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId, [MarshalAs(UnmanagedType.LPWStr)] string arguments, int options, out uint processId);
    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.InternalCall, MethodCodeType = System.Runtime.CompilerServices.MethodCodeType.Runtime)]
    public extern int ActivateForFile([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId, IntPtr itemArray, [MarshalAs(UnmanagedType.LPWStr)] string verb, out uint processId);
    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.InternalCall, MethodCodeType = System.Runtime.CompilerServices.MethodCodeType.Runtime)]
    public extern int ActivateForProtocol([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId, IntPtr itemArray, out uint processId);
}
"@
$pkg = Get-AppxPackage | Where-Object { $_.Name -like '*IdleDeck*' } | Select-Object -First 1
if (-not $pkg) { Write-Output 'ERR IdleDeck nao esta instalado (pacote da Microsoft Store nao encontrado)'; exit 0 }
$appId = (Get-AppxPackageManifest $pkg).Package.Applications.Application.Id
$mgr = [IApplicationActivationManager](New-Object ApplicationActivationManager)
[uint32]$procId = 0
try {
    $null = $mgr.ActivateApplication("$($pkg.PackageFamilyName)!$appId", "--remote-debugging-port=__PORT__", 0, [ref]$procId)
    Write-Output "OK $procId"
} catch {
    Write-Output ("ERR " + $_.Exception.Message)
}
"""


def port_of(cdp_url):
    return urllib.parse.urlparse(cdp_url).port or 9224


def run_powershell(script, timeout=60):
    """Roda um script PowerShell (codificado, sem problema de aspas) sem abrir janela de console."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        capture_output=True, text=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return (result.stdout or "").strip()


def _procs(path_like=PACKAGE_LIKE):
    return "Get-IdleDeckProcs -like '" + path_like.replace("'", "''") + "'"


def is_running():
    """Ha processo do IdleDeck (da Store) vivo, com ou sem a porta de depuracao."""
    out = run_powershell(_PS_COMMON + "(" + _procs() + ").Count", timeout=30)
    return out.strip().isdigit() and int(out.strip()) > 0


def request_close():
    """Igual clicar no X: o app pode abrir um dialogo nativo perguntando se quer sair (quem confirma e' voce)."""
    run_powershell(_PS_COMMON + _procs() + " | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object { $null = $_.CloseMainWindow() }", timeout=30)


def close_and_wait(log, stop=None):
    """Se o IdleDeck esta aberto SEM a porta: pede pra fechar e espera o usuario confirmar. True se nao ha mais nenhum."""
    if not is_running():
        return True
    log("O IdleDeck esta aberto SEM a depuração remota - pedindo pra fechar. Se aparecer uma janela perguntando, "
        "escolha SAIR (não só minimizar); o bot reabre sozinho em seguida (suas contas ficam salvas).")
    request_close()
    deadline = time.monotonic() + CLOSE_WAIT_SECONDS
    last_reminder = time.monotonic()
    while time.monotonic() < deadline and is_running():
        if stop is not None and stop.is_set():
            return False
        time.sleep(2)
        if time.monotonic() - last_reminder >= 30:
            last_reminder = time.monotonic()
            log("Ainda aguardando o IdleDeck fechar - feche pela janela dele (Sair).")
    if is_running():
        log("O IdleDeck não fechou a tempo. Feche pela janela (Sair) e clique em Iniciar de novo.")
        return False
    time.sleep(2)       # deixa o Windows liberar o pacote antes de reabrir
    return True


def launch(cdp_url, port_open, log, stop=None):
    """Deixa o IdleDeck aberto com a porta de depuracao. 'port_open' e' a funcao que testa a porta.
    Retorna True se a porta responde no final."""
    if port_open():
        return True
    if platform.system() != "Windows":
        log("Abrir o IdleDeck sozinho so funciona no Windows.")
        return False
    port = port_of(cdp_url)
    try:
        if not close_and_wait(log, stop):
            return False
        log("Abrindo o IdleDeck com a depuração remota...")
        script = _PS_ACTIVATE.replace("__PORT__", str(port))
        deadline = time.monotonic() + LAUNCH_TIMEOUT_SECONDS
        out, last_error = "", ""
        while time.monotonic() < deadline:
            if stop is not None and stop.is_set():
                return False
            out = run_powershell(script, timeout=60)
            if out.startswith("OK"):
                break
            last_error = out
            if "nao esta instalado" in out:
                break
            time.sleep(3)       # logo apos fechar o Windows ainda pode recusar ("aplicativo sendo encerrado")
        if not out.startswith("OK"):
            log(f"Não consegui abrir o IdleDeck: {last_error or out}")
            return False
        while time.monotonic() < deadline:
            if port_open():
                log("IdleDeck pronto.")
                return True
            time.sleep(0.5)
        log("O IdleDeck abriu mas a porta de depuração não respondeu.")
        return False
    except Exception as error:
        log(f"Erro ao abrir o IdleDeck: {error}")
        return False
