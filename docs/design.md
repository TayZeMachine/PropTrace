Architecure, Design Decisions and Application Evolution

This document will serve as my file for architectural decision record
and system design blueprint.It will track how I came to certain decisions, dcoumenting critical debugging pivots and will outline the boundaries of the Composite Property Suitability Index.

1) Database Schema and Warehouse Architecture

The local database instance is structured using a strict three-tier schema isolation model designed to decouple volatile staging inputs from active spatial layers and production-ready core API endpoints. This setup was initialized on June 22, 2026.

The first tier is the staging schema. This acts as an immutable landing archive for raw, high-volume administrative datasets. It houses two primary tables. The first is staging.price_paid_data, which contains the complete historical residential transaction footprint for the Birmingham territory from 1995 to the present, totaling 455,140 rows. The second is staging.raw_covenants, which stores unstructured legal text snippets of restrictive title deeds filtered programmatically from a nationwide database, totaling 1,911,065 rows.

The second tier is the geo schema. This schema functions as the spatial anchor registry for high-performance geometry layers and coordinate points. It contains geo.birmingham_polygons, which holds 346,823 complex 2D vector land boundary maps sourced from the HM Land Registry index. It also includes geo.birmingham_uprns, which stores 113,027 master Unique Property Reference Numbers mapped to their physical coordinate points. Additionally, it holds the geo.postcode_lsoa_bridge table, which is updated dynamically in batches of 100 to map individual property postcodes to their corresponding neighborhood census zones.

The final tier is the core schema. This serves as the optimized production domain that the web backend queries directly. It contains core.birmingham_properties_master, which holds 113,027 master records. This table acts as the central relational spine of the entire application, mapping unique UPRN keys to postcodes, tenure classifications, energy performance ratings, and building construction eras.

2) Engineering Challenges and technical pivots

Relational Hash Joins over Cartesian Products
On June 23, 2026, we resolved a major performance bottleneck in our SQL updates. During our initial data setup, running a mass relational update between our core properties master table and the raw covenants staging table without a defined join predicate triggered an unintended Cartesian Product. This cross-join generated a massive operational loop of over 215 billion comparisons, causing a severe write-lock on the database engine. To resolve this, we refactored the update script into an optimized relational Hash Join using indexed UPRN keys. This reduced the execution time from an infinite freeze to a clean 2.01 seconds.

Memory-Safe Chunked Ingestion
Also on June 23, 2026, we engineered a memory-safe ingestion pipeline to handle massive government datasets. Trying to load a 5.3 gigabyte flat file of country-wide transaction histories directly into standard system RAM caused immediate heap overflows and local machine crashes. To bypass this, we implemented a generator-driven streaming pipeline in Python that processes files in chunks of 50,000 rows. This allowed us to filter for Birmingham properties on the fly and release system memory after committing each block. We also resolved an undocumented column-shift bug caused by a hidden sixteenth column in the source data by mapping the missing status field and setting our index parameter to false.

Bypassing Environment Roadblocks via Pyogrio
On June 23, 2026, we encountered compilation failures while trying to load geographic boundary files. Our initial attempts to parse Land Registry Geography Markup Language files using standard Python libraries failed because of native Windows compiler errors with background GDAL software dependencies. To bypass this, we adapted our ingestion pipeline to use Pyogrio. Pyogrio is a modern vector input-output engine that comes with pre-compiled binary libraries natively supported by GeoPandas. This allowed us to successfully parse the coordinate nodes and populate our spatial tables with 346,823 cadastral boundaries in just 107.55 seconds.

Decoupled Query Strategy and Mapbox GL/ Leaflet JS Trade off Transition
During the system design phase, we proactively evaluated how to handle visual rendering for dense spatial datasets, choosing to bypass Leaflet.js and an all-in-one query model to prevent severe map lag. We deployed Mapbox GL JS on the frontend to leverage hardware-accelerated WebGL vector tiles, shifting the rendering burden to the user's graphics card to maintain a fluid 60 frames per second. We paired this with a decoupled backend API architecture that splits responsibilities into two lightweight routes: Route 1 (the Tabular API) handles only text and numbers to instantly calculate CPSI scores without heavy joins, while Route 2 (the Spatial API) focuses strictly on streaming physical boundaries visible on the screen. This proactive design ensures that panning the map only triggers fast geometry streams via Route 2, while text data and scoring are only pulled quietly from Route 1 when a user clicks an individual property parcel.

Transitioning to an Automated Compliance Check Engine
On July 10, 2026, we refined our user interface design to eliminate risk. Providing a free-text chatbot box for legal deed queries introduced a very high risk of model hallucinations, where the AI could accidentally make up fake easements or land restrictions. To prevent this, we redesigned the tool into an Automated Compliance Check Engine. The backend now runs five hardcoded legal questions regarding structural alterations, commercial use, nuisance clauses, access paths, and materials using strict instruction templates. This forces the model to return a clean, verifiable Yes, No, or Unknown checklist backed by direct quotes from the deeds.

3. Definitive CPSI Model Formulation

The Composite Property Suitability Index was implemented on July 14, 2026. 

This index was fundamentally redesigned as a result of our literature review, specifically Jacek Malczewski's work on Multi-Criteria Decision Analysis (MCDA) in Geographic Information Systems. Standard spatial decision systems use a Weighted Linear Combination where a very good score in one category can offset and hide a dangerous risk in another. To resolve this critical flaw, we designed a two-stage evaluation model.

Stage 1 is the Non-Compensatory Legal Constraint Gate. Before running any additive calculations, the engine performs a preliminary check on absolute physical and tenure restrictions. If a property is registered as a Leasehold and sits in a high holding-cost Council Tax Band like G or H, the system triggers an immediate circuit breaker. This bypasses all standard weight calculations and automatically locks the final risk score at a maximum value of 1.00, flagging the asset as high risk.

Stage 2 is the Weighted Linear Combination Equation. If a property successfully clears the Stage 1 boundary gate, its risk score is calculated dynamically based on user-defined weights. The core formula is:

CPSI = (w_legal * S_legal) + (w_env * S_env) + (w_econ * S_econ)

In this formula, S_legal represents the legal risk score, which is set to 0.4 for Leaseholds and 0.0 for Freeholds. S_env represents the environmental risk sub-score, which maps the property's energy performance rating to a decimal scale where rating A is 0.0 and rating G is 1.0. S_econ represents the economic risk sub-score, which starts at a baseline of 0.2 and adds a 0.4 penalty for pre-1900 Victorian historical builds and a 0.4 penalty for high council tax brackets. The variables w_legal, w_env, and w_econ represent the custom weights adjusted by the user, which must always add up to a total of 1.0.

## 4. Software Engineering Methodology and Sprint Logs

The development of this project is governed by a disciplined, iterative Agile methodology.

### Sprint 1: Data Ingestion and Multi-Schema Isolation
**Date Range: June 15 – June 22, 2026**
* **Objective:** Initialize the core data engineering warehouse layer, streaming and securing raw municipal and spatial datasets for the Birmingham territory.
* **Deliverables:** Built the three-tier database schema consisting of staging, geo, and core schemas to sandbox volatile inputs. Wrote memory-safe Pandas chunking scripts to ingest 113,027 baseline property records, 1.91 million raw legal staging rows, and 346,823 cadastral land parcel polygons without system RAM crashes.

### Sprint 2: Data Reconciliation and Optimization
**Date Range: June 23 – June 29, 2026**
* **Objective:** Resolve relational schema bottlenecks and configure backend database optimization.
* **Deliverables:** Refactored the slow cross-schema property updates into a relational Hash Join, reducing execution speed from a database write-lock down to 2.01 seconds. Developed a streaming pipeline to safely filter 454,282 Price Paid Data records on-the-fly, and integrated Pyogrio to flawlessly parse spatial geometry layers into PostGIS.

### Sprint 3: Decoupled API Engineering and GPU-Accelerated Frontend
**Date Range: June 30 – July 6, 2026**
* **Objective:** Initialize the web application backend and build a high-performance visual map interface.
* **Deliverables:** Configured Flask with zero-hardcode environmental variables and CORS security. Decoupled the query strategy into Route 1 for postcode attributes and Route 2 for spatial geometries to eliminate panning latency. Set up Mapbox GL JS on the frontend to leverage WebGL client-side hardware rendering.

### Sprint 4: Decision Support and System Requirements
Date Range: July 7 – July 14, 2026
* **Objective:** Implement the core decision-making math and document system performance requirements.
* **Deliverables:** Finalized the formal Functional and Non-Functional Requirements specifications. Programmed the two-stage Composite Property Suitability Index engine, deploying the Stage 1 non-compensatory circuit breaker to catch critical legal constraints alongside Stage 2 continuous weighting calculations.