"""Allow running as: python -m app"""

import logging
import sys

# Initialize logging early
from .logging_config import setup_logging

# Setup logging for CLI/watcher modes
setup_logging()

if len(sys.argv) > 1 and sys.argv[1] == "telegram":
    # Telegram bot mode
    logger = logging.getLogger("cerebro")
    logger.info("Launching Telegram bot mode")
    sys.argv.pop(1)
    from app.client.telegram.telegram_bot_client import main
elif len(sys.argv) > 1 and sys.argv[1] == "watch":
    logger = logging.getLogger("cerebro")
    logger.info("Launching watcher mode")
    sys.argv.pop(1)
    import time
    from app.service.obsidian_service import ObsidianService
    from app.client.watcher.observer import VaultObserver

    def main():
        service = ObsidianService()
        observer = VaultObserver(
            on_created_callback=service.handle_note_created,
            on_modified_callback=service.handle_note_modified,
            on_deleted_callback=service.handle_note_deleted,
        )
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
else:
    # Default: API mode (used by Docker container)
    logger = logging.getLogger("cerebro")
    logger.info("Launching API mode")
    from .main import main

main()
