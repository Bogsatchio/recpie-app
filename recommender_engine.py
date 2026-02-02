import pandas as pd
import numpy as np
import faiss
from sqlalchemy import create_engine
from sentence_transformers import SentenceTransformer

from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
    Prefetch
)


class RecommenderEngine():

    def __init__(self, engine, qd_client):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.qd_client = qd_client
        self.engine = engine

    def find_recipe(self, user_ingredients: str, k: int = 5, category: str = None, cuisine: str = None) -> pd.DataFrame:
        query_vec = self.model.encode(user_ingredients, normalize_embeddings=True)

        # One boosting condition is based on list value and another on exact match to a string
        should_conditions = []
        if category is not None:
            should_conditions.append(FieldCondition(key="category", match=MatchValue(value=category)))
        if cuisine is not None:
            should_conditions.append(FieldCondition(key="cuisine", match=MatchValue(value=cuisine)))

        boost_filter = Filter(should=should_conditions) if should_conditions else None
        print(boost_filter)


        results = self.qd_client.query_points(
            collection_name="recipes",

            # candidate pool
            prefetch=[
                Prefetch(
                    query=query_vec.tolist(),
                    limit=200
                )
            ],

            # final rerank query = raw vector (NOT SearchRequest)
            query=query_vec.tolist(),

            query_filter=boost_filter,
            limit=k,
            score_threshold=0.1,
            with_payload=True
        )

        hits = {hit.payload["ID"]: hit.score for hit in results.points}
        q_df = pd.read_sql(f"SELECT id, name, ingredients FROM recipes where id in {tuple(hits)}", self.engine)
        q_df['score'] = q_df['id'].map(hits)

        return q_df.sort_values(by="score", ascending=False)

