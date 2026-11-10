from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient
from beanie import init_beanie
from src.Settings import Settings
from typing import List, Optional
from bson import ObjectId
from pydantic import BaseModel, Field
from beanie import Document

settings = Settings()

class Standard(Document):
    doc_key: str
    title: str
    abstract: str
    authors: List[str]
    keywords: List[str]
    nist_page_url: str
    local_pdf_path: str
    publication_date: str
    downloaded: bool

    class Settings:
        name = settings.collection_name

class StandardValidator(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    abstract: str = Field(..., min_length=1, max_length=1000)
    authors: List[str] = Field(..., min_length=1, max_length=100)
    keywords: List[str] = Field(..., min_length=1, max_length=100)
    nist_page_url: str = Field(..., min_length=1, max_length=100)
    local_pdf_path: str = Field(..., min_length=1, max_length=100)
    publication_date: str = Field(..., min_length=1, max_length=100)
    downloaded: bool = Field(..., min_length=1, max_length=100)

@asynccontextmanager
async def lifespan(instance: FastAPI):
    client = AsyncMongoClient(settings.mongodb_uri)

    await init_beanie(
        database=client[settings.db_name],
        document_models=[Standard]
    )

    await settings.load_database_from_json()
    yield
    client.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add this right below your app = FastAPI(lifespan=lifespan) definition
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """
    Interceptors the browser's automatic tab icon requests
    and quietly responds with a 204 No Content to clean up terminal logs.
    """
    return Response(status_code=204)


# =====================================================================
# CRUD Operations
# =====================================================================

# --- CREATE ---
@app.post("/api/items", response_model=Standard, status_code=status.HTTP_201_CREATED)
async def create_item(payload: StandardValidator):
    new_entry = Standard(title=payload.title, abstract=payload.abstract, authors=payload.authors,
                         keywords=payload.keywords)
    await new_entry.insert()
    return new_entry


# --- READ (ALL/SEARCH) ---
@app.get("/api/search", response_model=List[Standard])
async def search_items(q: str = Query(..., min_length=1)):
    search_terms = [word.strip().lower() for word in q.split(",") if word.strip()]

    match_conditions = []

    for word in search_terms:
        match_conditions.extend([
            {"title": {"$regex": word, "$options": "i"}},
            {"abstract": {"$regex": word, "$options": "i"}},
            {"keywords": {"$regex": word, "$options": "i"}},
        ])

    score_additions = []
    for word in search_terms:
        # Title priority check (3 points) - Bulletproofed with $ifNull
        score_additions.append({
            "$cond": [
                {
                    "$regexMatch": {
                        "input": {"$ifNull": ["$title", ""]},
                        "regex": word,
                        "options": "i"
                    }
                },
                3,
                0
            ]
        })

        # Abstract priority check (2 points) - Bulletproofed with $ifNull
        score_additions.append({
            "$cond": [
                {
                    "$regexMatch": {
                        "input": {"$ifNull": ["$abstract", ""]},
                        "regex": word,
                        "options": "i"
                    }
                },
                2,
                0
            ]
        })

        # Keywords array match (1 point) - Bulletproofed with $ifNull
        score_additions.append({
            "$cond": [
                {
                    "$anyElementTrue": {
                        "$map": {
                            "input": {"$ifNull": ["$keywords", []]},
                            "as": "kw",
                            "in": {
                                "$regexMatch": {
                                    "input": {"$ifNull": ["$$kw", ""]},
                                    "regex": word,
                                    "options": "i"
                                }
                            }
                        }
                    }
                },
                1,
                0
            ]
        })

    pipeline = [
        {"$match": {"$or": match_conditions}},
        {
            "$addFields": {
                "search_score": {"$add": score_additions}
            }
        },
        {"$sort": {"search_score": -1}},
    ]


    return await Standard.aggregate(pipeline).to_list()


# --- READ (SINGLE) ---
@app.get("/api/items/{item_id}", response_model=Standard)
async def get_item(item_id: str):
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=404, detail="Invalid ID format")

    # Active record style fetch by primary ID key
    item = await Standard.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


# --- UPDATE ---
@app.put("/api/items/{item_id}", response_model=Standard)
async def update_item(item_id: str, payload: StandardValidator):
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=404, detail="Invalid ID format")


@app.delete("/api/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: str):
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=404, detail="Invalid ID format")
    item = await Standard.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    await item.delete()
    return None
