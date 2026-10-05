import os
import tempfile
from pathlib import Path


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, content: bytes) -> None:
        destination = self._path_for(key)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(content)
            os.replace(temporary_path, destination)
        except OSError:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    def delete(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)

    def read(self, key: str) -> bytes:
        return self._path_for(key).read_bytes()

    def _path_for(self, key: str) -> Path:
        if len(key) != 32 or any(character not in "0123456789abcdef" for character in key):
            raise ValueError("Invalid storage key")
        return self.root / key
