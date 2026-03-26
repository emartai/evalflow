"""Response cache for offline eval reuse."""

from __future__ import annotations

import hashlib
import shelve
from pathlib import Path
from typing import Any


class ResponseCache:
    """Shelve-backed response cache."""

    def __init__(self, cache_dir: Path = Path(".evalflow")) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.cache_dir / "response_cache"

    def _make_key(self, provider: str, model: str, prompt: str) -> str:
        payload = f"{provider}:{model}:{prompt}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def get(self, *args: str) -> str | None:
        """Return a cached response by key or provider/model/prompt triple."""

        key = self._resolve_key(*args)
        with shelve.open(str(self.cache_path)) as db:
            return db.get(key)

    def set(self, *args: str) -> None:
        """Persist a cached response by key or provider/model/prompt triple."""

        if len(args) == 2:
            key, response = args
        elif len(args) == 4:
            provider, model, prompt, response = args
            key = self._make_key(provider, model, prompt)
        else:
            raise TypeError("set() expects (key, response) or (provider, model, prompt, response)")
        with shelve.open(str(self.cache_path), writeback=False) as db:
            db[key] = response

    def get_for_prompt(self, provider: str, model: str, prompt: str) -> str | None:
        """Convenience wrapper for prompt-shaped cache lookups."""

        return self.get(self._make_key(provider, model, prompt))

    def set_for_prompt(
        self, provider: str, model: str, prompt: str, response: str
    ) -> None:
        """Convenience wrapper for prompt-shaped cache writes."""

        self.set(self._make_key(provider, model, prompt), response)

    def clear(self) -> None:
        with shelve.open(str(self.cache_path), writeback=False) as db:
            db.clear()

    def stats(self) -> dict[str, Any]:
        with shelve.open(str(self.cache_path)) as db:
            entries = len(db)
        size_bytes = sum(
            path.stat().st_size
            for path in self.cache_dir.glob("response_cache*")
            if path.is_file()
        )
        return {"entries": entries, "size_bytes": size_bytes}

    def _resolve_key(self, *args: str) -> str:
        if len(args) == 1:
            return args[0]
        if len(args) == 3:
            provider, model, prompt = args
            return self._make_key(provider, model, prompt)
        raise TypeError("get() expects (key) or (provider, model, prompt)")
