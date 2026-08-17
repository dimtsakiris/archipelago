"""
Archipelago Wikibase REST API
==============================
A REST wrapper around the Archipelago Wikibase SPARQL endpoint, giving
clean JSON access to items and collections without callers needing to
know any SPARQL.

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --reload

Then open http://localhost:8000/docs for interactive Swagger UI.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from sparql_client import (
    get_item,
    list_items,
    list_collections,
    get_collection,
    search_items,
    get_stats,
)

app = FastAPI(
    title="Archipelago Wikibase API",
    description=(
        "REST API over the Archipelago Wikibase instance "
        "(archipelago-wikibase.wikibase.cloud). Serves the Digital Cyclades "
        "fishing-heritage collection (Amorgos) and the Mining in the "
        "Cyclades: Digital Traces collection, as clean JSON."
    ),
    version="1.0.0",
)

# Allow browser-based clients (e.g. a future frontend) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/", tags=["meta"])
def root():
    return {
        "name": "Archipelago Wikibase API",
        "docs": "/docs",
        "endpoints": [
            "/items", "/items/{qid}", "/collections", "/collections/{qid}",
            "/search", "/stats",
        ],
    }


@app.get("/stats", tags=["meta"])
async def stats():
    """Summary counts: total items, total collections, breakdown by AN project."""
    return await get_stats()


@app.get("/items", tags=["items"])
async def items(
    lang: str = Query("el", pattern="^(el|en)$", description="Label/description language"),
    collection: Optional[str] = Query(None, description="Filter by collection Q-ID, e.g. Q3"),
    creator: Optional[str] = Query(None, description="Filter by creator (exact match)"),
    place: Optional[str] = Query(None, description="Filter by place (exact match)"),
    an_project: Optional[str] = Query(None, description="Filter by AN Project name (exact match)"),
    digital_type: Optional[str] = Query(None, description="Filter by digital object type, e.g. 'Εικόνα', 'Βίντεο'"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List items, with optional filters. Paginated."""
    return await list_items(
        lang=lang, collection=collection, creator=creator, place=place,
        an_project=an_project, digital_type=digital_type,
        limit=limit, offset=offset,
    )


@app.get("/items/{qid}", tags=["items"])
async def item_detail(qid: str, lang: str = Query("el", pattern="^(el|en)$")):
    """Full detail for a single item by Q-ID (e.g. Q351)."""
    result = await get_item(qid, lang=lang)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Item {qid} not found")
    return result


@app.get("/collections", tags=["collections"])
async def collections(lang: str = Query("el", pattern="^(el|en)$")):
    """List all collections with their item counts."""
    return await list_collections(lang=lang)


@app.get("/collections/{qid}", tags=["collections"])
async def collection_detail(qid: str, lang: str = Query("el", pattern="^(el|en)$")):
    """Collection detail plus all its items."""
    result = await get_collection(qid, lang=lang)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Collection {qid} not found")
    return result


@app.get("/search", tags=["items"])
async def search(
    q: str = Query(..., min_length=2, description="Free-text search across labels"),
    lang: str = Query("el", pattern="^(el|en)$"),
    limit: int = Query(50, ge=1, le=500),
):
    """Free-text search over item labels."""
    return await search_items(q, lang=lang, limit=limit)
