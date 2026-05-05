from recommender_engine.recommender_engine import RecommenderEngine


class FakeVector:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class FakeModel:
    def encode(self, text, normalize_embeddings=True):
        return FakeVector([0.1, 0.2, 0.3])


class FakeQdrantClient:
    def __init__(self):
        self.upserts = []
        self.deletes = []

    def upsert(self, collection_name, points):
        self.upserts.append((collection_name, points))

    def delete(self, collection_name, points_selector):
        self.deletes.append((collection_name, points_selector))


def make_engine():
    engine = object.__new__(RecommenderEngine)
    engine.model = FakeModel()
    engine.qd_client = FakeQdrantClient()
    engine.recipe_repository = object()
    engine.recipes_collection = "ingredients"
    engine.names_collection = "names"
    engine.ingredients_list = ["tomato", "tomatillo", "onion", "green onion"]
    return engine


def test_upsert_embedding_writes_ingredient_and_name_vectors(sample_recipe_payload):
    engine = make_engine()

    engine.upsert_embedding(10, sample_recipe_payload)

    assert [call[0] for call in engine.qd_client.upserts] == ["ingredients", "names"]
    ingredient_point = engine.qd_client.upserts[0][1][0]
    name_point = engine.qd_client.upserts[1][1][0]
    assert ingredient_point.id == 10
    assert ingredient_point.payload["ID"] == 10
    assert name_point.payload["ingredients"] == ["tomato", "onion", "garlic"]


def test_remove_recipe_from_indexes_deletes_from_both_collections():
    engine = make_engine()

    engine.remove_recipe_from_indexes(10)

    assert [call[0] for call in engine.qd_client.deletes] == ["ingredients", "names"]


def test_get_suggestions_prioritizes_close_matches():
    engine = make_engine()

    suggestions = engine.get_suggestions("tom", limit=2)

    assert suggestions[0] == "tomato"
    assert len(suggestions) == 2
