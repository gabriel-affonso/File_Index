"""Anfitrião Windows: mantém a aplicação local viva e responde ao atalho global."""
from __future__ import annotations
import ctypes
import ctypes.wintypes
import threading
import webbrowser
from app.web_main import start_server

MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_SPACE = 0x20
WM_HOTKEY = 0x0312
HOTKEY_ID = 1

def main():
    if not hasattr(ctypes, 'windll'):
        raise SystemExit('windows_launcher só pode ser executado no Windows.')
    server, url = start_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    webbrowser.open(url)
    user32 = ctypes.windll.user32
    if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, VK_SPACE):
        print('Não foi possível registar Ctrl+Shift+Espaço; a aplicação continua disponível no browser.')
    message = ctypes.wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) != 0:
            if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                webbrowser.open(url)
            user32.TranslateMessage(ctypes.byref(message));user32.DispatchMessageW(ctypes.byref(message))
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)
        server.shutdown()

if __name__ == '__main__': main()
