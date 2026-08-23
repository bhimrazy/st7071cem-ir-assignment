from miniseek.analyzer import Analyzer


def test_query_and_document_forms_converge():
    """The whole point of the analyzer: different surface forms, same terms."""
    analyzer = Analyzer()
    document = analyzer.analyze("Retrieval of COVID-19 datasets")
    query = analyzer.analyze("Retrieving covid-19 data")
    assert {"retriev", "covid-19", "covid", "19"} <= set(document) & set(query)


def test_hyphens_and_apostrophes_survive_tokenisation():
    """Compounds are kept whole -- and also split, so both queries work."""
    analyzer = Analyzer(stem=False, remove_stopwords=False)
    assert analyzer.analyze("COVID-19, children's health.") == [
        "covid-19",
        "covid",
        "19",
        "children's",
        "health",
    ]


def test_hyphenated_compounds_are_findable_by_their_parts():
    """A paper on 'yoga-based' work must be findable by searching 'yoga'."""
    analyzer = Analyzer()
    terms = analyzer.analyze("A digital yoga-based intervention")
    assert "yoga" in terms          # the part
    assert "yoga-bas" in terms      # and the compound


def test_possessives_are_not_split():
    """Splitting them would emit 'children' twice and double its frequency."""
    assert Analyzer().analyze("children's health") == ["children", "health"]


def test_compound_splitting_is_disableable():
    assert Analyzer(split_compounds=False).analyze("yoga-based") == ["yoga-bas"]


def test_stemming_strips_possessive_remnants():
    assert Analyzer().analyze("children's") == ["children"]


def test_stopwords_removed_before_stemming():
    """'are' must be filtered as a stopword, not survive as the stem 'ar'."""
    assert "ar" not in Analyzer().analyze("these are the results")


def test_stages_are_individually_disableable():
    text = "Retrieving the datasets"
    assert Analyzer(stem=False).analyze(text) == ["retrieving", "datasets"]
    assert Analyzer(remove_stopwords=False, stem=False).analyze(text) == [
        "retrieving",
        "the",
        "datasets",
    ]


def test_term_order_and_duplicates_are_preserved():
    """Ranking needs the counts; phrase queries need the order."""
    assert Analyzer(stem=False, remove_stopwords=False).analyze(
        "health data health"
    ) == ["health", "data", "health"]


def test_all_stopword_query_yields_nothing():
    """A documented limitation, pinned so it stays a known trade-off."""
    assert Analyzer().analyze("The Who") == []


def test_empty_and_punctuation_only_input():
    analyzer = Analyzer()
    assert analyzer.analyze("") == []
    assert analyzer.analyze("--- ... !!!") == []
