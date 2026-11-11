# Directory File Change Detection — Research & Implementation Guide

Detect when files are created, modified, or deleted in a target directory (including all subdirectories) in real time.

---

## Approach Comparison

| Criteria | `watchdog` | `watchfiles` | Manual Polling (`pathlib.stat`) |
| :--- | :--- | :--- | :--- |
| **Mechanism** | OS-native events (FSEvents / inotify / ReadDirectoryChangesW) | Rust `notify` crate via Python bindings | Periodic `stat()` calls on every file |
| **Latency** | Near-instant | Near-instant | Limited by poll interval |
| **CPU overhead** | Low | Very low | High for large trees |
| **Async support** | No (threaded) | Yes (`asyncio` native) | Manual |
| **Maturity** | Battle-tested, large ecosystem | Modern successor to `watchgod` | DIY |
| **Install** | `pip install watchdog` | `pip install watchfiles` | Built-in (no deps) |

**Recommendation:** Use **`watchdog`** for broad compatibility and maturity, or **`watchfiles`** if you want async and better performance. Avoid polling for real-time use cases.

---

## Option A — `watchdog` (Recommended for Most Cases)

### Install

```bash
pip install watchdog
```

### Basic Recursive Watcher

```python
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class ChangeHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            print(f"[CREATED]  {event.src_path}")

    def on_modified(self, event):
        if not event.is_directory:
            print(f"[MODIFIED] {event.src_path}")

    def on_deleted(self, event):
        if not event.is_directory:
            print(f"[DELETED]  {event.src_path}")

    def on_moved(self, event):
        print(f"[MOVED]    {event.src_path} → {event.dest_path}")


if __name__ == "__main__":
    path = "/path/to/your/directory"

    observer = Observer()
    observer.schedule(ChangeHandler(), path, recursive=True)  # ← recursive=True is key
    observer.start()

    print(f"Watching {path} (recursive)...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```

> **`recursive=True`** is the critical flag — it registers watches on all subdirectories, including newly created ones.

### Pattern Filtering

Only react to specific file types (e.g. `.md`, `.py`):

```python
from watchdog.events import PatternMatchingEventHandler


class FilteredHandler(PatternMatchingEventHandler):
    def __init__(self):
        super().__init__(
            patterns=["*.md", "*.py", "*.json"],   # watch only these
            ignore_patterns=["*.tmp", "*.swp"],     # ignore editor temp files
            ignore_directories=True,
        )

    def on_modified(self, event):
        print(f"[MODIFIED] {event.src_path}")

    def on_created(self, event):
        print(f"[CREATED]  {event.src_path}")

    def on_deleted(self, event):
        print(f"[DELETED]  {event.src_path}")
```

### Debounce + Hash Verification

Editors often trigger multiple `modified` events for a single save. Use debouncing and content hashing to only react to _real_ changes:

```python
import time
import hashlib
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


def file_hash(path: str) -> str | None:
    """Return SHA-256 of file content, or None if unreadable."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (FileNotFoundError, PermissionError, OSError):
        return None


class DebouncedHandler(PatternMatchingEventHandler):
    def __init__(self, patterns: list[str], debounce_seconds: float = 0.5):
        super().__init__(patterns=patterns, ignore_directories=True)
        self.debounce_seconds = debounce_seconds
        self._last_event: dict[str, float] = {}     # path → timestamp
        self._known_hashes: dict[str, str] = {}      # path → sha256

    def on_modified(self, event):
        now = time.time()
        path = event.src_path

        # Debounce: skip if we just processed this file
        last = self._last_event.get(path, 0)
        if (now - last) < self.debounce_seconds:
            return

        # Hash check: skip if content hasn't actually changed
        new_hash = file_hash(path)
        if new_hash is None:
            return
        if self._known_hashes.get(path) == new_hash:
            return

        self._known_hashes[path] = new_hash
        self._last_event[path] = now

        print(f"[REAL CHANGE] {path}")

    def on_created(self, event):
        path = event.src_path
        self._known_hashes[path] = file_hash(path) or ""
        self._last_event[path] = time.time()
        print(f"[CREATED] {path}")

    def on_deleted(self, event):
        path = event.src_path
        self._known_hashes.pop(path, None)
        self._last_event.pop(path, None)
        print(f"[DELETED] {path}")


if __name__ == "__main__":
    path = "/path/to/your/directory"

    observer = Observer()
    observer.schedule(
        DebouncedHandler(patterns=["*.md", "*.py"]),
        path,
        recursive=True,
    )
    observer.start()

    print(f"Watching {path} with debounce + hash verification...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```

---

## Option B — `watchfiles` (Modern, Async-Native)

### Install

```bash
pip install watchfiles
```

### Synchronous Usage

```python
from watchfiles import watch, Change

for changes in watch("/path/to/your/directory", recursive=True):
    for change_type, path in changes:
        match change_type:
            case Change.added:
                print(f"[CREATED]  {path}")
            case Change.modified:
                print(f"[MODIFIED] {path}")
            case Change.deleted:
                print(f"[DELETED]  {path}")
```

### Async Usage

```python
import asyncio
from watchfiles import awatch, Change


async def monitor(directory: str):
    async for changes in awatch(directory, recursive=True):
        for change_type, path in changes:
            match change_type:
                case Change.added:
                    print(f"[CREATED]  {path}")
                case Change.modified:
                    print(f"[MODIFIED] {path}")
                case Change.deleted:
                    print(f"[DELETED]  {path}")


asyncio.run(monitor("/path/to/your/directory"))
```

### With Filtering

```python
from watchfiles import watch, Change, DefaultFilter


class MarkdownFilter(DefaultFilter):
    allowed_extensions = (".md", ".py", ".json")


for changes in watch("/path/to/dir", watch_filter=MarkdownFilter(), recursive=True):
    for change_type, path in changes:
        print(f"[{change_type.name.upper()}] {path}")
```

> `watchfiles` already debounces internally (default 50ms) and only reports actual content changes.

---

## Option C — Manual Polling (No Dependencies)

Best for simple scripts or one-shot "what changed since last time" checks.

```python
import time
from pathlib import Path


def snapshot(directory: str, patterns: list[str] = None) -> dict[str, float]:
    """Build a {filepath: mtime} map of all files in the directory tree."""
    root = Path(directory)
    result = {}
    globs = patterns or ["*"]
    for glob in globs:
        for p in root.rglob(glob):
            if p.is_file():
                result[str(p)] = p.stat().st_mtime
    return result


def diff_snapshots(
    old: dict[str, float],
    new: dict[str, float],
) -> dict[str, list[str]]:
    """Compare two snapshots and return created/modified/deleted lists."""
    old_keys, new_keys = set(old), set(new)
    return {
        "created":  sorted(new_keys - old_keys),
        "deleted":  sorted(old_keys - new_keys),
        "modified": sorted(
            p for p in old_keys & new_keys if old[p] != new[p]
        ),
    }


if __name__ == "__main__":
    directory = "/path/to/your/directory"
    poll_interval = 2  # seconds

    print(f"Polling {directory} every {poll_interval}s...")
    previous = snapshot(directory)

    while True:
        time.sleep(poll_interval)
        current = snapshot(directory)
        changes = diff_snapshots(previous, current)

        for kind, paths in changes.items():
            for p in paths:
                print(f"[{kind.upper()}] {p}")

        previous = current
```

---

## Edge Cases to Handle

| Issue | Cause | Fix |
| :--- | :--- | :--- |
| **Duplicate events** | Editors (Vim, VS Code) save via temp-file-then-rename | Use debounce + hash check, or also handle `on_moved` |
| **Partial writes** | Large file still being written when event fires | Add a short delay, then hash; or wait for file size to stabilize |
| **Permission errors** | Watching system or locked files | Wrap reads in `try/except` |
| **inotify limit (Linux)** | Too many subdirectories | Increase `fs.inotify.max_user_watches` via `sysctl` |
| **Symlinks** | May not be followed by default | Check library docs for symlink options |
| **New subdirectories** | Watchdog auto-adds them; polling needs re-scan | Use `recursive=True` (watchdog handles this) |

---

## Integration with Cerebro

A practical watcher service that plugs into the rest of the app:

```python
import time
import hashlib
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


class CerebroFileWatcher:
    """Watch a directory tree and call back on real file changes."""

    def __init__(
        self,
        directory: str,
        patterns: list[str] | None = None,
        debounce_seconds: float = 0.5,
        on_change=None,
    ):
        self.directory = directory
        self.on_change = on_change or self._default_callback
        self._handler = _Handler(
            patterns=patterns or ["*.md"],
            debounce_seconds=debounce_seconds,
            callback=self.on_change,
        )
        self._observer = Observer()

    def start(self):
        self._observer.schedule(self._handler, self.directory, recursive=True)
        self._observer.start()
        print(f"CerebroFileWatcher: monitoring {self.directory}")

    def stop(self):
        self._observer.stop()
        self._observer.join()

    @staticmethod
    def _default_callback(event_type: str, path: str):
        print(f"[{event_type}] {path}")


class _Handler(PatternMatchingEventHandler):
    def __init__(self, patterns, debounce_seconds, callback):
        super().__init__(patterns=patterns, ignore_directories=True)
        self.debounce_seconds = debounce_seconds
        self.callback = callback
        self._last: dict[str, float] = {}
        self._hashes: dict[str, str] = {}

    def _hash(self, path):
        try:
            return hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except Exception:
            return None

    def on_created(self, event):
        self._hashes[event.src_path] = self._hash(event.src_path) or ""
        self.callback("CREATED", event.src_path)

    def on_deleted(self, event):
        self._hashes.pop(event.src_path, None)
        self.callback("DELETED", event.src_path)

    def on_modified(self, event):
        now = time.time()
        path = event.src_path
        if (now - self._last.get(path, 0)) < self.debounce_seconds:
            return
        h = self._hash(path)
        if h and self._hashes.get(path) == h:
            return
        self._hashes[path] = h or ""
        self._last[path] = now
        self.callback("MODIFIED", path)


# Usage
if __name__ == "__main__":
    def handle(event_type, path):
        print(f"  → {event_type}: {path}")
        # e.g. trigger re-index, send Telegram notification, etc.

    watcher = CerebroFileWatcher(
        directory="/path/to/your/vault",
        patterns=["*.md"],
        on_change=handle,
    )
    watcher.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
```

---

## TL;DR

```
1. pip install watchdog        ← or watchfiles for async
2. Observer + Handler          ← recursive=True covers subdirs
3. Debounce + SHA-256 hash     ← filter phantom events
4. Pattern filtering           ← only watch *.md, *.py, etc.
5. Wrap in a service class     ← plug into Cerebro
```
