import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drakoria_bot import launcher


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.scripts = []
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(launcher.time, "sleep", lambda s: None).start()

    def fake_ps(self, activate_result="OK 123"):
        def run(script, timeout=60):
            self.scripts.append(script)
            return activate_result if "ActivateApplication" in script else ""
        return mock.patch.object(launcher, "run_powershell", run)

    def test_port_already_open_does_nothing(self):
        with self.fake_ps():
            self.assertTrue(launcher.launch("http://127.0.0.1:9224", lambda: True, self.logs.append))
        self.assertEqual(self.scripts, [])

    def test_opens_with_the_port_from_the_url_and_waits_for_it(self):
        calls = {"n": 0}

        def port_open():
            calls["n"] += 1
            return calls["n"] > 3          # a porta so' responde depois de uns instantes

        with self.fake_ps(), mock.patch.object(launcher, "is_running", lambda: False):
            self.assertTrue(launcher.launch("http://127.0.0.1:9333", port_open, self.logs.append))
        self.assertTrue(any("--remote-debugging-port=9333" in s for s in self.scripts))

    def test_running_without_port_asks_to_close_and_waits_for_the_user(self):
        states = iter([True, True, True, False, False, False])      # o usuario confirma 'Sair' depois de um tempo
        with self.fake_ps(), mock.patch.object(launcher, "is_running", lambda: next(states, False)), \
                mock.patch.object(launcher, "request_close") as close:
            ok = launcher.launch("http://127.0.0.1:9224", lambda: bool(self.scripts and any("Activate" in s for s in self.scripts)), self.logs.append)
        self.assertTrue(ok)
        close.assert_called_once()
        self.assertTrue(any("SEM a depuração" in m for m in self.logs))

    def test_never_kills_processes(self):
        source = open(launcher.__file__, encoding="utf-8").read()
        self.assertNotIn("Stop-Process", source)
        self.assertNotIn("taskkill", source.lower())

    def test_user_does_not_close_in_time(self):
        with self.fake_ps(), mock.patch.object(launcher, "is_running", lambda: True), mock.patch.object(launcher, "request_close"), \
                mock.patch.object(launcher, "CLOSE_WAIT_SECONDS", 0):
            self.assertFalse(launcher.launch("http://127.0.0.1:9224", lambda: False, self.logs.append))
        self.assertFalse(any("ActivateApplication" in s for s in self.scripts))     # nao tentou abrir por cima
        self.assertTrue(any("não fechou a tempo" in m for m in self.logs))

    def test_not_installed(self):
        with self.fake_ps("ERR IdleDeck nao esta instalado (pacote da Microsoft Store nao encontrado)"), \
                mock.patch.object(launcher, "is_running", lambda: False):
            self.assertFalse(launcher.launch("http://127.0.0.1:9224", lambda: False, self.logs.append))
        self.assertTrue(any("Não consegui abrir" in m for m in self.logs))

    def test_stop_event_cancels_the_wait(self):
        stop = threading.Event()
        stop.set()
        with self.fake_ps(), mock.patch.object(launcher, "is_running", lambda: True), mock.patch.object(launcher, "request_close"):
            self.assertFalse(launcher.launch("http://127.0.0.1:9224", lambda: False, self.logs.append, stop))

    def test_port_from_url(self):
        self.assertEqual(launcher.port_of("http://127.0.0.1:9230"), 9230)
        self.assertEqual(launcher.port_of("http://localhost"), 9224)


if __name__ == "__main__":
    unittest.main()
