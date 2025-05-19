import os
import json
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List
from fastapi.middleware.cors import CORSMiddleware  # Add this import at the top
from typing import Optional
# import json


# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SITE_URL = os.getenv("SITE_URL")
SITE_NAME = os.getenv("SITE_NAME")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "tradnet")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "products")

if not OPENAI_API_KEY:
    raise EnvironmentError("OPENAI_API_KEY environment variable not set!")

# Initialize OpenAI client (new SDK format)
client = OpenAI(api_key=OPENAI_API_KEY)

# Allowed categories
ALLOWED_CATEGORIES = {"sports", "gaming", "mobilephones", "laptops", "earphones", "toys"}

# FastAPI app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Default React development server
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
    expose_headers=["*"]  # Exposes all headers to the client
)

# MongoDB client
mongo_client = AsyncIOMotorClient(MONGODB_URI)
db = mongo_client[DB_NAME]
products_collection = db[COLLECTION_NAME]

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