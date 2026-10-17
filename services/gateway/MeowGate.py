"""MeowGate entry point; admission protocol implementation stays separately testable."""
import argparse
import runpy
from pathlib import Path

if __name__ == '__main__':
    parser=argparse.ArgumentParser(prog='MeowGate',description='Loopback admission gateway. Configure the framework/provider and game adapter before starting.')
    parser.add_argument('--check',action='store_true',help='validate required deployment environment without starting or mutating data')
    args=parser.parse_args()
    if args.check:
        import os
        import sys
        required=['OO_PLATFORM_URL','OO_PLATFORM_GATEWAY_KEY','OO_GAME_KEY']
        missing=[name for name in required if not os.environ.get(name)]
        if missing:
            print('Missing required deployment configuration: '+', '.join(missing));sys.exit(2)
        from admission import PlatformConsumer
        try:PlatformConsumer(os.environ['OO_PLATFORM_URL'],os.environ['OO_PLATFORM_GATEWAY_KEY'],os.environ.get('OO_PLATFORM_CA_FILE'))
        except Exception:
            print('Invalid provider URL, TLS configuration or credentials format');sys.exit(2)
        print('Configuration format valid; service health and game integration not yet verified')
    else:
        runpy.run_path(str(Path(__file__).with_name('admission.py')),run_name='__main__')
