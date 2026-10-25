"""Run the current MeowGM source UI on an ephemeral loopback port, without Rust/Go builds."""
import argparse
import os
from pathlib import Path
import secrets
import sys
import webbrowser

FROZEN = getattr(sys, 'frozen', False)
ROOT = Path(sys._MEIPASS) if FROZEN else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'gateway'))
from mrad_console_host import MradReadOnlyHandler
from server import Gateway, Store


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    default_data = Path(sys.executable).resolve().parent / 'data' if FROZEN else ROOT / '.runtime' / 'mrad-console'
    parser.add_argument('--data', type=Path, default=default_data)
    parser.add_argument('--port', type=int, default=0)
    browser = parser.add_mutually_exclusive_group()
    browser.add_argument('--open', dest='open_browser', action='store_true', help='open the local management window in your browser')
    browser.add_argument('--no-open', dest='open_browser', action='store_false', help='do not launch a browser automatically')
    parser.set_defaults(open_browser=FROZEN)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('--port must be 0..65535')
    os.environ.setdefault('MEOW_MANAGER_PROFILE', '115us')
    args.data.mkdir(parents=True, exist_ok=True)
    server = Gateway(('127.0.0.1', args.port), Store(args.data / 'gateway.sqlite3'))
    server.RequestHandlerClass = MradReadOnlyHandler
    server.mrad_only = True
    server.local_mode = True
    server.setup_nonce = ''
    server.desktop_nonce = secrets.token_urlsafe(32)
    server.operations.actor = '本机管理'
    url = 'http://' + server.authority + '/#setup=' + server.desktop_nonce
    print('MeowGM source console (local window URL; do not share): ' + url, flush=True)
    print('Open "Mrad 只读管理" and connect explicitly. Ctrl+C stops only this console.', flush=True)
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
