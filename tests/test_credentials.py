import os
import sys
import tempfile
import unittest

from drakoria_bot.credentials import Credentials


@unittest.skipUnless(sys.platform == "win32", "DPAPI so' no Windows")
class CredentialsTest(unittest.TestCase):
    def test_saves_encrypted_and_reads_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "credentials.json")
            creds = Credentials(path)
            creds.save("conta1", "senha-de-teste")
            self.assertNotIn("senha-de-teste", open(path, encoding="utf-8").read())   # nunca em texto puro
            self.assertEqual(creds.usernames(), ["conta1"])
            self.assertEqual(creds.get("CONTA1"), "senha-de-teste")
            creds.save("conta1", "outra-senha")
            self.assertEqual(creds.get("conta1"), "outra-senha")
            creds.remove("conta1")
            self.assertEqual(creds.usernames(), [])


if __name__ == "__main__":
    unittest.main()
