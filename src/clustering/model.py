from __future__ import annotations

import pickle
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from clustering.paths import MODEL_PATH
from miniseek.analyzer import Analyzer

DEFAULT_N_CLUSTERS = 3
DEFAULT_RANDOM_STATE = 42
DEFAULT_MODEL_PATH = MODEL_PATH


@dataclass(slots=True)
class ClusterAssignment:
    """Where one document landed, and how close it was to every centroid."""

    cluster_id: int
    category: str
    distances: dict[str, float]
    # The heaviest terms the input shared with the training vocabulary, and how
    # many it shared in total.
    matched_terms: list[str]
    matched_term_count: int

    @property
    def margin(self) -> float:
        """How much closer the winning centroid is than the runner-up, in [0, 1].

        Values are small in absolute terms: in a 5000-dimension sparse space
        almost every document sits close to distance 1 from every centroid, so
        a margin of 0.02 is a comfortable win, not a coin toss. Useful for
        comparing two assignments, not as a probability.
        """
        ordered = sorted(self.distances.values())
        if len(ordered) < 2 or ordered[1] == 0:
            return 0.0
        return float(1.0 - ordered[0] / ordered[1])


@dataclass(slots=True)
class ClusteringModel:
    """A fitted vectoriser + clusterer, plus human-readable cluster names.

    >>> corpus = load_corpus()
    >>> model = ClusteringModel.fit(corpus.documents, corpus.labels)
    >>> model.predict("Shares fell after the budget was announced.").category
    'Economics'
    >>> model.save()
    """

    vectorizer: TfidfVectorizer
    kmeans: KMeans
    cluster_to_category: dict[int, str]
    n_clusters: int = DEFAULT_N_CLUSTERS
    random_state: int = DEFAULT_RANDOM_STATE

    @classmethod
    def fit(
        cls,
        documents: list[str],
        labels: list[str],
        *,
        n_clusters: int = DEFAULT_N_CLUSTERS,
        random_state: int = DEFAULT_RANDOM_STATE,
        analyzer: Analyzer | None = None,
        max_features: int | None = 5000,
        min_df: int = 2,
    ) -> ClusteringModel:
        """Cluster `documents`, then name each cluster by majority vote on `labels`.

        K-means never sees `labels`: they are used only after the fact to turn
        cluster ids into category names.
        """
        if len(documents) != len(labels):
            raise ValueError("documents and labels must be the same length")

        text_analyzer = analyzer or Analyzer()
        vectorizer = TfidfVectorizer(
            # Task 1's analyzer, so both tasks agree on what a term is.
            tokenizer=text_analyzer.analyze,
            preprocessor=str,
            lowercase=False,
            token_pattern=None,
            max_features=max_features,
            min_df=min_df,
            # log(1 + tf) instead of raw tf. Without this, a long article that
            # repeats one word 30 times sits far out along that axis and drags
            # a centroid with it, so clusters form around article length as
            # much as topic. It is the same saturation idea BM25 applies in
            # Task 1, and on this corpus it lifts ARI from 0.827 to 0.907.
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(documents)

        kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
        cluster_ids = kmeans.fit_predict(matrix)

        return cls(
            vectorizer=vectorizer,
            kmeans=kmeans,
            cluster_to_category=_majority_vote_labels(cluster_ids, labels, n_clusters),
            n_clusters=n_clusters,
            random_state=random_state,
        )

    def predict(self, text: str) -> ClusterAssignment:
        """Assign an unseen document to the nearest cluster."""
        vector = self.vectorizer.transform([text])
        cluster_id = int(self.kmeans.predict(vector)[0])
        distances = self.kmeans.transform(vector)[0]
        matched = self._matched_terms(vector)
        return ClusterAssignment(
            cluster_id=cluster_id,
            category=self.category_for_cluster(cluster_id),
            distances={
                self.category_for_cluster(i): float(distances[i])
                for i in range(self.n_clusters)
            },
            matched_terms=matched[:8],
            matched_term_count=len(matched),
        )

    def predict_many(self, texts: list[str]) -> list[ClusterAssignment]:
        return [self.predict(text) for text in texts]

    def top_terms_per_cluster(self, top_n: int = 10) -> dict[int, list[str]]:
        """The highest-weighted terms at each centroid: what the cluster is about."""
        terms = self.vectorizer.get_feature_names_out()
        centroids = self.kmeans.cluster_centers_
        return {
            cluster_id: [
                terms[i] for i in centroids[cluster_id].argsort()[::-1][:top_n]
            ]
            for cluster_id in range(self.n_clusters)
        }

    def category_for_cluster(self, cluster_id: int) -> str:
        return self.cluster_to_category.get(cluster_id, f"cluster-{cluster_id}")

    def _matched_terms(self, vector: Any) -> list[str]:
        """Vocabulary terms the input actually contributed, heaviest first.

        Words absent from the training vocabulary carry no weight at all, so
        showing what did match explains an assignment the user disagrees with.
        """
        terms = self.vectorizer.get_feature_names_out()
        row = vector.tocoo()
        ranked = sorted(zip(row.col, row.data), key=lambda pair: pair[1], reverse=True)
        return [str(terms[index]) for index, _ in ranked]

    def save(self, path: str | Path = DEFAULT_MODEL_PATH) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as handle:
            pickle.dump(self, handle)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_MODEL_PATH) -> ClusteringModel:
        with open(Path(path), "rb") as handle:
            model = pickle.load(handle)
        if not isinstance(model, cls):
            raise TypeError(f"{path} does not contain a {cls.__name__}")
        return model


def _majority_vote_labels(
    cluster_ids: Any, true_labels: list[str], n_clusters: int
) -> dict[int, str]:
    votes: dict[int, Counter[str]] = {i: Counter() for i in range(n_clusters)}
    for cluster_id, label in zip(cluster_ids, true_labels, strict=True):
        votes[int(cluster_id)][label] += 1
    return {
        cluster_id: counter.most_common(1)[0][0] if counter else f"cluster-{cluster_id}"
        for cluster_id, counter in votes.items()
    }
