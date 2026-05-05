import pytest


@pytest.fixture
def sample_recipe_payload():
    return {
        "name": "Tomato Soup",
        "preparation_time": 10,
        "cooking_time": 25,
        "category": ["Soup"],
        "ingredients": ["tomato", "onion", "garlic"],
        "ingredients_raw": ["4 tomatoes", "1 onion", "2 cloves garlic"],
        "instructions": "Cook vegetables, blend, and serve.",
        "cooking_methods": ["simmer", "blend"],
        "implements": ["pot", "blender"],
        "nutrition": {"calories": 220},
        "cuisine": "European",
        "number_of_steps": 3,
        "url": "https://example.com/tomato-soup",
    }
