import pandas as pd

from recommender_engine.re_utils import (
    _boost_score,
    _df_to_records,
    _hits_to_df,
    _normalize_ingredients,
    _penalize_score,
)


def test_normalize_ingredients_handles_string_list_and_empty_values():
    assert _normalize_ingredients("tomato, onion, , garlic") == ["tomato", "onion", "garlic"]
    assert _normalize_ingredients([" tomato ", "", 12, "onion"]) == ["tomato", "onion"]
    assert _normalize_ingredients(None) == []


def test_boost_score_increases_for_matching_metadata_and_ingredients():
    payload = {
        "ingredients": ["tomato", "onion"],
        "category": "Soup",
        "cuisine": "European",
    }

    score = _boost_score(1.0, payload, ["tomato"], "Soup", "European")

    assert score == 1.3


def test_penalize_score_reduces_for_missing_ingredients_and_mismatched_metadata():
    payload = {
        "ingredients": ["tomato"],
        "category": "Salad",
        "cuisine": "Asian",
    }

    score = _penalize_score(1.0, payload, ["tomato", "onion"], "Soup", "European")

    assert score == 0.985


def test_df_to_records_replaces_nan_with_none():
    df = pd.DataFrame([{"name": "Soup", "rating": float("nan")}])

    assert _df_to_records(df) == [{"name": "Soup", "rating": None}]


def test_hits_to_df_fetches_sorts_and_limits_records():
    class FakeRepository:
        def get_recipes_by_ids(self, ids):
            assert set(ids) == {1, 2, 3}
            return pd.DataFrame(
                [
                    {"id": 1, "name": "One"},
                    {"id": 2, "name": "Two"},
                    {"id": 3, "name": "Three"},
                ]
            )

    df = _hits_to_df(FakeRepository(), {1: 0.7, 2: 0.9, 3: 0.8}, 2)

    assert list(df["id"]) == [2, 3]
    assert list(df["score"]) == [0.9, 0.8]
