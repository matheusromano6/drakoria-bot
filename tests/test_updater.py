import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drakoria_bot import updater


def release(tag, assets=("DrakoriaBot-windows.zip",)):
    body = {"tag_name": tag, "assets": [{"name": n, "browser_download_url": f"https://x/{n}"} for n in assets]}

    def opener(request, timeout=0):
        return io.BytesIO(json.dumps(body).encode())

    return opener


class VersionTests(unittest.TestCase):
    def test_numeric_compare(self):
        self.assertGreater(updater.parse_version("v1.10.0"), updater.parse_version("1.9.9"))
        self.assertEqual(updater.parse_version("v1.0.0"), (1, 0, 0))
        self.assertEqual(updater.parse_version(""), ())

    def test_newer_release_found(self):
        info = updater.check_for_update(lambda m: None, current="1.0.0", opener=release("v1.1.0"))
        self.assertEqual(info, {"version": "1.1.0", "asset_url": "https://x/DrakoriaBot-windows.zip"})

    def test_same_or_older_means_up_to_date(self):
        self.assertIsNone(updater.check_for_update(lambda m: None, current="1.1.0", opener=release("v1.1.0")))
        self.assertIsNone(updater.check_for_update(lambda m: None, current="1.2.0", opener=release("v1.1.0")))

    def test_release_without_the_asset_is_ignored(self):
        self.assertIsNone(updater.check_for_update(lambda m: None, current="1.0.0", opener=release("v2.0.0", assets=("outro.zip",))))

    def test_network_error_never_raises(self):
        logs = []

        def boom(request, timeout=0):
            raise OSError("sem rede")

        self.assertIsNone(updater.check_for_update(logs.append, current="1.0.0", opener=boom))
        self.assertTrue(logs)


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make_zip(self, with_exe=True, exe_bytes=b"NOVO"):
        path = os.path.join(self.tmp, "release.zip")
        with zipfile.ZipFile(path, "w") as z:
            if with_exe:
                z.writestr("DrakoriaBot.exe", exe_bytes)
            z.writestr("LEIA-ME.md", "leia")
        return "file:///" + path.replace("\\", "/")

    def test_not_frozen_refuses(self):
        logs = []
        self.assertFalse(updater.apply_update("x", logs.append))
        self.assertIn("executavel", logs[0])

    def test_invalid_zip_is_rejected_before_touching_anything(self):
        bad = os.path.join(self.tmp, "bad.zip")
        open(bad, "wb").write(b"nao e zip")
        logs = []
        self.assertFalse(updater.apply_update("file:///" + bad.replace("\\", "/"), logs.append, current_exe=os.path.join(self.tmp, "a.exe")))

    def test_zip_without_exe_is_rejected(self):
        self.assertFalse(updater.apply_update(self.make_zip(with_exe=False), lambda m: None, current_exe=os.path.join(self.tmp, "a.exe")))

    def test_swap_script_waits_for_pid_and_keeps_backup(self):
        bat = updater.build_swap_script(1234, r"C:\app\DrakoriaBot.exe", r"C:\tmp\new.exe", r"C:\tmp\log.txt", "Tarefa_1234")
        self.assertIn('tasklist /FI "PID eq 1234"', bat)
        self.assertLess(bat.index("tasklist"), bat.index("move /Y"))
        self.assertIn('move /Y "C:\\app\\DrakoriaBot.exe" "C:\\app\\DrakoriaBot.exe.bak"', bat)
        self.assertIn('schtasks /delete /tn "Tarefa_1234"', bat)

    def test_real_swap_with_a_dummy_exe(self):
        """Roda o .bat de verdade (schtasks) com um 'exe' de mentira: confere troca, reabertura e limpeza."""
        app = os.path.join(self.tmp, "app")
        os.makedirs(app)
        current = os.path.join(app, "DrakoriaBot.exe")
        system32 = os.path.join(os.environ["WINDIR"], "System32")
        shutil.copy(os.path.join(system32, "hostname.exe"), current)          # "versao antiga" (inofensiva)
        before = open(current, "rb").read()
        new_bytes = open(os.path.join(system32, "whoami.exe"), "rb").read()   # "versao nova" (inofensiva)
        url = self.make_zip(exe_bytes=new_bytes)
        proc = subprocess.Popen(["ping", "-n", "4", "127.0.0.1"], stdout=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        logs = []
        ok = updater.apply_update(url, logs.append, current_exe=current, pid=proc.pid)
        self.assertTrue(ok, logs)
        proc.wait()
        log_file = next(l.split("em: ")[1].rstrip(")") for l in logs if "update_log" in l)
        end = time.time() + 30
        while time.time() < end and not (os.path.exists(log_file) and "concluido" in open(log_file, errors="ignore").read()):
            time.sleep(0.5)
        text = open(log_file, errors="ignore").read()
        self.assertIn("concluido", text, text)
        self.assertEqual(open(current, "rb").read(), new_bytes)                    # exe trocado
        self.assertNotEqual(open(current, "rb").read(), before)
        self.assertFalse(os.path.exists(current + ".bak"))                         # backup apagado


if __name__ == "__main__":
    unittest.main()
