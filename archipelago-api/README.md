# Archipelago Wikibase API

A REST API in front of the Archipelago Wikibase SPARQL endpoint
(`archipelago-wikibase.wikibase.cloud`). Serves items and collections as
clean JSON — no SPARQL knowledge required by callers.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | API info |
| GET | `/stats` | Total items/collections, breakdown by AN Project |
| GET | `/items` | List items, with filters (`collection`, `creator`, `place`, `an_project`, `digital_type`) and pagination (`limit`, `offset`) |
| GET | `/items/{qid}` | Full detail for one item, e.g. `/items/Q351` |
| GET | `/collections` | List all collections with item counts |
| GET | `/collections/{qid}` | Collection detail + all its items |
| GET | `/search?q=...` | Free-text search over item labels |

All endpoints accept `?lang=el` or `?lang=en` (default `el`) to choose the
label/description language returned.

Interactive docs (Swagger UI) are auto-generated at `/docs` once running.

## Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open:
- http://localhost:8000/docs — interactive API explorer
- http://localhost:8000/stats — quick sanity check
- http://localhost:8000/items?collection=Q3&limit=5

## Run with Docker

```bash
docker build -t archipelago-api .
docker run -p 8000:8000 archipelago-api
```

## Deploy to the cloud (free tier options)

### Render.com (recommended, simplest)
1. Push this folder to a GitHub repo (or a subfolder of your existing
   `archipelago` repo — set Render's "Root Directory" to that subfolder).
2. On [render.com](https://render.com): **New → Web Service** → connect
   the repo.
3. Render auto-detects the `Dockerfile`. Leave build/start commands blank
   (the Dockerfile's `CMD` handles it).
4. Deploy. You'll get a public URL like `https://archipelago-api.onrender.com`.

Free tier note: the service sleeps after ~15 minutes of inactivity and
takes a few seconds to wake on the next request — fine for a demo/thesis
project, not for production traffic.

### Railway.app (alternative)
1. `railway login`
2. `railway init` inside this folder
3. `railway up` — it detects the Dockerfile automatically.
4. `railway domain` to get a public URL.

### Fly.io (alternative)
```bash
fly launch    # detects the Dockerfile, asks a few questions
fly deploy
```

## Example requests

```bash
# All collections with counts
curl https://your-api-url/collections

# Items from the Hozoviotissa collection (Q3), English labels
curl "https://your-api-url/items?collection=Q3&lang=en&limit=10"

# Single item detail
curl https://your-api-url/items/Q351

# Search
curl "https://your-api-url/search?q=καΐκι"

# Only video items from the mining project
curl "https://your-api-url/items?digital_type=Βίντεο&an_project=Εξόρυξη%20στις%20Κυκλάδες:%20Ψηφιακά%20Ίχνη"
```

## Notes on the data model

Property IDs are mapped to friendly JSON keys in `sparql_client.py`
(`PROPS` dict) — keep that in sync with `property_map.json` in the main
repo if the Wikibase schema changes. Current mapping:

- `creator` (P2), `date` (P3), `place` (P4), `collection` (P5),
  `keywords` (P6), `color` (P7), `collection_method` (P8),
  `registration_date` (P9), `documenter` (P10), `notes` (P11),
  `an_project` (P12), `same_as` (P13), `identifier` (P14),
  `source_url` (P15), `digital_object_type` (P16)
