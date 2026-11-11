from pathlib import Path
from typing import Callable, Optional

from app.config import watchdog_config
from app.logging_config import setup_logging
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

logger = setup_logging()

class VaultObserver:
    def __init__(
        self,
        on_modified_callback: Optional[Callable[[Path], None]] = None,
        on_created_callback: Optional[Callable[[Path], None]] = None,
        on_deleted_callback: Optional[Callable[[Path], None]] = None,
    ):
        config = watchdog_config()
        self.folder_path = Path(config.vault_path or config.vault_folder_path)
        self.observer = PollingObserver(timeout=config.poll_interval_seconds)

        self._custom_modified = on_modified_callback
        self._custom_created = on_created_callback
        self._custom_deleted = on_deleted_callback

        self.event_handler = FileSystemEventHandler()
        self.event_handler.on_modified = self._handle_modified
        self.event_handler.on_created = self._handle_created
        self.event_handler.on_deleted = self._handle_deleted
        self.event_handler.on_moved = self._handle_moved

    def _is_markdown_file(self, path: Path) -> bool:
        """Check if path is a valid non-hidden markdown file."""
        return path.suffix == ".md" and not path.name.startswith(".")

    def _handle_modified(self, event: FileSystemEvent):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if not self._is_markdown_file(path):
            return
        try:
            if self._custom_modified:
                self._custom_modified(path)
            else:
                self.on_modified(event)
        except Exception as e:
            logger.exception(f"Error handling modified event for {path}: {e}")

    def _handle_created(self, event: FileSystemEvent):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if not self._is_markdown_file(path):
            return
        try:
            if self._custom_created:
                self._custom_created(path)
            else:
                self.on_created(event)
        except Exception as e:
            logger.exception(f"Error handling created event for {path}: {e}")

    def _handle_deleted(self, event: FileSystemEvent):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if not self._is_markdown_file(path):
            return
        try:
            if self._custom_deleted:
                self._custom_deleted(path)
            else:
                self.on_deleted(event)
        except Exception as e:
            logger.exception(f"Error handling deleted event for {path}: {e}")

    def _handle_moved(self, event: FileSystemEvent):
        if event.is_directory:
            return
        old_path = Path(event.src_path)
        new_path = Path(getattr(event, "dest_path", ""))
        try:
            if self._is_markdown_file(old_path) and self._custom_deleted:
                self._custom_deleted(old_path)
            if self._is_markdown_file(new_path) and new_path.exists() and self._custom_created:
                self._custom_created(new_path)
        except Exception as e:
            logger.exception(f"Error handling moved event from {old_path} to {new_path}: {e}")

    def start(self):
        """Start the observer to watch for file changes."""
        if not self.folder_path.exists():
            raise ValueError(f"Vault folder path does not exist: {self.folder_path}")
        
        self.observer.schedule(event_handler=self.event_handler, path=str(self.folder_path), recursive=True)
        self.observer.start()
        logger.info(f"👀 Observer started! Watching full path: {self.folder_path}")

    def stop(self):
        """Stop the observer."""
        self.observer.stop()
        self.observer.join()
        logger.info("🛑 Observer stopped.")

    def on_modified(self, event: FileSystemEvent):
        logger.info(f"File has been modified on {event.src_path} but not updated in the metadata")

    def on_created(self, event: FileSystemEvent):
        logger.info(f"File created has been created: {event.src_path} but not updated in the metadata")

    def on_deleted(self, event: FileSystemEvent):
        logger.info(f"File deleted has been deleted: {event.src_path} but not updated in the metadata")

