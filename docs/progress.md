Project Development & Progress Log
Student: Tayab (txb527) (3046927)

Project: Master's Dissertation (Computer Science Conversion)

University: University of Birmingham

Log Entry: 26/06/2026 — Second Supervisor Meeting & Strategic Alignment
During the second formal project review meeting, my supervisor and I discussed the core direction of the application. The project was initially focused on building a compliance application for evaluating restrictive covenants. During our conversation, my supervisor suggested considering a couple of additional features.

The Pivot: Reflecting on those feature suggestions after the meeting, I realized that instead of keeping the application strictly limited to a document viewer for legal text, I could significantly expand the scope to make it much more comprehensive. I decided to pivot the architecture into a multi-layered investment risk application designed to evaluate a property's long-term viability from multiple angles. By combining her ideas with my own framework, I have designed a data core structured around six distinct datasets to capture physical, financial, and legal risk vectors:

HM Land Registry Price Paid Data (PPD): Providing historical transaction timelines since 1995 to evaluate asset trends and map sales dates against legal restriction timestamps.

HM Land Registry INSPIRE Index Polygons: Providing precise, vector-based cadastral boundaries to convert geographic map points into active, interactive spatial fences.

Ordnance Survey UPRN Dataset: Serving as the master relational anchor across my schemas to completely eliminate the risk of text-based address mismatching.

HM Land Registry Restrictive Covenant Data: Providing the raw, unstructured textual deeds that my LLM pipeline parses to detect structural or usage limitations.

Domestic Energy Performance Certificates (EPC) Bulk Data: Introducing live asset energy ratings to layer physical compliance risks directly over our land boundaries.

CDRC Council Tax Bandings Dataset: Providing localized residential tax bands to analyze financial holding outlays and economic risk.

I plan to present this expanded, comprehensive vision to my supervisor in our next meeting to get her feedback on the multi-variable risk approach.

Comprehensive Investment Risk Framework & Expanded Scope
Following my decision to expand the application into a comprehensive investment risk utility application, I have moved away from a basic legal compliance checker to an integrated multi-source analytical platform. The application evaluates a property's viability across three distinct risk vectors, combining macro-level structural indicators with micro-level legal data.

The Combined Property Suitability Index (CPSI)
To give users a cohesive understanding of asset risk, the application calculates a weighted, algorithmic risk score between 0.0 and 1.0. This score is built across three core risk layers:

Legal Compliance Layer (40% Weight): The backend utilizes a Large Language Model automated via prompt engineering to scan the unstructured title deeds. If an absolute restriction on structural modifications, extensions, or commercial usage is detected, a high-risk flag (1.0) is triggered.

Environmental & Climate Risk Layer (30% Weight): Sourced from the Domestic EPC data archive. Properties holding an E, F, or G efficiency rating trigger a maximum risk score (1.0) due to the UK's strict Minimum Energy Efficiency Standards (MEES), which impose heavy leasing penalties and operational friction.

Economic & Structural Risk Layer (30% Weight): Sourced from the VOA building era and Council Tax datasets. An ancient building classification (pre-1900) paired with a high Council Tax Band (F, G, or H) indicates an asset with extreme potential retrofit overheads and high fixed holding costs while it sits vacant during development.

Interactive Geospatial Visualizations
The frontend mapping layer will translate these backend mathematical risk scores into a highly visual, sub-meter granular interface:

High Risk (Score ≥ 0.75): Rendered as a Red map vector. This indicates an asset with an active structural legal restriction combined with severe environmental non-compliance (e.g., a Victorian era building holding an alteration ban and an EPC F rating).

Medium Risk (Score 0.40 – 0.74): Rendered as an Amber map vector. This signals conditional covenants or mid-tier efficiency brackets (EPC D) requiring targeted surveyor inspection.

Low Risk (Score < 0.40): Rendered as a Green map vector. This represents modern, high-efficiency properties entirely free from restrictive title legalese.

When an asset parcel is selected, an interactive analytical sidebar dashboard dynamically slides open to display explicit checkmarks for the legal constraints, the building era, historical transaction trends, and ongoing financial tax outlays.

Log Entry: 28/06/2026 — Database Engineering & Pipeline Obstacles
This session was spent setting up my local PostgreSQL database and integrating the PostGIS extension to handle geospatial mapping data. While attempting to build out the master property core (core.birmingham_properties_master), I hit significant type safety and relational data alignment issues:

The UPRN BigInt Restriction: I originally tried to prepend an alphanumeric template string ('PROP-') to rows in my staging queries. This threw a severe type mismatch error because the database schema strictly locks the UPRN field to a numeric bigint data type. I resolved this by discarding the string parsing completely and mapping the column directly to an auto-incrementing database sequence (currval), preserving pure numeric integrity.

The Aggregate Window Clause Error: When attempting to update master properties with raw EPC strings, PostgreSQL rejected my query with a GROUP BY error because the staging dataset lacked explicit inspection timestamps to sort by. I solved this by refactoring my window function query to use a blank ordering directive: ORDER BY (SELECT NULL), forcing Postgres to safely isolate the primary matching record per postcode string.

The Neighborhood Bridge Challenge: While joining the VOA construction eras and Council Tax bands to my master table, I realized that the raw VOA metrics are aggregated strictly by ONS LSOA codes, while my core table maps individual property addresses via postcodes. To bridge this without a static map file, I wrote a custom batch-processing Python script (ingest_geo_bridge.py) leveraging the postcodes.io API. By querying the API in optimized batches of 100, I mapped all 18,824 unique local postcodes directly to their official LSOA identifiers without hitting connection timeouts, creating a clean spatial bridge table (geo.postcode_lsoa_bridge) that completed our backend data warehouse.

Log Entry: 02/07/2026 — Backend API Construction & Repository Initialization
Today, I shifted gears from database ingestion to backend web architecture. I built out the application data layer to expose our newly enriched database grid to the web.

Flask API Layer Configuration: I established an isolated virtual environment (venv) and deployed a Flask application powered by Flask-SQLAlchemy. I wrote a dedicated object class (BirminghamProperty) that mirrors our production database schema.

Endpoint Delivery: I designed and verified a clean GET route at /api/properties/<postcode>. The endpoint accepts incoming user requests, normalizes uppercase strings, strips spacing anomalies, queries the PostgreSQL data layers, and returns a fully unified asset profile (UPRN, EPC rating, building era, and tax band) as an asynchronous JSON payload.

GitLab Deployment: I successfully initialized Git in my project root, generated a secure Personal Access Token via the university portal, and pushed my active codebase up to the server. This establishes my baseline code velocity and log history for tracking.

Log Entry: 09/07/2026 — Advanced PostGIS Integration, Optimization & Workspace Refactoring
Following the initialization of my Flask API layer, this week's engineering block was dedicated to constructing the spatial processing core of the application, securing backend configurations, and establishing a rigorous data governance framework on Google Drive to maintain a strict, auditable data lineage.

1. Structural Refactoring & Data Governance Framework
To align the project with institutional data governance standards and ensure readiness for the academic audit trail, I refactored the remote cloud storage workspace (M.Sc dissertation) into a numbered, chronological hierarchy clamped to a strict maximum depth of 2 layers:

01_Administrative_&_Timeline/ – Houses active project management templates and structural overviews.

02_Datasets_&_Raw_Sources/ – Serves as the immutable repository for original public registry data assets.

03_System_Architecture_Blueprints/ – Contains technical specifications, tech stack design rationales, and feature plans.

04_Code_Mastery_&_Inspection_Prep/ – Dedicated space for line-by-line codebase analysis, execution flow traces, and viva mock defenses.

05_Thesis_&_Progress_Logs/ – Chronological progress tracking archives, supervisor briefing logs, and active thesis drafts.

2. Immutable Data Lineage Ingestion
I completed the acquisition and cloud archiving of authoritative, raw data assets directly inside the 02_Datasets_&_Raw_Sources/ directory. This preserves an unedited, auditable trail of the original structures before ingestion into PostgreSQL:

Land_Registry_Cadastral_Parcels.gml & .gfs sidecar metadata (HM Land Registry) – The underlying XML spatial foundation vectors for Birmingham parcel coordinates.

pp-complete.csv (HM Land Registry) – Complete transactional Price Paid records since 1995 for historical macro tracking.

birmingham_covenants.csv (HMLR Open Data) – Unstructured legal deed text profiles.

birmingham_uprns.csv (Ordnance Survey) – Master identification keys serving as the relational anchor to bridge text tables with spatial boundaries.

EPC_RATINGS.CSV, dwellingages.csv, and variable_dictionary_dwelling.csv (DLUHC Open Data Communities) – Alphanumeric micro-level physical risk and environmental profile metrics.

3. Refactoring Route 1 (Postcode Engine) & Exception Handling
I updated Route 1 (/api/properties/<postcode>) to adhere to strict RESTful architectural constraints.

Defensive Engineering Guardrails: Refactored the core text processing to strip all whitespace and transform the string to uppercase before applying an immutable negative index slice (f"{clean_postcode[:-3]} {clean_postcode[-3:]}"). This systematically normalizes chaotic user input to perfectly align with Royal Mail database keys, preventing silent query execution lookup failures.

Semantic HTTP Protocol Selection: Enforced a strict conditional boundary: if a query yields an empty collection or returns a valid postcode that lacks active risk parameters, the API short-circuits and issues a 404 Not Found status. This avoids returning a 200 OK with an empty data payload, protecting frontend client rendering engines from trying to interpret null maps.

4. Route 2 Architectural Implementation (Spatial Viewport Engine)
I designed and deployed the core geospatial endpoint at /api/spatial/parcels to serve vector streams dynamically to the client interface.

# Spatial Viewport Boundary Processing Snippet
bbox_envelope_4326 = ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326)
bbox_area_meters = db.session.query(ST_Area(ST_Transform(bbox_envelope_4326, 27700))).scalar()

# Performance safety trigger: Reject queries if the viewport area is too massive
if bbox_area_meters > 5000000:  # 5 square kilometers
    return jsonify({
        "status": "warning",
        "message": "Viewport area too massive. Please zoom in further.",
        "area_sqm": bbox_area_meters
    }), 200

# Optimized spatial join intersection query
query_results = db.session.query(
    BirminghamGeometry.inspireid,
    ST_AsGeoJSON(ST_Transform(BirminghamGeometry.geometry, 4326)).label('geojson_geom')
).filter(
    ST_Intersects(BirminghamGeometry.geometry, ST_Transform(bbox_envelope_4326, 27700))
).limit(150).all()

Coordinate System Projections (SRID 4326 ⇄ 27700): The route captures four coordinate points from the browser viewport, constructs a bounding box tracking envelope using global degrees (SRID 4326), and instantly maps it using ST_Transform into flat SRID 27700 (British National Grid meters) to calculate exact real-world surface parameters.

Memory Safeguard Constraint: To prevent server thread resource exhaustion or browser rendering lag when zoomed out to macro scales, I engineered a short-circuit performance gate. If the screen envelope area bounds exceed 5 square kilometers, the query halts execution immediately and issues a warning payload.

Relational Spatial Joins & GeoJSON Serialization: For safe scales, the engine executes a multi-schema join matching the database geometry schema layer to the core text table attributes via the UPRN anchor (BirminghamProperty.uprn == BirminghamGeometry.inspireid). It queries the table using an ST_Intersects condition filter and wraps the returned spatial boundaries inside an inline ST_AsGeoJSON compiler, outputting an industry-standard, fully serialized GeoJSON FeatureCollection capped at .limit(150) for rendering stability.

Log Entry: 14/07/2026 — Algorithmic Core Execution, Type-Safety Debugging & Multi-Source Validation

Today, I transitioned the backend from a purely passive spatial query layer into an active Multi-Criteria Decision Analysis (MCDA) framework by deploying the core scoring rules for the Composite Property Suitability Index (CPSI).

1. Two-Stage Computational Scoring Pipeline
Grounded in Jacek Malczewski's (2006) warnings regarding standard Weighted Linear Combination (WLC) compensatory flaws—where excellent attributes dangerously obscure catastrophic risks—I engineered a strict, two-stage computation helper function (`calculate_cpsi_score`):
- Stage 1 (Non-Compensatory Gate): Implements a strict structural circuit breaker. If an asset matches severe risk conditions (e.g., long leaseholds paired with luxury high-holding-cost Council Tax Bands G or H), the system short-circuits, completely bypasses the additive algebra, and locks the risk score at a ceiling of 1.00 (Red status).
- Stage 2 (Compensatory WLC Matrix): If an asset clears the binary gate, it enters a standard additive model base. The engine parses categorical attributes (EPC alphanumeric bands, building eras) and normalizes them into continuous risk sub-scores across Legal (40%), Environmental (30%), and Economic (30%) layers before computing the final composite floating-point risk index.

2. Debugging Scope Parameters & Parameter Alignment
During the initialization of Route 1 (`/api/properties/<postcode>`), I encountered and resolved a significant scoping type-error during active compilation. An initial routing layout accidentally duplicated the `env_w` variable string and mapped the raw, un-hashed database configuration string (`db_password`) directly into the mathematical calculation function array where the economic weight float variable (`econ_w`) belonged. This would have triggered an unhandled type-safety breakdown upon runtime execution during multiplication tasks. I refactored the parameter grid, successfully mapping `econ_w` to its individual client request target and ensuring type-safe floating-point inputs.

3. Relational Verification of One-to-Many Postcode Spatial Densities
Upon execution testing of Route 1 against local test postcodes (e.g., B11 1AA), the API successfully returned multiple records within a single JSON collection payload. While a baseline visual inspection could mistake this for query duplication, a deep relational schema trace verified that the database engine handles a strict, accurate one-to-many relationship (One Postcode cluster -> Multiple UPRN asset nodes). The master table cleanly isolates independent properties via unique BigInt Ordnance Survey UPRNs. The identical residual CPSI scores (0.21, Green tier) reflect matching physical staging matrices (EPC D, Tax Band A, Freehold tenure) logged across those distinct structural assets.

4. Repository Deployment Velocity
To maintain compliance with the department's active version-history framework, I initialized a comprehensive git pipeline tracking checkpoint updates for 'app.py' and 'REQUIREMENTS.md'.