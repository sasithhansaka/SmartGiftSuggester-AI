
class GiftStoryRequest(BaseModel):
    story: str

def extract_keywords(story: str):
    # Expand this list as needed
    keywords = []
    for word in ["car", "driving", "automotive", "vehicle", "drive", "music", "sport", "game", "phone", "laptop", "earphone", "toy"]:
        if word in story.lower():
            keywords.append(word)
    return keywords

@app.post("/suggest-gift-box")
async def suggest_gift_box(req: GiftStoryRequest):
    # Extract keywords and filter products for relevance
    keywords = extract_keywords(req.story)
    if keywords:
        keyword_query = {"$or": [
            {"tags": {"$in": keywords}},
            {"description": {"$regex": "|".join(keywords), "$options": "i"}}
        ]}
        cursor = products_collection.find(keyword_query).limit(50)
    else:
        cursor = products_collection.find({}).limit(50)

    candidates = []
    async for p in cursor:
        candidates.append({
            "_id": str(p["_id"]),
            "name": p.get("short_title") or p.get("name"),
            "description": p.get("description"),
            "category": p.get("category"),
            "price": p.get("price"),
            "tags": p.get("tags", []),
        })

    if not candidates:
        return {"answer": "Sorry, there are no suitable products for your gift box on our site."}

    prompt = f"""
You are an advanced AI gift assistant for an e-commerce site.

A user will describe, in natural language, the gift box they want (including details like the recipient, occasion, budget, recipient's interests, style, and any other important preferences).
If the user's request is NOT related to suggesting a gift or a gift box, reply with: "I'm here to suggest only gift items." and nothing else.
Your tasks:
- Carefully read the user's story and understand their needs: recipient, occasion, preferences, interests, style, and budget.
- ONLY select products from the product catalog that are clearly, directly relevant to the interests or preferences stated by the user (e.g., for 'car driving', only car/driving/automotive items).
- For every product you suggest, include a short explanation in a "reason" field describing exactly why you picked it for this user and story.
- Never suggest generic, unrelated, or only partially relevant products.
- Do NOT suggest any products that are not in the product catalog provided.
- The total price of all chosen products MUST NOT exceed the user's budget.
- If you cannot find any products that fully match the user's needs, reply exactly with: "Sorry, there are no suitable products for your gift box on our site."

Your response should be a JSON list where each item is an object with "_id", "name", and "reason" fields, for example:
[
  {{"_id": "...", "name": "...", "reason": "..."}},
  ...
]

Here is the user's request:
{req.story}

Here is the product catalog:
{json.dumps(candidates, ensure_ascii=False)}
"""

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "You are an expert at picking thoughtful gift combinations. Pick only from the provided product catalog."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=800,
    )
    answer = response.choices[0].message.content.strip()
    try:
        if answer.startswith("Sorry"):
            return {"answer": answer}
        gift_suggestions = json.loads(answer)
        return {"suggestions": gift_suggestions}
    except Exception:
        return {"answer": answer}