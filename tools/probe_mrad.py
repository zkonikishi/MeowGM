"""Run the same read-only Mrad handshake used by the desktop gateway."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services' / 'gateway'))
from mrad_transport import MAX_RESPONSE_BYTES, ProbeError, probe, validate_url, main

if __name__ == '__main__':
    raise SystemExit(main())
