"""Bounded, RAM-only local-rain test after a confirmed reboot."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'firmware-fullscreen'))
import smoke_fullscreen

if __name__ == '__main__':
    smoke_fullscreen.main('matrix-live', 'ccb55a58beb825e730175969d9388bdc94ef55d0ad8534947a3ec8c728473884', rain=True)
