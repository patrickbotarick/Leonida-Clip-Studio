"""Serviço de origem única. Ctrl+C, fechar console ou encerrar.ps1 encerram o fluxo."""
import json
import argparse
import os
import socket
import sys
import threading
import uuid
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import uvicorn
    from backend.config import DATA

    parser = argparse.ArgumentParser(description='Leonida Clip Studio — servidor local')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('Porta deve estar entre 0 e 65535.')
    if not (ROOT / 'frontend/dist/index.html').is_file():
        print('Interface não compilada. Execute scripts/configurar.ps1 primeiro.')
        return 1
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == 'nt':
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(('127.0.0.1', args.port))
        sock.listen(128)
    except OSError:
        print(f'Porta {args.port} ocupada. Feche a outra instância ou execute scripts/encerrar.ps1 se ela pertence a este projeto.')
        sock.close()
        return 1
    token = uuid.uuid4().hex
    port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    stop_file = DATA / f'stop-{token}'
    state_file = DATA / 'run.json'
    # Um diretório de dados possui apenas uma instância, inclusive em portas diferentes.
    import msvcrt
    lock_file = (DATA / 'instance.lock').open('a+b')
    if lock_file.tell() == 0:
        lock_file.write(b'0'); lock_file.flush()
    lock_file.seek(0)
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print('Este diretório de dados já está aberto em outra instância.')
        lock_file.close(); sock.close()
        return 1
    state_file.write_text(json.dumps({'pid': os.getpid(), 'token': token, 'url': url}), encoding='utf-8')
    config = uvicorn.Config('backend.main:app', host='127.0.0.1', port=port, access_log=False, log_level='info',
                            loop='asyncio:SelectorEventLoop', timeout_keep_alive=2, timeout_graceful_shutdown=5)
    server = uvicorn.Server(config)
    finished = threading.Event()

    def monitor():
        opened = False
        while not finished.wait(0.3):
            if stop_file.exists():
                server.should_exit = True
                return
            if server.started and not opened:
                opened = True
                print(f'\nLeonida Clip Studio: {url}\nMantenha esta janela aberta. Ctrl+C encerra os serviços.\n')
                if not args.no_browser:
                    webbrowser.open(url)

    threading.Thread(target=monitor, daemon=True).start()
    try:
        server.run(sockets=[sock])
    finally:
        finished.set()
        sock.close()
        stop_file.unlink(missing_ok=True)
        if state_file.exists() and json.loads(state_file.read_text(encoding='utf-8')).get('token') == token:
            state_file.unlink()
        lock_file.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
