"""A read-only viewer for any miniseek collection on disk: what it holds, how
it was configured, and the documents themselves.

Deliberately generic. `Collection.open` reads the schema and analyzer back out
of `meta.json`, so this never needs to be told what a collection contains --
point it at a directory and it works, whether that is the publications index
or something else entirely. That is why it lives in `miniseek` rather than in
the API: it is a tool for the library, not for this one project's corpus.

Served with `http.server` from the standard library rather than FastAPI, which
is not squeamishness about dependencies in general -- the API uses FastAPI
happily -- but about *this* package's. `miniseek` is meant to stand on its own
under everything else; a viewer is no reason for the search library to start
depending on a web framework.

Read-only in the strict sense, via `Collection.open(read_only=True)`. That
flag exists because of this module: an ordinary open holds the log for
appending and rewrites `meta.json` on close even when nothing was added, so
the first version of this viewer quietly touched every collection it looked
at. It is now safe to point at the same directory the API is serving.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .collection import META_FILE, Collection

DEFAULT_PORT = 8100
DEFAULT_PAGE_SIZE = 10


def describe(collection: Collection) -> dict[str, Any]:
    """Counts and configuration for one collection.

    Only reports settings that are actually *persisted* -- the schema and the
    analyzer. `sync_interval` and `compact_ratio` are constructor options of
    whichever process opened the collection, so showing them here would
    describe this viewer rather than the data on disk.
    """
    schema = collection.schema
    index = collection.index
    return {
        "name": collection.name,
        "path": str(collection.path) if collection.path else None,
        "stats": {
            "documents": len(collection),
            "vocabulary": index.vocabulary_size,
            "log_entries": collection.log_entries,
            "dead_entries": collection.dead_entries,
        },
        "id_field": schema.id_field,
        "fields": [
            {
                "name": f.name,
                "indexed": f.indexed,
                "stored": f.stored,
                "weight": f.weight,
                # Average length is only meaningful for a field the index
                # actually tokenised.
                "average_length": (
                    round(index.average_field_length(f.name), 1) if f.indexed else None
                ),
            }
            for f in schema.fields
        ],
        "analyzer": collection.analyzer.config(),
    }


def documents(
    collection: Collection,
    *,
    offset: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
    contains: str = "",
) -> dict[str, Any]:
    """One page of stored documents, oldest first.

    `contains` is a plain case-insensitive substring filter over the id and the
    stored fields -- deliberately *not* a search. This is a viewer: it shows
    what is in the collection, and a ranked result set would show something
    else, ordered by a relevance score that has nothing to do with browsing.
    """
    needle = contains.strip().lower()
    matched = [
        document
        for document in collection
        if not needle or needle in _haystack(document.fields, document.id)
    ]
    window = matched[offset : offset + limit]
    return {
        "total": len(matched),
        "offset": offset,
        "limit": limit,
        "contains": contains,
        "documents": [
            {
                "id": document.id,
                "internal_id": document.internal_id,
                "fields": document.fields,
            }
            for document in window
        ],
    }


def _haystack(fields: dict[str, Any], external_id: str) -> str:
    """Everything about a document as one lowercase string, for filtering.

    JSON rather than str() so nested values (an author list of dicts) are
    searchable by their contents rather than by a Python repr.
    """
    return (external_id + " " + json.dumps(fields, ensure_ascii=False)).lower()


def open_for_viewing(path: Path) -> Collection:
    """Open an existing collection without creating or modifying anything.

    `Collection.open` would happily create an empty collection given a schema,
    and its error for a missing one talks about creating it -- neither is what
    someone pointing a viewer at the wrong directory needs to hear.
    """
    if not (path / META_FILE).exists():
        raise FileNotFoundError(
            f"no miniseek collection at {path} (expected {path / META_FILE})"
        )
    return Collection.open(path, read_only=True)


PAGE_FILE = "viewer.html"


def page() -> bytes:
    """The viewer's HTML, read from `viewer.html` next to this module.

    Read on each request rather than cached at import, so editing the page
    means refreshing the browser instead of restarting the server. The file is
    a few kilobytes on a local disk and this is a developer tool serving one
    person, so the reread costs nothing worth optimising away.

    Kept as a plain file rather than a string in this module for the obvious
    reason -- an editor can syntax-highlight and format it -- and deliberately
    *not* a Jinja template, because there is nothing to interpolate: the page
    ships static and fetches its data as JSON. A template engine here would be
    a dependency earning its keep by substituting zero variables.
    """
    return (Path(__file__).parent / PAGE_FILE).read_bytes()


class _Handler(BaseHTTPRequestHandler):
    """Serves the page and its two JSON endpoints. One collection per server."""

    collection: Collection
    directory: Path
    lock = threading.Lock()

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        route = urlparse(self.path)
        query = parse_qs(route.query)

        if route.path in ("/", "/index.html"):
            self._send(page(), "text/html; charset=utf-8")
        elif route.path == "/api/collection":
            with self.lock:
                self._json(describe(self.collection))
        elif route.path == "/api/documents":
            with self.lock:
                self._json(
                    documents(
                        self.collection,
                        offset=_int(query.get("offset"), 0),
                        limit=min(_int(query.get("limit"), DEFAULT_PAGE_SIZE), 200),
                        contains=(query.get("contains") or [""])[0],
                    )
                )
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        """Re-read the collection from disk.

        The viewer holds a snapshot: it replayed the log when it opened, so a
        re-index afterwards is invisible until something re-reads it. Cheaper
        to offer a button than to make people restart the server.
        """
        if urlparse(self.path).path != "/api/reload":
            self.send_error(404)
            return
        with self.lock:
            self.collection.close()
            type(self).collection = open_for_viewing(self.directory)
            self._json({"reloaded": True, "documents": len(self.collection)})

    def _json(self, payload: dict[str, Any]) -> None:
        self._send(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet by default: one request log line per keystroke in the filter
        box drowns out anything worth reading."""


def _int(values: list[str] | None, default: int) -> int:
    """Query parameters arrive as text and may be anything at all."""
    try:
        return max(0, int((values or [str(default)])[0]))
    except ValueError:
        return default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="miniseek-view",
        description="Browse a miniseek collection: counts, settings, documents.",
        epilog=(
            "examples:\n"
            "  miniseek-view data/index            the publications index\n"
            "  miniseek-view data/index --port 9000\n"
            "  miniseek-view data/index --no-browser\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", help="collection directory (holds meta.json)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, metavar="N")
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open a browser window"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    directory = Path(args.path)

    try:
        collection = open_for_viewing(directory)
    except (FileNotFoundError, ValueError) as error:
        print(f"miniseek-view: {error}", file=sys.stderr)
        return 1

    _Handler.collection = collection
    _Handler.directory = directory

    url = f"http://127.0.0.1:{args.port}/"
    print(f"{collection.name}: {len(collection)} documents, {directory}")
    print(f"viewing at {url}  (ctrl-c to stop)")
    if not args.no_browser:
        webbrowser.open(url)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
        _Handler.collection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
