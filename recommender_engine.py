import pandas as pd
from sentence_transformers import SentenceTransformer
from database import QD_INGREDIENT_COLLECTION, QD_NAME_COLLECTION

from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
    Prefetch,
)
from qdrant_client.http import models as qdrant_models

BOOSTER_VALUE = 0.15
PENALTY_VALUE = 0.8


class RecommenderEngine():

    def __init__(self, engine, qd_client, recipe_repository):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.qd_client = qd_client
        self.engine = engine
        self.recipe_repository = recipe_repository
        self.recipes_collection = QD_INGREDIENT_COLLECTION
        self.names_collection = QD_NAME_COLLECTION


    def _build_boost_filter(self, *, category: str = None, cuisine: str = None, ingredients: list[str] = None) -> Filter | None:
        should_conditions = []
        if category is not None:
            should_conditions.append(FieldCondition(key="category", match=MatchValue(value=category)))
        if cuisine is not None:
            should_conditions.append(FieldCondition(key="cuisine", match=MatchValue(value=cuisine)))
        if ingredients is not None:
            for ingredient in ingredients:
                should_conditions.append(
                    FieldCondition(key="ingredients", match=MatchValue(value=ingredient))
                )

        return Filter(should=should_conditions) if should_conditions else None

    def _query_qdrant(
        self,
        *,
        collection_name: str,
        query_vec,
        boost_filter: Filter | None,
        k: int,
        score_threshold: float,
    ):
        return self.qd_client.query_points(
            collection_name=collection_name,
            # candidate pool
            prefetch=[
                Prefetch(
                    query=query_vec.tolist(),
                    limit=400
                )
            ],
            # final rerank query = raw vector (NOT SearchRequest)
            query=query_vec.tolist(),
            query_filter=boost_filter,
            limit=k,
            score_threshold=score_threshold,
            with_payload=True
        )

    def _hits_to_df(self, hits) -> pd.DataFrame:
        if not hits:
            return pd.DataFrame(columns=["id", "name", "ingredients", "score"])

        q_df = self.recipe_repository.get_recipes_by_ids(
            self.engine,
            hits.keys(),
            columns=["id", "name", "ingredients"],
        )
        if q_df.empty:
            return pd.DataFrame(columns=["id", "name", "ingredients", "score"])

        q_df["score"] = q_df["id"].map(hits)
        return q_df.sort_values(by="score", ascending=False)

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
        boost = 0.0
        query_ingredients = self._normalize_ingredients(ingredients)
        if query_ingredients:
            payload_ingredients = self._normalize_ingredients(payload.get("ingredients"))
            matched = len(set(query_ingredients) & set(payload_ingredients))
            boost += BOOSTER_VALUE * matched
        if category is not None and payload.get("category") == category:
            boost += BOOSTER_VALUE
        if cuisine is not None and payload.get("cuisine") == cuisine:
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
        penalty = 0.0
        query_ingredients = self._normalize_ingredients(ingredients)
        payload_ingredients = self._normalize_ingredients(payload.get("ingredients"))
        if query_ingredients and payload_ingredients:
            missing = len(set(query_ingredients) - set(payload_ingredients))
            penalty += PENALTY_VALUE * missing
        payload_category = payload.get("category")
        if category is not None and payload_category is not None and payload_category != category:
            penalty += PENALTY_VALUE
        payload_cuisine = payload.get("cuisine")
        if cuisine is not None and payload_cuisine is not None and payload_cuisine != cuisine:
            penalty += PENALTY_VALUE
        return max(0.0, score * (1 - penalty))

    def find_recipe_by_ingredients(self, user_ingredients: str, k: int = 5, category: str = None, cuisine: str = None) -> pd.DataFrame:
        query_vec = self.model.encode(user_ingredients, normalize_embeddings=True)
        query_ingredients = self._normalize_ingredients(user_ingredients)

        boost_filter = self._build_boost_filter(category=category, cuisine=cuisine)
        results = self._query_qdrant(
            collection_name=self.recipes_collection,
            query_vec=query_vec,
            boost_filter=boost_filter,
            k=k,
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
        return self._hits_to_df(hits)

    def find_recipe_by_name(
        self,
        recipe_name: str,
        k: int = 5,
        category: str = None,
        cuisine: str = None,
        ingredients: list[str] = None,
    ) -> pd.DataFrame:
        query_vec = self.model.encode(recipe_name, normalize_embeddings=True)

        boost_filter = self._build_boost_filter(category=category, cuisine=cuisine, ingredients=ingredients)
        results = self._query_qdrant(
            collection_name=self.names_collection,
            query_vec=query_vec,
            boost_filter=boost_filter,
            k=200,
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
        return self._hits_to_df(hits)

    def upsert_embedding(self, recipe_id: int, recipe) -> None:
        """
        Embed recipe ingredients and upsert the vector + payload into Qdrant.
        Accepts a recipe object (Pydantic model or dict) with ingredients, category, cuisine, cooking_methods.
        """
        if isinstance(recipe, dict):
            ingredients = recipe["ingredients"]
            name = recipe["name"]
            category = recipe["category"]
            cuisine = recipe["cuisine"]
            cooking_methods = recipe["cooking_methods"]
        else:
            ingredients = recipe.ingredients
            name = recipe.name
            category = recipe.category
            cuisine = recipe.cuisine
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
