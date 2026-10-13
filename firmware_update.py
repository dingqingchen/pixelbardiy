"""Console entry for the separate, operator-controlled MCU updater."""
import sys
from halo.firmware_update import main

if __name__ == '__main__':
    try:
        sys.exit(main() or 0)
    except Exception as exc:
        print('STOPPED: '+str(exc), file=sys.stderr)
        sys.exit(1)
