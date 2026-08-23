"""Tests for Task 2's clustering pipeline.

Deliberately network-free: the fitting/prediction/evaluation tests build a
small synthetic corpus locally rather than calling `load_corpus`, which would
either hit the network or depend on a cache file that may not exist in CI.
The one test that does exercise `load_corpus` skips itself when neither a
cache nor network access is available, rather than failing the suite.
"""

from __future__ import annotations

import pytest

from clustering.dataset import DEFAULT_CACHE_PATH, load_corpus
from clustering.evaluate import elbow_sweep, evaluate
from clustering.model import ClusteringModel

# Three clearly separated topics with enough within-topic vocabulary overlap
# that K-means has something real to cluster on, and enough documents per
# category (15) that silhouette scoring and majority-vote labelling are
# meaningful rather than degenerate.
_ECONOMICS = [
    "The central bank raised interest rates to curb inflation across the economy.",
    "Stock markets fell after unemployment figures disappointed investors.",
    "The government announced a budget aimed at reducing the national deficit.",
    "Economists warned a manufacturing slowdown could trigger a recession.",
    "The company reported strong quarterly profits boosting shareholder confidence.",
    "Trade negotiations between the two countries collapsed over tariffs.",
    "The housing market cooled as mortgage rates climbed to a decade high.",
    "Oil prices surged following supply disruptions from major exporters.",
    "The finance minister defended new tax reforms as necessary for growth.",
    "Consumer spending rose modestly despite cost of living pressures.",
    "The stock exchange closed higher after strong export figures.",
    "Analysts expect the economy to grow steadily next fiscal quarter.",
    "The central bank held interest rates steady amid inflation concerns.",
    "Shares in the banking sector rallied after strong earnings reports.",
    "The trade deficit narrowed as exports of manufactured goods increased.",
]
_ENTERTAINMENT = [
    "The film won several awards at the ceremony including best original score.",
    "The singer announced a world tour to promote her latest album.",
    "Critics praised the actor's performance in the new drama series.",
    "The streaming service confirmed a second season for the hit comedy show.",
    "Fans queued overnight for tickets to the highly anticipated concert.",
    "The director revealed plans for a sequel after the film's box office success.",
    "A new exhibition celebrating classic cinema opened at the gallery this week.",
    "The band's surprise reunion delighted long-time fans at the festival.",
    "The novelist's latest book topped the bestseller list within days.",
    "The television network unveiled its lineup of shows for the coming season.",
    "The actress received a nomination for her role in the new drama film.",
    "The album debuted at number one on the music charts this week.",
    "The comedian's new stand-up special premiered on the streaming platform.",
    "The orchestra performed a sold-out concert at the historic theatre.",
    "The movie studio announced a new franchise starring the award-winning actor.",
]
_POLITICS = [
    "The prime minister faced questions in parliament over immigration policy.",
    "Opposition leaders criticised the government's handling of the health crisis.",
    "Voters head to the polls next week in a tightly contested general election.",
    "The president signed an executive order addressing climate change targets.",
    "Lawmakers debated a controversial bill on data privacy late into the night.",
    "The coalition government announced a reshuffle of key cabinet positions.",
    "Protesters gathered outside parliament to demand electoral reform.",
    "The foreign secretary met counterparts to discuss the diplomatic dispute.",
    "A new poll suggests the ruling party's approval rating has dropped sharply.",
    "The senate passed the amended legislation after months of negotiation.",
    "The opposition party unveiled its manifesto ahead of the general election.",
    "Ministers clashed over the proposed reforms to the voting system.",
    "The government faced a vote of no confidence following the scandal.",
    "The president's approval rating fell after the controversial policy announcement.",
    "Parliament will reconvene next month to debate the new immigration bill.",
]

CATEGORY_ORDER = ("Economics", "Entertainment", "Politics")


def _tag(sentences: list[str], marker: str) -> list[str]:
    """Append a repeated, category-unique marker word to each sentence.

    A 15-document-per-category fixture is tiny next to the real ~1,300
    document BBC corpus, and with such a small, sparse TF-IDF matrix K-means'
    random centroid initialisation can occasionally settle on a locally
    optimal but topically wrong split (this is a real property of K-means,
    not a fixture bug). Repeating a category-unique token gives TF-IDF a
    strong, unambiguous signal to anchor each cluster on, so the fixture
    exercises the *mapping and prediction machinery* deterministically without
    relying on K-means finding subtle natural-language topic structure in 15
    short sentences -- that is what the real BBC-corpus run demonstrates.
    """
    return [f"{s} {(marker + ' ') * 4}".strip() for s in sentences]


@pytest.fixture
def synthetic_corpus() -> tuple[list[str], list[str]]:
    documents = (
        _tag(_ECONOMICS, "econsignal")
        + _tag(_ENTERTAINMENT, "entsignal")
        + _tag(_POLITICS, "politsignal")
    )
    labels = (
        ["Economics"] * len(_ECONOMICS)
        + ["Entertainment"] * len(_ENTERTAINMENT)
        + ["Politics"] * len(_POLITICS)
    )
    return documents, labels


@pytest.fixture
def fitted_model(synthetic_corpus) -> ClusteringModel:
    documents, labels = synthetic_corpus
    # min_df=1: the synthetic corpus is far smaller than the real one, and the
    # library default of min_df=2 combined with a tiny vocabulary could drop
    # too many terms otherwise.
    return ClusteringModel.fit(documents, labels, min_df=1)


class TestFitting:
    def test_produces_three_clusters(self, fitted_model, synthetic_corpus):
        documents, _ = synthetic_corpus
        tfidf_matrix = fitted_model.vectorizer.transform(documents)
        cluster_ids = fitted_model.kmeans.predict(tfidf_matrix)
        assert set(cluster_ids) == {0, 1, 2}

    def test_cluster_to_category_mapping_is_a_bijection(self, fitted_model):
        """Each of the three well-separated topics should claim its own cluster.

        This is a property of the well-separated synthetic fixture, not a
        guarantee K-means gives in general -- real, messier data (see the BBC
        corpus results) can have two clusters agree on a majority label.
        """
        mapping = fitted_model.cluster_to_category
        assert set(mapping.keys()) == {0, 1, 2}
        assert set(mapping.values()) == set(CATEGORY_ORDER)

    def test_top_terms_per_cluster_are_nonempty_and_distinct(self, fitted_model):
        top_terms = fitted_model.top_terms_per_cluster(top_n=5)
        assert set(top_terms.keys()) == {0, 1, 2}
        for terms in top_terms.values():
            assert len(terms) == 5
            assert all(isinstance(t, str) and t for t in terms)


class TestPrediction:
    @pytest.mark.parametrize(
        ("sentence", "expected_category"),
        [
            (
                "The chancellor announced a new budget to tackle rising inflation.",
                "Economics",
            ),
            (
                "The actress won an award for her performance in the new film.",
                "Entertainment",
            ),
            (
                "Parliament debated the new immigration bill for hours.",
                "Politics",
            ),
        ],
    )
    def test_predict_assigns_a_plausible_category(
        self, fitted_model, sentence, expected_category
    ):
        assignment = fitted_model.predict(sentence)
        assert assignment.category in CATEGORY_ORDER
        assert assignment.cluster_id in {0, 1, 2}
        # Each topic in the fixture is written with strongly distinctive
        # vocabulary, so an on-topic new sentence should land in its own
        # cluster rather than merely landing in *some* valid cluster.
        assert assignment.category == expected_category

    def test_predict_distances_cover_every_category(self, fitted_model):
        assignment = fitted_model.predict("A short, ambiguous sentence.")
        assert set(assignment.distances.keys()) == set(CATEGORY_ORDER)
        assert all(d >= 0 for d in assignment.distances.values())

    def test_predict_many_matches_individual_predict(self, fitted_model):
        sentences = ["The election result surprised everyone.", "The album sold well."]
        batch = fitted_model.predict_many(sentences)
        individual = [fitted_model.predict(s) for s in sentences]
        assert [a.category for a in batch] == [a.category for a in individual]


class TestPersistence:
    def test_save_and_load_roundtrip_predicts_identically(self, fitted_model, tmp_path):
        path = tmp_path / "model.pkl"
        fitted_model.save(path)
        reloaded = ClusteringModel.load(path)

        sentence = "The prime minister addressed parliament on the new policy."
        original = fitted_model.predict(sentence)
        restored = reloaded.predict(sentence)
        assert original.category == restored.category
        assert original.cluster_id == restored.cluster_id


class TestEvaluation:
    def test_metrics_are_in_valid_ranges(self, fitted_model, synthetic_corpus):
        documents, labels = synthetic_corpus
        tfidf_matrix = fitted_model.vectorizer.transform(documents)
        cluster_ids = fitted_model.kmeans.predict(tfidf_matrix)

        report = evaluate(
            tfidf_matrix,
            list(cluster_ids),
            fitted_model.kmeans,
            labels,
            fitted_model.cluster_to_category,
            k_range=range(2, 5),
        )

        assert -1.0 <= report.silhouette <= 1.0
        assert report.inertia >= 0.0
        assert report.chosen_k == 3

        assert report.extrinsic is not None
        extrinsic = report.extrinsic
        assert -1.0 <= extrinsic.adjusted_rand_index <= 1.0
        assert 0.0 <= extrinsic.normalized_mutual_info <= 1.0
        assert 0.0 <= extrinsic.homogeneity <= 1.0
        assert 0.0 <= extrinsic.completeness <= 1.0
        assert 0.0 <= extrinsic.v_measure <= 1.0
        # A well-separated synthetic corpus should cluster almost perfectly.
        assert extrinsic.adjusted_rand_index > 0.8

        row_total = sum(sum(row) for row in extrinsic.confusion)
        assert row_total == len(documents)

    def test_elbow_sweep_covers_requested_k_range(self, fitted_model, synthetic_corpus):
        documents, _ = synthetic_corpus
        tfidf_matrix = fitted_model.vectorizer.transform(documents)
        sweep = elbow_sweep(tfidf_matrix, k_range=range(2, 5))

        assert [p.k for p in sweep] == [2, 3, 4]
        # Inertia is monotonically non-increasing as k grows -- more clusters
        # can only reduce (or match) within-cluster variance.
        inertias = [p.inertia for p in sweep]
        assert inertias == sorted(inertias, reverse=True)


class TestDatasetLoading:
    def test_load_corpus_has_at_least_100_documents_across_three_categories(self):
        """Uses the real BBC corpus if a cache (or network) is available.

        Skipped rather than failed when neither is available, per the brief:
        this pipeline must not require network access to be tested, but when
        the real corpus *is* reachable it is worth checking against it.
        """
        try:
            corpus = load_corpus()
        except ConnectionError:
            pytest.skip("no cached corpus and no network access")

        if (
            corpus.provenance.source == "synthetic-fallback"
            and not DEFAULT_CACHE_PATH.exists()
        ):
            pytest.skip("only the synthetic fallback corpus is available")

        assert len(corpus) >= 100
        assert set(corpus.labels) == set(CATEGORY_ORDER)
