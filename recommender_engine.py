import pandas as pd
from enum import Enum
from sentence_transformers import SentenceTransformer
from database import QD_INGREDIENT_COLLECTION, QD_NAME_COLLECTION

from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
    Prefetch,
    FusionQuery,
    Fusion,
    NearestQuery
)
from qdrant_client.http import models as qdrant_models

BOOSTER_VALUE = 0.08
PENALTY_VALUE = 0.005
HITS_BEFORE_BOOSTING = 200


class RecommenderEngine():

    def __init__(self, engine, qd_client, recipe_repository):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.qd_client = qd_client
        self.engine = engine
        self.recipe_repository = recipe_repository
        self.recipes_collection = QD_INGREDIENT_COLLECTION
        self.names_collection = QD_NAME_COLLECTION

    def _enum_value(self, value):
        return value.value if isinstance(value, Enum) else value

    def _enum_list(self, values):
        if values is None:
            return []
        return [self._enum_value(value) for value in values]


    def _build_boost_filter(self, *, category: str = None, cuisine: str = None, ingredients: list[str] = None) -> Filter | None:
        category_value = self._enum_value(category)
        cuisine_value = self._enum_value(cuisine)
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
    
    def _df_to_records(self, df: pd.DataFrame) -> list[dict]:
        if df is None or df.empty:
            return []
        safe_df = df.replace([float("inf"), float("-inf")], pd.NA)
        safe_df = safe_df.astype(object).where(pd.notnull(safe_df), None)
        return safe_df.to_dict(orient="records")

    def _query_qdrant(
        self,
        *,
        collection_name: str,
        query_vec,
        boost_filter: Filter | None,
        score_threshold: float,
    ):
        if boost_filter is None:
            return self.qd_client.query_points(
                collection_name=collection_name,
                query=query_vec.tolist(),
                limit=HITS_BEFORE_BOOSTING,
                score_threshold=score_threshold,
                with_payload=True,
            )

        results = self.qd_client.query_points(
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

    def _hits_to_df(self, hits, k: int) -> pd.DataFrame:
        if not hits:
            return pd.DataFrame()

        q_df = self.recipe_repository.get_recipes_by_ids(
            self.engine,
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

    def _normalize_ingredients(self, ingredients):
        if not ingredients:
            return []
        if isinstance(ingredients, str):
            return [item.strip() for item in ingredients.split(",") if item.strip()]
        return [item.strip() for item in ingredients if isinstance(item, str) and item.strip()]

    def _boost_score(
        self,
        score: float,
        payload: dict,
        ingredients: list[str] | None,
        category: str | None,
        cuisine: str | None,
    ) -> float:
        category_value = self._enum_value(category)
        cuisine_value = self._enum_value(cuisine)
        boost = 0.0
        query_ingredients = self._normalize_ingredients(ingredients)
        if query_ingredients:
            payload_ingredients = self._normalize_ingredients(payload.get("ingredients"))
            matched = len(set(query_ingredients) & set(payload_ingredients))
            boost += BOOSTER_VALUE * matched
        if category_value is not None and payload.get("category") == category_value:
            boost += BOOSTER_VALUE
        if cuisine_value is not None and payload.get("cuisine") == cuisine_value:
            boost += BOOSTER_VALUE
        return score * (1 + boost)

    def _penalize_score(
        self,
        score: float,
        payload: dict,
        ingredients: list[str] | None,
        category: str | None,
        cuisine: str | None,
    ) -> float:
        category_value = self._enum_value(category)
        cuisine_value = self._enum_value(cuisine)
        penalty = 0.0
        query_ingredients = self._normalize_ingredients(ingredients)
        payload_ingredients = self._normalize_ingredients(payload.get("ingredients"))
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

    def find_recipe_by_ingredients(self, user_ingredients: str, k: int = 5, category: str = None, cuisine: str = None) -> list[dict]:
        query_vec = self.model.encode(user_ingredients, normalize_embeddings=True)
        query_ingredients = self._normalize_ingredients(user_ingredients)

        boost_filter = self._build_boost_filter(category=category, cuisine=cuisine)
        results = self._query_qdrant(
            collection_name=self.recipes_collection,
            query_vec=query_vec,
            boost_filter=boost_filter,
            score_threshold=0.2,
        )

        hits = {
            hit.payload["ID"]: self._penalize_score(
                self._boost_score(
                    hit.score,
                    hit.payload,
                    query_ingredients,
                    category,
                    cuisine,
                ),
                hit.payload,
                query_ingredients,
                category,
                cuisine,
            )
            for hit in results.points
        }
        return self._df_to_records(self._hits_to_df(hits, k))

    def find_recipe_by_name(
        self,
        recipe_name: str,
        k: int = 5,
        category: str = None,
        cuisine: str = None,
        ingredients: list[str] = None,
    ) -> list[dict]:
        query_vec = self.model.encode(recipe_name, normalize_embeddings=True)

        boost_filter = self._build_boost_filter(category=category, cuisine=cuisine, ingredients=ingredients)
        results = self._query_qdrant(
            collection_name=self.names_collection,
            query_vec=query_vec,
            boost_filter=boost_filter,
            score_threshold=0.3,
        )

        hits = {
            hit.payload["ID"]: self._penalize_score(
                self._boost_score(
                    hit.score,
                    hit.payload,
                    ingredients,
                    category,
                    cuisine,
                ),
                hit.payload,
                ingredients,
                category,
                cuisine,
            )
            for hit in results.points
        }
        return self._df_to_records(self._hits_to_df(hits, k))

    def upsert_embedding(self, recipe_id: int, recipe) -> None:
        """
        Embed recipe ingredients and upsert the vector + payload into Qdrant.
        Accepts a recipe object (Pydantic model or dict) with ingredients, category, cuisine, cooking_methods.
        """
        if isinstance(recipe, dict):
            ingredients = recipe["ingredients"]
            name = recipe["name"]
            category = self._enum_list(recipe["category"])
            cuisine = self._enum_value(recipe["cuisine"])
            cooking_methods = recipe["cooking_methods"]
        else:
            ingredients = recipe.ingredients
            name = recipe.name
            category = self._enum_list(recipe.category)
            cuisine = self._enum_value(recipe.cuisine)
            cooking_methods = recipe.cooking_methods

        ingredients_text = ", ".join(ingredients)
        embedding = self.model.encode(
            ingredients_text,
            normalize_embeddings=True,
        )
        point = qdrant_models.PointStruct(
            id=recipe_id,
            vector=embedding.tolist(),
            payload={
                "ID": recipe_id,
                "category": category,
                "cuisine": cuisine,
                "cooking_methods": cooking_methods,
            },
        )
        self.qd_client.upsert(
            collection_name=self.recipes_collection,
            points=[point],
        )

        name_embedding = self.model.encode(
            name,
            normalize_embeddings=True,
        )
        name_point = qdrant_models.PointStruct(
            id=recipe_id,
            vector=name_embedding.tolist(),
            payload={
                "ID": recipe_id,
                "ingredients": ingredients,
                "category": category,
                "cuisine": cuisine,
                "cooking_methods": cooking_methods,

            },
        )
        self.qd_client.upsert(
            collection_name=self.names_collection,
            points=[name_point],
        )

    def remove_recipe_from_indexes(self, recipe_id: int) -> None:
        """
        Remove a recipe's vector from Qdrant by ID.
        """
        self.qd_client.delete(
            collection_name=self.recipes_collection,
            points_selector=qdrant_models.PointIdsList(points=[recipe_id]),
        )

        self.qd_client.delete(
            collection_name=self.names_collection,
            points_selector=qdrant_models.PointIdsList(points=[recipe_id]),
        )
