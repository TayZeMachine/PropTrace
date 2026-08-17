## How to recreate the spatial decision support system by student 3049627

---

## System Requirements & Prerequisites

Ensure the following runtimes and tools are installed on your host system:

## Python: 3.10 or higher
## PostgreSQL: PostGIS 3.3+ spatial extension enabled
## GDAL / GEOS / PROJ: Installed and added to system PATH (required for GeoPandas, Shapely, and GeoAlchemy2 spatial operations)
## Mapbox Public Access Token: Required for client-side WebGL vector map rendering

---

## Quick-Start Setup Guide

### 1. Clone Repository & Setup Virtual Environment

# Clone the repository
git clone https://git.cs.bham.ac.uk/projects-2025-26/txb527 
cd LegacyTrace-UK

# Create and activate Python virtual environment
python -m venv venv

# On macOS/Linux:
source venv/bin/activate
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
2. Install Python DependenciesBashpip install --upgrade pip
pip install -r requirements.txt
# Database Setup & Initialization (PostgreSQL / PostGIS)1. Initialize Database & SchemasOpen a terminal with psql or use your preferred SQL client (e.g., pgAdmin, DataGrip) to create the database and establish the three-schema architectural isolation:SQLCREATE DATABASE proptrace_msc;
\c proptrace_msc;

2. Configure Environment Variables (.env)Create a .env file in the root directory:Bashcp .env.example .env
Set your local database credentials and Mapbox token in .env:Ini, TOMLFLASK_APP=app.py
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=your_generated_secret_key_here

# PostgreSQL / PostGIS connection URI
DATABASE_URL=postgresql://postgres:password@localhost:5432/proptrace_msc

# Mapbox GL JS Public Token
MAPBOX_ACCESS_TOKEN=pk.eyJ1IjoieW91ci11c2VybmFtZSIsImEiOiJ5b3VyLXRva2VuIn0...
Data Pipeline & ETL IngestionExecute the data ingestion pipelines in order to populate the staging, geo, and core tables:Bash# 1. Ingest Master Postcode-LSOA Bridge & UPRN coordinates
python -m scripts.ingest_postcode_bridge

# 2. Ingest Ordnance Survey Cadastral INSPIRE Polygons (geo schema)
python -m scripts.ingest_polygons

# 3. Ingest Environment Agency Flood Zone 2 & 3 Vector Polygons
python -m scripts.ingest_flood

# 4. Ingest Title Deed Restrictive Covenants & EPC Certificates (staging schema)
python -m scripts.ingest_covenants
python -m scripts.ingest_epc

# 5. Build Materialized Master Query Table (core schema)
python -m scripts.build_core_master

2. Configure Environment Variables (.env)Create a .env file in the root directory:Bashcp .env.example .env
Set your local database credentials and Mapbox token in .env:Ini, TOMLFLASK_APP=app.py
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=your_generated_secret_key_here

3. Spatial Indexing & Physical Clustering Execute the following spatial optimization queries in PostGIS to ensure O(\log N) bounding box searches and minimize disk I/O seek latency:SQL

-- Enable PostGIS spatial extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Create the three isolated schemas
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS geo;
CREATE SCHEMA IF NOT EXISTS core;



