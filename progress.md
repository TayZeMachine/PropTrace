# Project Development & Progress Log
**Student:** Tayab (txb527) (3046927) 
**Project:** Master's Dissertation (Computer Science Conversion)  
**University:** University of Birmingham  



  Project Timeline & Development Logs

 Log Entry: 26/06/2026 — Second Supervisor Meeting & Strategic Alignment
During my second formal project review meeting, my supervisor and I discussed the core direction of the application. The project was initially focused on building a compliance application for evaluating restrictive covenants. During our conversation, my supervisor suggested considering a couple of additional features. 

The Pivot: Reflecting on those feature suggestions after the meeting, I realized that instead of keeping the application strictly limited to a document viewer for legal text, I could significantly expand the scope to make it much more comprehensive. I decided to pivot the architecture into a multi-layered investment risk application designed to evaluate a property's long-term viability from multiple angles. By combining her ideas with my own framework, I have designed a data core structured around six distinct datasets to capture physical, financial, and legal risk vectors:

1. HM Land Registry Price Paid Data (PPD): Providing historical transaction timelines since 1995 to evaluate asset trends and map sales dates against legal restriction timestamps.

2. HM Land Registry INSPIRE Index Polygons: Providing precise, vector-based cadastral boundaries to convert geographic map points into active, interactive spatial fences.

3. Ordnance Survey UPRN Dataset: Serving as the master relational anchor across my schemas to completely eliminate the risk of text-based address mismatching.

4. HM Land Registry Restrictive Covenant Data: Providing the raw, unstructured textual deeds that my LLM pipeline parses to detect structural or usage limitations.

5. Domestic Energy Performance Certificates (EPC) Bulk Data: Introducing live asset energy ratings to layer physical compliance risks directly over our land boundaries.

6. CDRC Council Tax Bandings Dataset: Providing localized residential tax bands to analyze financial holding outlays and economic risk.

I plan to present this expanded, comprehensive vision to my supervisor in our next meeting to get her feedback on the multi-variable risk approach.

---

 Comprehensive Investment Risk Framework & Expanded Scope

Following my decision to expand the application into a comprehensive investment risk utility application, I have moved away from a basic legal compliance checker to an integrated multi-source analytical platform. The application evaluates a property's viability across three distinct risk vectors, combining macro-level structural indicators with micro-level legal data.

 The Combined Property Suitability Index (CPSI)
To give users a cohesive understanding of asset risk, the application calculates a weighted, algorithmic risk score between 0.0 and 1.0. This score is built across three core risk layers:

1. Legal Compliance Layer (40% Weight): The backend utilizes a Large Language Model automated via prompt engineering to scan the unstructured title deeds. If an absolute restriction on structural modifications, extensions, or commercial usage is detected, a high-risk flag (1.0) is triggered.

2. Environmental & Climate Risk Layer (30% Weight): Sourced from the Domestic EPC data archive. Properties holding an E, F, or G efficiency rating trigger a maximum risk score (1.0) due to the UK's strict Minimum Energy Efficiency Standards (MEES), which impose heavy leasing penalties and operational friction.

3. Economic & Structural Risk Layer (30% Weight): Sourced from the VOA building era and Council Tax datasets. An ancient building classification (pre-1900) paired with a high Council Tax Band (F, G, or H) indicates an asset with extreme potential retrofit overheads and high fixed holding costs while it sits vacant during development.

 Interactive Geospatial Visualizations
The frontend mapping layer will translate these backend mathematical risk scores into a highly visual, sub-meter granular interface:
*High Risk (Score ≥ 0.75): Rendered as a **Red** map vector. This indicates an asset with an active structural legal restriction combined with severe environmental non-compliance (e.g., a Victorian era building holding an alteration ban and an EPC F rating).
*Medium Risk (Score 0.40 – 0.74): Rendered as an **Amber** map vector. This signals conditional covenants or mid-tier efficiency brackets (EPC D) requiring targeted surveyor inspection.
*Low Risk (Score < 0.40): Rendered as a **Green** map vector. This represents modern, high-efficiency properties entirely free from restrictive title legalese.

When an asset parcel is selected, an interactive analytical sidebar dashboard dynamically slides open to display explicit checkmarks for the legal constraints, the building era, historical transaction trends, and ongoing financial tax outlays.



Log Entry: 28/06/2026 — Database Engineering & Pipeline Obstacles
This session was spent setting up my local PostgreSQL database and integrating the PostGIS extension to handle geospatial mapping data. While attempting to build out the master property core (`core.birmingham_properties_master`), I hit significant type safety and relational data alignment issues:

The UPRN BigInt Restriction: I originally tried to prepend an alphanumeric template string (`'PROP-'`) to rows in my staging queries. This threw a severe type mismatch error because the database schema strictly locks the UPRN field to a numeric `bigint` data type. I resolved this by discarding the string parsing completely and mapping the column directly to an auto-incrementing database sequence (`currval`), preserving pure numeric integrity.

The Aggregate Window Clause Error: When attempting to update master properties with raw EPC strings, PostgreSQL rejected my query with a `GROUP BY` error because the staging dataset lacked explicit inspection timestamps to sort by. I solved this by refactoring my window function query to use a blank ordering directive: `ORDER BY (SELECT NULL)`, forcing Postgres to safely isolate the primary matching record per postcode string.

The Neighborhood Bridge Challenge: While joining the VOA construction eras and Council Tax bands to my master table, I realized that the raw VOA metrics are aggregated strictly by ONS LSOA codes, while my core table maps individual property addresses via postcodes. To bridge this without a static map file, I wrote a custom batch-processing Python script (`ingest_geo_bridge.py`) leveraging the `postcodes.io` API. By querying the API in optimized batches of 100, I mapped all 18,824 unique local postcodes directly to their official LSOA identifiers without hitting connection timeouts, creating a clean spatial bridge table (`geo.postcode_lsoa_bridge`) that completed our backend data warehouse.



 Log Entry: 02/07/2026 — Backend API Construction & Repository Initialization

Today, I shifted gears from database ingestion to backend web architecture. I built out the application data layer to expose our newly enriched database grid to the web.

Flask API Layer Configuration: I established an isolated virtual environment (`venv`) and deployed a `Flask` application powered by `Flask-SQLAlchemy`. I wrote a dedicated object class (`BirminghamProperty`) that mirrors our production database schema.

Endpoint Delivery: I designed and verified a clean GET route at `/api/properties/<postcode>`. The endpoint accepts incoming user requests, normalizes uppercase strings, strips spacing anomalies, queries the PostgreSQL data layers, and returns a fully unified asset profile (UPRN, EPC rating, building era, and tax band) as an asynchronous JSON payload.

GitLab Deployment: I successfully initialized Git in my project root, generated a secure Personal Access Token via the university portal, and pushed my active codebase up to the server. This establishes my baseline code velocity and log history for tracking.

---

 Objectives for Next Week
- Research and select the web mapping framework for the user interface (evaluating Leaflet.js vs Mapbox).
- Write asynchronous JavaScript functions (`fetch()`) to pass bounding box parameters directly from the user's live map screen view into the backend database query engine.
- Design interactive sidebar dashboard overlays to render the complete asset risk profile upon user selection.