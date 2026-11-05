# PropTrace UK

**Spatial Decision Support System for UK residential property risk screening.**

MSc Computer Science dissertation project — University of Birmingham.

> **Naming note.** The product name is **PropTrace UK**. The database and some paths still use `proptrace_msc` / LegacyTrace from earlier working titles. They refer to the same system.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-black.svg)](https://flask.palletsprojects.com/)
[![PostGIS](https://img.shields.io/badge/PostGIS-3.3+-green.svg)](https://postgis.net/)

---

## What it does

PropTrace UK consolidates fragmented UK open property data into one interactive map so a non-specialist can screen residential stock for:

- **Legal risk** — HM Land Registry restrictive covenants  
- **Environmental risk** — Environment Agency Flood Zone 3  
- **Structural / energy risk** — EPC bands and VOA dwelling-age eras (via CDRC)

A two-stage **Composite Property Suitability Index (CPSI)** applies a non-compensatory gate (covenant / flood) before a weighted linear combination for tradeable factors.

**Scale of the delivered warehouse:** 624,394 property records · 346,823 cadastral polygons · Birmingham / West Midlands test region.

---

## Live demo

<!-- Replace this URL once you deploy (see Hosting below) -->
**Live app:** _coming soon — add your Render / Railway URL here_

Until the live URL is live, employers can:

1. Clone and run locally (below), or  
2. Ask for a short walkthrough / screen recording of the evaluation build.

---

## Architecture

| Tier | Stack |
|------|--------|
| Presentation | Mapbox GL JS (`templates/index.html`) |
| Application | Flask REST API (`app.py`) — Route 1 postcode lookup, Route 2 spatial viewport |
| Data | PostgreSQL + PostGIS — schemas `staging` → `geo` → `core` |

```
Browser (Mapbox)  →  Flask API  →  PostGIS (core.birmingham_properties_master)
```

---

## Repository contents

| Path | Purpose |
|------|---------|
| `app.py` | Flask API + CPSI scoring engine |
| `templates/index.html` | Interactive map UI |
| `src/` | ETL ingestion scripts (HMLR, ONS NSUL, CDRC EPC/VOA, postcode bridge) |
| `ingest_flood.py` | Environment Agency flood-zone ingestion |
| `sensitivity_analysis.py`, `test_gate_logic.py` | Evaluation / gate-logic utilities |
| `requirements.txt` | Python dependencies |
| `docs/` | Dissertation chapters, design notes, figures |

**Raw multi-GB CSV/GML source files are not in this repo** (gitignored). They must be obtained from the official open-data portals / CDRC and placed locally before running ingestion.

---

## Prerequisites

- Python 3.10+
- PostgreSQL with **PostGIS 3.3+**
- [Mapbox](https://account.mapbox.com/) public access token (free tier is fine)
- Optional for production deploy: `gunicorn`

---

## Local setup

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/PropTrace_UK.git
cd PropTrace_UK

python -m venv venv
# Windows
.\venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Database

```sql
CREATE DATABASE proptrace_msc;
\c proptrace_msc
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS geo;
CREATE SCHEMA IF NOT EXISTS core;
```

### 3. Environment

```bash
cp .env.example .env
```

Edit `.env` with your Postgres credentials and Mapbox token.

### 4. Ingest data (first-time only)

Place source files under `data/` (or paths expected by each script), then run from the project root / `src/` as appropriate:

```bash
# Examples — adjust paths to match your local layout
python src/ingest_polygons.py      # HMLR cadastral GML → geo.birmingham_polygons
python src/ingest_nsul.py          # ONS NSUL → address spine
python src/ingest_covenants.py     # HMLR covenants
python ingest_flood.py             # EA flood zones
python src/ingest_new_layers.py    # CDRC EPC + VOA dwelling age
python src/ingest_geo_bridge.py    # postcodes.io → LSOA bridge
```

Then run your SQL ETL that builds `core.birmingham_properties_master` (denormalised production table used by the API).

### 5. Run the app

```bash
python app.py
```

Open **http://localhost:5000**

---

## Hosting for employers (recommended path)

This is **not** a static GitHub Pages site. It needs a **Python web process** plus a **PostGIS database**.

### Practical recommendation

| Piece | Suggested host | Why |
|-------|----------------|-----|
| Flask API + UI | [Render](https://render.com) or [Railway](https://railway.app) | GitHub auto-deploy, HTTPS, free/cheap tiers |
| PostGIS | [Neon](https://neon.tech) (enable `postgis`) or Railway PostGIS template | Managed Postgres with spatial extensions |
| Map | Mapbox (already in frontend) | Restrict the token to your live domain |

**Important storage note:** the full Birmingham warehouse (hundreds of thousands of polygons + attributes) is **too large for most free DB tiers** (~0.5–1 GB). For a public portfolio demo, use either:

1. **A spatial subset** (e.g. one Birmingham AOI / ~5–20k parcels) exported from your local DB, **or**  
2. A small paid PostGIS plan (~£3–10/month) if you want the full region online.

### Deploy steps (Render + Neon outline)

1. Push this repo to a **public** GitHub repository.  
2. Create a Neon project → SQL: `CREATE EXTENSION postgis;` → create `staging` / `geo` / `core` → restore a **demo dump** (`pg_dump` / `pg_restore` of your subset).  
3. On Render: **New Web Service** → connect the GitHub repo.  
   - Build: `pip install -r requirements.txt gunicorn`  
   - Start: `gunicorn app:app --bind 0.0.0.0:$PORT`  
4. Set environment variables on Render to match Neon (`DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`) and any Mapbox settings.  
5. Paste the public HTTPS URL into the **Live demo** section above.

### Quick interview fallback (no permanent host)

```bash
# With the app running locally:
npx localtunnel --port 5000
# or: cloudflared tunnel --url http://localhost:5000
```

Share the temporary URL for a live call. Prefer a permanent deploy for the README link.

### Before you make the repo public

- [ ] Confirm `.env` is **not** committed (it is gitignored).  
- [ ] In Mapbox → token settings → **URL restrict** to `localhost` + your Render/Railway domain.  
- [ ] Prefer injecting the Mapbox token via env/template rather than leaving a long-lived unrestricted `pk.` key in `templates/index.html`.  
- [ ] Do **not** commit raw CSV/GML data or database dumps containing personal identifiers beyond what open data already publishes.

---

## API sketch

| Route | Role |
|-------|------|
| `GET /` | Map UI |
| `GET /api/properties/<postcode>` | Tabular attributes + CPSI score |
| `GET /api/spatial/parcels` | Viewport GeoJSON (bbox safety cap) |

---

## Dissertation / evaluation

Computational checks and user evaluation artefacts live under `docs/dissertation/` and the sensitivity scripts in the repo root. The scoring model’s gate independence was verified computationally on production data; see the dissertation for methods and results.

---

## Licence / data attribution

Application code: © Tayab Belbina — University of Birmingham MSc project.

Underlying open data remains copyright of the respective publishers (HM Land Registry, Ordnance Survey / ONS, Environment Agency, DLUHC EPC register / VOA dwelling statistics via CDRC). Redistribution of raw source files is subject to those licences — this repo ships **code**, not the bulk downloads.
