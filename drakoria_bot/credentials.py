"""Logins salvos pra relogar sozinho (server save / queda). As senhas ficam CRIPTOGRAFADAS pelo Windows (DPAPI):
so' o mesmo usuario do Windows, neste PC, consegue abrir. Arquivo: credentials.json ao lado do .exe. Nunca vai pro log."""
import base64
import ctypes
import ctypes.wintypes
import json
import os
import sys


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def protect(text):
    if sys.platform != "win32":
        raise RuntimeError("logins salvos so' no Windows")
    data, _keep = _blob(text.encode("utf-8"))
    out = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(data), "drakoriabot", None, None, None, 0, ctypes.byref(out)):
        raise OSError("CryptProtectData falhou")
    try:
        return base64.b64encode(ctypes.string_at(out.pbData, out.cbData)).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def unprotect(token):
    raw = base64.b64decode(token)
    data, _keep = _blob(raw)
    out = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(data), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("CryptUnprotectData falhou (outro usuario/PC?)")
    try:
        return ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


class Credentials:
    def __init__(self, path):
        self.path = path

    def _load(self):
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, encoding="utf-8") as file:
                return list(json.load(file).get("logins") or [])
        except (OSError, ValueError):
            return []

    def usernames(self):
        return [item["username"] for item in self._load()]

    def get(self, username):
        for item in self._load():
            if item["username"].casefold() == username.casefold():
                return unprotect(item["password"])
        return None

    def save(self, username, password):
        items = [i for i in self._load() if i["username"].casefold() != username.casefold()]
        items.append({"username": username, "password": protect(password)})
        self._write(items)

    def remove(self, username):
        self._write([i for i in self._load() if i["username"].casefold() != username.casefold()])

    def _write(self, items):
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump({"logins": items}, file, ensure_ascii=False, indent=2)
