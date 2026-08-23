"""BBC News corpus for the clustering task: Economics, Entertainment, Politics.

Downloaded from the dataset's own home page rather than a third-party copy, so
the data we cluster is provably the data we cite.
"""

from __future__ import annotations

import io
import json
import random
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from clustering.paths import CORPUS_PATH, PROJECT_ROOT

CATEGORIES: tuple[str, ...] = ("Economics", "Entertainment", "Politics")

# The archive ships five folders; the brief asks for three. Its "business"
# folder is relabelled as "Economics" here. That is the closest of the five to
# what the brief asks for, but not an exact match: the folder mixes
# macroeconomic reporting (growth, unemployment, oil prices) with company news
# (takeovers, results, deals). Worth stating rather than quietly assuming the
# two words mean the same thing.
_FOLDER_MAP = {
    "business": "Economics",
    "entertainment": "Entertainment",
    "politics": "Politics",
}

# Enough per category to be well over the brief's 100-document floor while
# keeping the classes balanced, which stops k-means centroids drifting towards
# whichever category happens to be largest. The smallest of the three folders
# holds 386 articles, so this is always satisfiable.
DOCUMENTS_PER_CATEGORY = 200
SAMPLE_SEED = 42

ORIGINAL_SOURCE = "http://mlg.ucd.ie/datasets/bbc.html"
DOWNLOAD_URL = "http://mlg.ucd.ie/files/datasets/bbc-fulltext.zip"
CITATION = (
    'D. Greene and P. Cunningham, "Practical Solutions to the Problem of '
    'Diagonal Dominance in Kernel Document Clustering", Proc. 23rd '
    "International Conference on Machine Learning (ICML 2006)."
)
LICENCE_NOTE = (
    "Provided by the BBC as benchmark data for research purposes only; all "
    "rights, including copyright, remain with the BBC. Used here for "
    "non-commercial coursework with attribution."
)

DEFAULT_CACHE_PATH = CORPUS_PATH


@dataclass(slots=True)
class Provenance:
    """Where a corpus came from, kept beside it so the report can cite it."""

    source: str
    fetched_at: str
    # Relative to the backend root, so provenance files stay identical across
    # machines rather than recording somebody's home directory.
    cache_file: str = ""
    original_source: str = ORIGINAL_SOURCE
    citation: str = CITATION
    licence_note: str = LICENCE_NOTE
    category_counts: dict[str, int] = field(default_factory=dict)
    available_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "fetched_at": self.fetched_at,
            "cache_file": self.cache_file,
            "original_source": self.original_source,
            "citation": self.citation,
            "licence_note": self.licence_note,
            "category_counts": self.category_counts,
            "available_counts": self.available_counts,
        }


@dataclass(slots=True)
class Corpus:
    """Documents and their true categories.

    >>> corpus = load_corpus()
    >>> len(corpus), corpus.categories
    (600, ('Economics', 'Entertainment', 'Politics'))
    """

    documents: list[str]
    labels: list[str]
    provenance: Provenance

    def __len__(self) -> int:
        return len(self.documents)

    @property
    def categories(self) -> tuple[str, ...]:
        present = set(self.labels)
        return tuple(c for c in CATEGORIES if c in present)


def load_corpus(
    *,
    cache_path: str | Path = DEFAULT_CACHE_PATH,
    per_category: int | None = DOCUMENTS_PER_CATEGORY,
    force_refresh: bool = False,
) -> Corpus:
    """Load the corpus, downloading and caching the archive on first use.

    `per_category=None` keeps every article instead of a balanced sample.
    """
    cache_path = Path(cache_path)

    if force_refresh or not cache_path.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(_download())

    documents, labels = _read_archive(cache_path)
    if not documents:
        raise ValueError(f"no usable documents found in {cache_path}")

    available = _counts(labels)
    if per_category is not None:
        documents, labels = _balanced_sample(documents, labels, per_category)

    provenance = Provenance(
        # Always the URL: the cached file is a copy of that download, so the
        # origin is the same whether or not this call went to the network.
        source=DOWNLOAD_URL,
        fetched_at=datetime.now(UTC).isoformat(),
        cache_file=_relative(cache_path),
        category_counts=_counts(labels),
        available_counts=available,
    )
    _write_provenance(cache_path, provenance)
    return Corpus(documents=documents, labels=labels, provenance=provenance)


def _download() -> bytes:
    response = httpx.get(DOWNLOAD_URL, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    return response.content


def _read_archive(path: Path) -> tuple[list[str], list[str]]:
    """Read `bbc/<category>/<id>.txt` out of the archive, keeping our three."""
    documents: list[str] = []
    labels: list[str] = []
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
        for name in sorted(archive.namelist()):
            parts = name.split("/")
            if len(parts) != 3 or not name.endswith(".txt"):
                continue
            label = _FOLDER_MAP.get(parts[1].lower())
            if label is None:
                continue
            # Each file is a headline, a blank line, then the body. Both are
            # kept: the headline carries some of the most topical wording.
            text = archive.read(name).decode("utf-8", errors="replace").strip()
            if text:
                documents.append(text)
                labels.append(label)
    return documents, labels


def _balanced_sample(
    documents: list[str], labels: list[str], per_category: int
) -> tuple[list[str], list[str]]:
    """Take an equal number of documents per category, deterministically."""
    by_category: dict[str, list[str]] = {category: [] for category in CATEGORIES}
    for document, label in zip(documents, labels, strict=True):
        by_category[label].append(document)

    rng = random.Random(SAMPLE_SEED)
    sampled_documents: list[str] = []
    sampled_labels: list[str] = []
    for category in CATEGORIES:
        pool = by_category[category]
        # Shuffle rather than slice the head: the archive is ordered by file
        # number, which is roughly chronological, so the first N would all come
        # from the same stretch of 2004-2005 news.
        rng.shuffle(pool)
        chosen = pool[:per_category]
        sampled_documents.extend(chosen)
        sampled_labels.extend([category] * len(chosen))
    return sampled_documents, sampled_labels


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        # A cache path outside the project (a temp dir in tests, say) has no
        # meaningful relative form; the file name alone is enough.
        return path.name


def _counts(labels: list[str]) -> dict[str, int]:
    return {category: labels.count(category) for category in CATEGORIES}


def _write_provenance(cache_path: Path, provenance: Provenance) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.with_suffix(".provenance.json").write_text(
        json.dumps(provenance.to_dict(), indent=2), encoding="utf-8"
    )
