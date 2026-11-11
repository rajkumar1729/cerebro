"""Run Cerebro's API and Telegram bot in one container."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request


def _api_is_healthy() -> bool:
    port = os.getenv("API_PORT", "8000")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2):
            return True
    except (OSError, urllib.error.URLError):
        return False


def main() -> None:
    api = subprocess.Popen([sys.executable, "-m", "app"])
    bot: subprocess.Popen | None = None
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        for process in (bot, api):
            if process is not None and process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        while not stopping:
            api_status = api.poll()
            if api_status is not None:
                raise SystemExit(api_status or 1)
            if _api_is_healthy():
                break
            time.sleep(1)

        if not stopping:
            bot = subprocess.Popen([sys.executable, "-m", "app", "telegram"])

        while not stopping:
            for process in (api, bot):
                if process is not None and process.poll() is not None:
                    raise SystemExit(process.returncode or 1)
            time.sleep(1)
    finally:
        stop(signal.SIGTERM, None)
        for process in (bot, api):
            if process is not None:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
