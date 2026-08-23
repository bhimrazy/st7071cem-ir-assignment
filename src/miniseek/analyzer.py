"""The same analyzer must run over documents at index time and queries at search
time. Otherwise a search for "Retrieving" never matches an indexed
"retrieval", because the index only ever holds the stemmed form."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer

# Words are runs of letters/digits, allowing internal apostrophes and hyphens so
# that "COVID-19" and "children's" survive as single tokens rather than being
# split into fragments that no longer mean anything.
TOKEN_RE = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)*")

# Splits a hyphenated token back into its parts, so that "yoga-based" also
# indexes "yoga" and "based". Deliberately hyphens only: splitting a
# possessive would emit "children" twice, since Porter already reduces
# "children's" to "children", which would double its term frequency.
COMPOUND_SPLIT_RE = re.compile(r"-")


@lru_cache(maxsize=1)
def _english_stopwords() -> frozenset[str]:
    """Load NLTK's stopword list, downloading the corpus on first use."""
    try:
        words = stopwords.words("english")
    except LookupError:
        nltk.download("stopwords", quiet=True)
        words = stopwords.words("english")
    return frozenset(words)


@dataclass(slots=True)
class Analyzer:
    """Configurable pipeline: normalise -> tokenize -> filter -> stem.

    Each stage can be switched off, which makes it possible to show in the
    report what each one actually contributes to retrieval quality.
    """

    lowercase: bool = True
    remove_stopwords: bool = True
    stem: bool = True
    min_token_length: int = 2
    split_compounds: bool = True
    _stemmer: PorterStemmer = field(default_factory=PorterStemmer, repr=False)

    def config(self) -> dict[str, bool | int]:
        """The settings that affect output, for persisting alongside an index.

        An index built with stemming on is meaningless to an analyzer with
        stemming off, so this travels with the data.
        """
        return {
            "lowercase": self.lowercase,
            "remove_stopwords": self.remove_stopwords,
            "stem": self.stem,
            "min_token_length": self.min_token_length,
            "split_compounds": self.split_compounds,
        }

    @classmethod
    def from_config(cls, config: dict[str, bool | int]) -> Analyzer:
        return cls(**config)  # type: ignore[arg-type]

    def analyze(self, text: str) -> list[str]:
        """Return the ordered list of terms for `text`.

        Order is preserved because the index stores positions, which is what
        makes phrase queries possible later on.
        """
        if self.lowercase:
            text = text.lower()

        terms = TOKEN_RE.findall(text)

        if self.split_compounds:
            terms = self._expand_compounds(terms)

        if self.min_token_length > 1:
            terms = [t for t in terms if len(t) >= self.min_token_length]

        if self.remove_stopwords:
            stops = _english_stopwords()
            terms = [t for t in terms if t not in stops]

        if self.stem:
            # Stemming last: the stopword list is written in unstemmed form, so
            # filtering after stemming would let "ar" (from "are") slip through.
            # The strip cleans up possessives, where Porter turns "children's"
            # into a token with a dangling apostrophe.
            terms = [self._stemmer.stem(t).strip("'-") for t in terms]

        return [t for t in terms if t]

    @staticmethod
    def _expand_compounds(terms: list[str]) -> list[str]:
        """Index hyphenated and possessive compounds *and* their parts.

        Keeping "covid-19" whole is right -- splitting it produces "19", which
        is meaningless on its own. But keeping compounds *only* whole is
        wrong, and the failure is invisible: a paper titled "A digital
        yoga-based intervention" indexes the single term "yoga-bas", so a
        search for "yoga" matches nothing at all. The same silently applies to
        "cross-sectional", "gender-inclusive" and every other hyphenated
        modifier common in academic titles.

        Emitting both the compound and its parts serves both queries. Lucene
        solves this the same way with WordDelimiterGraphFilter, which emits
        parts alongside the catenated form.

        The cost: parts occupy their own positions, so a phrase query spanning
        a compound would measure distance slightly differently. Lucene avoids
        this with position increments of zero. That refinement is not
        implemented here, and is noted as a limitation.
        """
        expanded: list[str] = []
        for term in terms:
            expanded.append(term)
            if COMPOUND_SPLIT_RE.search(term):
                expanded.extend(part for part in COMPOUND_SPLIT_RE.split(term) if part)
        return expanded
