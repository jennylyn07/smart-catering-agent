import json

NEW_RECIPES = [
  # CHINESE
  {"id":"chn-007","name":"Sweet and Sour Pork","cuisine":"chinese","category":"main",
   "allergens":["soy"],"dietary_flags":[],
   "ingredients":[{"name":"pork","quantity":1.0,"unit":"kg"},{"name":"pineapple","quantity":0.3,"unit":"kg"},
                  {"name":"bell pepper","quantity":0.2,"unit":"kg"},{"name":"vinegar","quantity":0.15,"unit":"L"},
                  {"name":"ketchup","quantity":0.1,"unit":"kg"},{"name":"soy sauce","quantity":0.05,"unit":"L"}]},
  {"id":"chn-008","name":"Mapo Tofu","cuisine":"chinese","category":"main",
   "allergens":["soy"],"dietary_flags":["vegan","halal"],
   "ingredients":[{"name":"tofu","quantity":0.8,"unit":"kg"},{"name":"doubanjiang","quantity":0.05,"unit":"kg"},
                  {"name":"garlic","quantity":0.04,"unit":"kg"},{"name":"ginger","quantity":0.03,"unit":"kg"},
                  {"name":"spring onion","quantity":0.05,"unit":"kg"}]},
  {"id":"chn-009","name":"Hot and Sour Soup","cuisine":"chinese","category":"soup",
   "allergens":["soy","egg"],"dietary_flags":[],
   "ingredients":[{"name":"tofu","quantity":0.3,"unit":"kg"},{"name":"bamboo shoots","quantity":0.15,"unit":"kg"},
                  {"name":"egg","quantity":0.1,"unit":"kg"},{"name":"vinegar","quantity":0.05,"unit":"L"},
                  {"name":"soy sauce","quantity":0.05,"unit":"L"}]},
  {"id":"chn-010","name":"Sauteed Bok Choy","cuisine":"chinese","category":"vegetable",
   "allergens":["soy"],"dietary_flags":["vegan","halal"],
   "ingredients":[{"name":"bok choy","quantity":1.0,"unit":"kg"},{"name":"garlic","quantity":0.05,"unit":"kg"},
                  {"name":"oyster sauce","quantity":0.06,"unit":"L"},{"name":"cooking oil","quantity":0.05,"unit":"L"}]},
  {"id":"chn-011","name":"Pineapple Fried Rice","cuisine":"chinese","category":"rice",
   "allergens":["egg","soy"],"dietary_flags":["halal"],
   "ingredients":[{"name":"rice","quantity":0.5,"unit":"kg"},{"name":"pineapple","quantity":0.3,"unit":"kg"},
                  {"name":"egg","quantity":0.15,"unit":"kg"},{"name":"soy sauce","quantity":0.05,"unit":"L"},
                  {"name":"spring onion","quantity":0.05,"unit":"kg"}]},
  {"id":"chn-012","name":"Almond Jelly with Lychee","cuisine":"chinese","category":"dessert",
   "allergens":["nuts"],"dietary_flags":["vegan","halal"],
   "ingredients":[{"name":"almond milk","quantity":0.5,"unit":"L"},{"name":"agar agar","quantity":0.02,"unit":"kg"},
                  {"name":"lychee","quantity":0.4,"unit":"kg"},{"name":"sugar","quantity":0.1,"unit":"kg"}]},
  {"id":"chn-013","name":"Beef Noodle Soup","cuisine":"chinese","category":"noodles",
   "allergens":["soy","gluten"],"dietary_flags":[],
   "ingredients":[{"name":"beef","quantity":0.8,"unit":"kg"},{"name":"egg noodles","quantity":0.4,"unit":"kg"},
                  {"name":"bok choy","quantity":0.3,"unit":"kg"},{"name":"soy sauce","quantity":0.08,"unit":"L"},
                  {"name":"star anise","quantity":0.005,"unit":"kg"},{"name":"ginger","quantity":0.03,"unit":"kg"}]},
  # WESTERN
  {"id":"wes-008","name":"Grilled Salmon","cuisine":"western","category":"main",
   "allergens":["fish"],"dietary_flags":["no_meat","halal"],
   "ingredients":[{"name":"salmon fillet","quantity":1.2,"unit":"kg"},{"name":"lemon","quantity":0.15,"unit":"kg"},
                  {"name":"butter","quantity":0.08,"unit":"kg"},{"name":"garlic","quantity":0.04,"unit":"kg"},
                  {"name":"dill","quantity":0.01,"unit":"kg"}]},
  {"id":"wes-009","name":"Beef Burger","cuisine":"western","category":"main",
   "allergens":["gluten","egg","dairy"],"dietary_flags":[],
   "ingredients":[{"name":"ground beef","quantity":1.0,"unit":"kg"},{"name":"burger bun","quantity":0.5,"unit":"kg"},
                  {"name":"cheese","quantity":0.2,"unit":"kg"},{"name":"lettuce","quantity":0.1,"unit":"kg"},
                  {"name":"tomato","quantity":0.2,"unit":"kg"}]},
  {"id":"wes-010","name":"Tiramisu","cuisine":"western","category":"dessert",
   "allergens":["dairy","egg","gluten"],"dietary_flags":["vegetarian"],
   "ingredients":[{"name":"mascarpone","quantity":0.5,"unit":"kg"},{"name":"ladyfingers","quantity":0.25,"unit":"kg"},
                  {"name":"egg","quantity":0.2,"unit":"kg"},{"name":"coffee","quantity":0.3,"unit":"L"},
                  {"name":"cocoa powder","quantity":0.03,"unit":"kg"},{"name":"sugar","quantity":0.1,"unit":"kg"}]},
  {"id":"wes-011","name":"Creamy Mushroom Soup","cuisine":"western","category":"soup",
   "allergens":["dairy"],"dietary_flags":["vegetarian"],
   "ingredients":[{"name":"mushroom","quantity":0.6,"unit":"kg"},{"name":"cream","quantity":0.3,"unit":"L"},
                  {"name":"onion","quantity":0.15,"unit":"kg"},{"name":"butter","quantity":0.05,"unit":"kg"},
                  {"name":"thyme","quantity":0.005,"unit":"kg"}]},
  {"id":"wes-012","name":"Mashed Potatoes","cuisine":"western","category":"vegetable",
   "allergens":["dairy"],"dietary_flags":["vegetarian"],
   "ingredients":[{"name":"potato","quantity":1.0,"unit":"kg"},{"name":"butter","quantity":0.1,"unit":"kg"},
                  {"name":"cream","quantity":0.2,"unit":"L"},{"name":"salt","quantity":0.01,"unit":"kg"}]},
  # INTERNATIONAL
  {"id":"int-009","name":"Butter Chicken","cuisine":"international","category":"main",
   "allergens":["dairy"],"dietary_flags":["halal"],
   "ingredients":[{"name":"chicken","quantity":1.0,"unit":"kg"},{"name":"butter","quantity":0.1,"unit":"kg"},
                  {"name":"tomato","quantity":0.5,"unit":"kg"},{"name":"cream","quantity":0.2,"unit":"L"},
                  {"name":"garam masala","quantity":0.02,"unit":"kg"},{"name":"ginger","quantity":0.03,"unit":"kg"}]},
  {"id":"int-010","name":"Beef Bulgogi","cuisine":"international","category":"main",
   "allergens":["soy"],"dietary_flags":[],
   "ingredients":[{"name":"beef","quantity":1.0,"unit":"kg"},{"name":"soy sauce","quantity":0.1,"unit":"L"},
                  {"name":"sesame oil","quantity":0.03,"unit":"L"},{"name":"garlic","quantity":0.05,"unit":"kg"},
                  {"name":"pear","quantity":0.3,"unit":"kg"},{"name":"spring onion","quantity":0.05,"unit":"kg"}]},
  {"id":"int-011","name":"Vegetable Curry","cuisine":"international","category":"main",
   "allergens":["nuts"],"dietary_flags":["vegan","halal","no_meat"],
   "ingredients":[{"name":"potato","quantity":0.5,"unit":"kg"},{"name":"carrot","quantity":0.3,"unit":"kg"},
                  {"name":"coconut milk","quantity":0.4,"unit":"L"},{"name":"curry powder","quantity":0.03,"unit":"kg"},
                  {"name":"onion","quantity":0.2,"unit":"kg"},{"name":"tomato","quantity":0.3,"unit":"kg"}]},
  {"id":"int-012","name":"Grilled Fish Fillet","cuisine":"international","category":"main",
   "allergens":["fish"],"dietary_flags":["no_meat","halal"],
   "ingredients":[{"name":"fish fillet","quantity":1.2,"unit":"kg"},{"name":"lemon","quantity":0.15,"unit":"kg"},
                  {"name":"olive oil","quantity":0.05,"unit":"L"},{"name":"garlic","quantity":0.04,"unit":"kg"},
                  {"name":"parsley","quantity":0.02,"unit":"kg"}]},
  {"id":"int-013","name":"Coleslaw","cuisine":"international","category":"salad",
   "allergens":["egg"],"dietary_flags":["vegetarian","halal"],
   "ingredients":[{"name":"cabbage","quantity":0.5,"unit":"kg"},{"name":"carrot","quantity":0.2,"unit":"kg"},
                  {"name":"mayonnaise","quantity":0.15,"unit":"kg"},{"name":"sugar","quantity":0.03,"unit":"kg"},
                  {"name":"lemon","quantity":0.05,"unit":"kg"}]},
  # FILIPINO (thin categories)
  {"id":"fil-029","name":"Ginisang Sitaw","cuisine":"filipino","category":"vegetable",
   "allergens":["soy"],"dietary_flags":["vegan","halal"],
   "ingredients":[{"name":"string beans","quantity":0.8,"unit":"kg"},{"name":"garlic","quantity":0.05,"unit":"kg"},
                  {"name":"onion","quantity":0.1,"unit":"kg"},{"name":"tomato","quantity":0.2,"unit":"kg"},
                  {"name":"cooking oil","quantity":0.04,"unit":"L"}]},
  {"id":"fil-030","name":"Chicken Binakol","cuisine":"filipino","category":"soup",
   "allergens":[],"dietary_flags":["halal"],
   "ingredients":[{"name":"chicken","quantity":1.0,"unit":"kg"},{"name":"young coconut","quantity":0.5,"unit":"kg"},
                  {"name":"ginger","quantity":0.05,"unit":"kg"},{"name":"lemongrass","quantity":0.05,"unit":"kg"},
                  {"name":"onion","quantity":0.15,"unit":"kg"}]},
]

with open("knowledge_base/recipes.json") as f:
    data = json.load(f)

existing_ids = {r["id"] for r in data["recipes"]}
added = 0
for recipe in NEW_RECIPES:
    if recipe["id"] not in existing_ids:
        data["recipes"].append(recipe)
        added += 1

with open("knowledge_base/recipes.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"Added {added} recipes. Total now: {len(data['recipes'])}")
