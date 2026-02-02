import json
import pandas as pd
from sqlalchemy import text


def extract_ner(ingredient_text, engine):
    product_set = pd.read_sql_query(text("select product_name from products"), engine)['product_name']
    matches = []
    ingredient_text = ingredient_text.replace("[", "").replace("]", "").replace('"', "").replace(",","")
    ingredient_list = ingredient_text.split(" ")

    for product in product_set:
        if product in ingredient_list:
            matches.append(product)

    return json.dumps(matches)





