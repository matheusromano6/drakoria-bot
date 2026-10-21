import unittest
from unittest import mock

from drakoria_bot import browsers as B

NETSTAT = """
  Proto  Local Address          Foreign Address        State           PID
  TCP    127.0.0.1:9223         0.0.0.0:0              LISTENING       4242
  TCP    0.0.0.0:9230           0.0.0.0:0              LISTENING       777
  TCP    127.0.0.1:9223         127.0.0.1:51000        ESTABLISHED     4242
  TCP    127.0.0.1:8080         0.0.0.0:0              LISTENING       12
"""


class BrowsersTest(unittest.TestCase):
    def test_listening_ports_only_debug_range(self):
        with mock.patch("subprocess.run", return_value=mock.Mock(stdout=NETSTAT)):
            self.assertEqual(B._listening_ports(), {9223: 4242, 9230: 777})

    def test_free_port_skips_used(self):
        with mock.patch.object(B, "_listening_ports", return_value={9231: 1, 9232: 2}):
            self.assertEqual(B.free_port(), 9233)

    def test_profile_dir_is_per_browser(self):
        self.assertTrue(B.profile_dir("Opera GX").endswith("navegador\opera-gx") or
                        B.profile_dir("Opera GX").endswith("navegador/opera-gx"))


if __name__ == "__main__":
    unittest.main()
