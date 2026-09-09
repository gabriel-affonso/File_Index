"""Anfitrião Windows: mantém a aplicação local viva e responde ao atalho global."""
from __future__ import annotations
import ctypes
import ctypes.wintypes
import os
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_SPACE = 0x20
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
PM_REMOVE = 0x0001
HOTKEY_ID = 1

def main():
    if not hasattr(ctypes, 'windll'):
        raise SystemExit('windows_launcher só pode ser executado no Windows.')
    # Import tardio: caso uma dependência falhe, o utilizador recebe um diálogo
    # e um ficheiro de log, em vez de uma janela que desaparece imediatamente.
    from app.web_main import BUILD_ID, start_server, watcher
    server, url = start_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f'Local Knowledge Explorer [{BUILD_ID}]: {url}')
    webbrowser.open(url)
    user32 = ctypes.windll.user32
    if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, VK_SPACE):
        print('Não foi possível registar Ctrl+Shift+Espaço; a aplicação continua disponível no browser.')
    message = ctypes.wintypes.MSG()
    try:
        # GetMessageW bloqueia dentro de uma chamada nativa e pode atrasar o
        # KeyboardInterrupt. PeekMessageW devolve regularmente o controlo ao
        # Python, portanto Ctrl+C volta a encerrar o anfitrião e o servidor.
        running = True
        while running:
            while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_REMOVE):
                if message.message == WM_QUIT:
                    running = False
                    break
                if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                    webbrowser.open(url)
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
            time.sleep(0.05)
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)
        server.shutdown()
        watcher.stop()

def report_startup_error(error: Exception):
    log_dir = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'LocalKnowledgeExplorer' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / 'startup-error.log'
    log_file.write_text(traceback.format_exc(), encoding='utf-8')
    message = f'A aplicação não conseguiu iniciar.\n\nDetalhes: {error}\n\nLog: {log_file}'
    if hasattr(ctypes, 'windll'):
        ctypes.windll.user32.MessageBoxW(None, message, 'Local Knowledge Explorer', 0x10)
    else:
        print(message, file=sys.stderr)

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        report_startup_error(error)
        raise SystemExit(1)
