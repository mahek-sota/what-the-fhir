"""A deliberately small, polite, read-only FHIR REST client.

No FHIR library on purpose: every call is a plain HTTP GET returning raw JSON.

Politeness rules baked in:
- GET only (there is no method for anything else).
- Small pages (_count=50) and a hard cap on pages followed (20).
- A short sleep before every real network request.
- A request timeout.
- Every raw response is cached under cache/<server>/ so reruns don't re-hit the server.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlencode

import httpx

SERVERS: dict[str, str] = {
    "smart": "https://r4.smarthealthit.org",
    "hapi": "https://hapi.fhir.org/baseR4",
}

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "cache"
PAGE_SIZE = 50
MAX_PAGES = 20
SLEEP_SECONDS = 1.0
TIMEOUT_SECONDS = 30.0


class FhirClient:
    def __init__(
        self,
        name: str,
        base_url: str | None = None,
        *,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        sleep_seconds: float = SLEEP_SECONDS,
        timeout: float = TIMEOUT_SECONDS,
        max_pages: int = MAX_PAGES,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.name = name
        self.base_url = (base_url or SERVERS[name]).rstrip("/")
        self.cache_dir = Path(cache_dir) / name
        self.sleep_seconds = sleep_seconds
        self.max_pages = max_pages
        self.network_calls = 0  # how many requests actually went over the wire
        self._http = httpx.Client(
            timeout=timeout,
            headers={"Accept": "application/fhir+json", "User-Agent": "fhirlearn/0.1"},
            follow_redirects=True,
            transport=transport,
        )

    # -- URL + cache helpers -------------------------------------------------

    def build_url(self, path_or_url: str, params: dict[str, Any] | None = None) -> str:
        """Turn 'Patient' + params into a full URL. Absolute URLs (e.g. 'next' links) pass through."""
        if path_or_url.startswith(("http://", "https://")):
            url = path_or_url
        else:
            url = f"{self.base_url}/{path_or_url.lstrip('/')}"
        if params:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode(sorted(params.items()))}"
        return url

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        return self.cache_dir / f"{digest}.json"

    # -- the only way to talk to a server: GET -------------------------------

    def get(self, path_or_url: str, params: dict[str, Any] | None = None) -> dict:
        url = self.build_url(path_or_url, params)
        cache_file = self._cache_path(url)
        if cache_file.exists():
            return json.loads(cache_file.read_text())["body"]

        time.sleep(self.sleep_seconds)
        self.network_calls += 1
        resp = self._http.get(url)
        resp.raise_for_status()
        body = resp.json()

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"url": url, "body": body}, indent=1))
        return body

    def iter_pages(self, resource_type: str, params: dict[str, Any] | None = None) -> Iterator[dict]:
        """Yield search Bundles, following link[relation=next] up to max_pages."""
        params = {"_count": PAGE_SIZE, **(params or {})}
        url: str | None = self.build_url(resource_type, params)
        pages = 0
        while url and pages < self.max_pages:
            bundle = self.get(url)
            pages += 1
            yield bundle
            url = next_link(bundle)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "FhirClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def next_link(bundle: dict) -> str | None:
    for link in bundle.get("link", []):
        if link.get("relation") == "next":
            return link.get("url")
    return None


def entries(bundle: dict) -> list[dict]:
    """The resources inside a Bundle (Bundle.entry[].resource)."""
    return [e["resource"] for e in bundle.get("entry", []) if "resource" in e]
