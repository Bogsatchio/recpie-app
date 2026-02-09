from enum import Enum

import pandas as pd

from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
    Prefetch,
    FusionQuery,
    Fusion,
    NearestQuery,
)

BOOSTER_VALUE = 0.1
PENALTY_VALUE = 0.005
HITS_BEFORE_BOOSTING = 200


def _enum_value(value):
    return value.value if isinstance(value, Enum) else value


def _enum_list(values):
    if values is None:
        return []
    return [_enum_value(value) for value in values]


def _build_boost_filter(*, category: str = None, cuisine: str = None, ingredients: list[str] = None) -> Filter | None:
    category_value = _enum_value(category)
    cuisine_value = _enum_value(cuisine)
    should_conditions = []
    if category_value is not None:
        should_conditions.append(FieldCondition(key="category", match=MatchValue(value=category_value)))
    if cuisine_value is not None:
        should_conditions.append(FieldCondition(key="cuisine", match=MatchValue(value=cuisine_value)))
    if ingredients is not None:
        for ingredient in ingredients:
            should_conditions.append(
                FieldCondition(key="ingredients", match=MatchValue(value=ingredient))
            )

    return Filter(should=should_conditions) if should_conditions else None


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    safe_df = df.replace([float("inf"), float("-inf")], pd.NA)
    safe_df = safe_df.astype(object).where(pd.notnull(safe_df), None)
    return safe_df.to_dict(orient="records")


def _query_qdrant(
    qd_client,
    *,
    collection_name: str,
    query_vec,
    boost_filter: Filter | None,
    score_threshold: float,
):
    if boost_filter is None:
        return qd_client.query_points(
            collection_name=collection_name,
            query=query_vec.tolist(),
            limit=HITS_BEFORE_BOOSTING,
            score_threshold=score_threshold,
            with_payload=True,
        )

    results = qd_client.query_points(
        collection_name=collection_name,
        prefetch=[
            # 1. THE VECTOR RANKER
            Prefetch(
                query=NearestQuery(nearest=query_vec.tolist()),
                limit=400,
                score_threshold=score_threshold,
            ),

            # 2. THE SOFT FILTER (BOOST) RANKER
            # Same vector query, but with a filter to boost matches.
            Prefetch(
                query=NearestQuery(nearest=query_vec.tolist()),
                filter=boost_filter,
                limit=20,
            ),
        ],
        # 3. THE MERGE LOGIC
        # This looks at both prefetch lists and combines them.
        query=FusionQuery(fusion=Fusion.RRF),
        limit=HITS_BEFORE_BOOSTING,
        with_payload=True,
    )
    return results


def _hits_to_df(recipe_repository, hits, k: int) -> pd.DataFrame:
    if not hits:
        return pd.DataFrame()

    q_df = recipe_repository.get_recipes_by_ids(
        hits.keys(),
    )
    if q_df.empty:
        q_df["score"] = pd.Series(dtype="float")
        return q_df

    q_df["score"] = q_df["id"].map(hits)
    q_df = q_df[q_df["score"].notna()]
    if q_df.empty:
        return pd.DataFrame()

    q_df = q_df.sort_values(by="score", ascending=False).head(k)
    q_df = q_df.replace([float("inf"), float("-inf")], pd.NA)
    q_df = q_df.astype(object).where(pd.notnull(q_df), None)
    return q_df


def _normalize_ingredients(ingredients):
    if not ingredients:
        return []
    if isinstance(ingredients, str):
        return [item.strip() for item in ingredients.split(",") if item.strip()]
    return [item.strip() for item in ingredients if isinstance(item, str) and item.strip()]


def _boost_score(
    score: float,
    payload: dict,
    ingredients: list[str] | None,
    category: str | None,
    cuisine: str | None,
) -> float:
    category_value = _enum_value(category)
    cuisine_value = _enum_value(cuisine)
    boost = 0.0
    query_ingredients = _normalize_ingredients(ingredients)
    if query_ingredients:
        payload_ingredients = _normalize_ingredients(payload.get("ingredients"))
        matched = len(set(query_ingredients) & set(payload_ingredients))
        boost += BOOSTER_VALUE * matched
    if category_value is not None and payload.get("category") == category_value:
        boost += BOOSTER_VALUE
    if cuisine_value is not None and payload.get("cuisine") == cuisine_value:
        boost += BOOSTER_VALUE
    return score * (1 + boost)


def _penalize_score(
    score: float,
    payload: dict,
    ingredients: list[str] | None,
    category: str | None,
    cuisine: str | None,
) -> float:
    category_value = _enum_value(category)
    cuisine_value = _enum_value(cuisine)
    penalty = 0.0
    query_ingredients = _normalize_ingredients(ingredients)
    payload_ingredients = _normalize_ingredients(payload.get("ingredients"))
    if query_ingredients and payload_ingredients:
        missing = len(set(query_ingredients) - set(payload_ingredients))
        penalty += PENALTY_VALUE * missing
    payload_category = payload.get("category")
    if category_value is not None and payload_category is not None and payload_category != category_value:
        penalty += PENALTY_VALUE
    payload_cuisine = payload.get("cuisine")
    if cuisine_value is not None and payload_cuisine is not None and payload_cuisine != cuisine_value:
        penalty += PENALTY_VALUE
    return max(0.0, score * (1 - penalty))
