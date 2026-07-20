"""AI-CONTEXT: Background worker entrypoint.

Placeholder loop for the compose `worker` service (dev/CI parity). Real jobs
— geofence evaluation (F3), aggregation (F10/M2), dunning cadences (M3),
ML batch (M8) — register here as their foundations land. Kept alive so the
service is healthy in the topology from session 1.
"""

import signal
import sys
import time


def main() -> None:
    running = {"on": True}

    def stop(*_: object) -> None:
        running["on"] = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    sys.stdout.write("longhaul-worker: started (no jobs registered yet)\n")
    sys.stdout.flush()
    while running["on"]:
        time.sleep(1)
    sys.stdout.write("longhaul-worker: stopped\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
