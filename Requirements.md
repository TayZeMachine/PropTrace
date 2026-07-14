System Requirement Specifications (Functional & Non Functional)

This document will outline the formal Functional and Non-Functional Requirements governing the system architecture. These criteria establish the verification matrix used during the testing and evaluation phases.

1) Functional Requirements

These upcoming requirements will outline the core behaviours that the application must execute.

FR1 : Static Multi-Source Data Ingestion
The database tier must support the batch ingestion of large-scale public datasets from mostly CSV and one gml file specifically extracting and structuring HM Land registry transaction history, Ordance Survey UPRNS, GOV EPC RATINGS, AND CDRC Council Tax/Building Age data and HM Restricted Covenants.

FR2: Automated Batch Spatial Bridging
  The backend must run an automatic background script (`ingest_geo_bridge.py`) to connect property postcodes with neighborhood level (LSOA) risk data from my CDRC dataset which uses LSOA codes instead of postcode. The script must send postcodes to the `postcodes.io` API in efficient groups of 100 to find their matching neighborhood codes, and then save these matches into a permanent database lookup table (`geo.postcode_lsoa_bridge`) so the app can link the datasets instantly.

FR3: Postcode Query Normalization
  The system MUST expose a RESTful API route at `/api/properties/<postcode>` that intercepts user string entries, programmatically strips whitespace, capitalizes characters, and applies a negative index slice (`f"{clean_postcode[:-3]} {clean_postcode[-3:]}"`) to systematically normalize chaotic user inputs into exact Royal Mail indexing keys.

FR4: Semantic HTTP Routing & Exception Handlers
  If a valid postcode query yields an empty collection row set or maps onto a coordinate sector containing zero active risk metrics, the API engine MUST short-circuit and issue a strict `404 Not Found` HTTP status code rather than returning an empty `200 OK` payload, protecting client-side template engines.

FR5: Map Viewport Searching
 The map system must capture the four corners of the user's current screen view (`min_lng`, `min_lat`, `max_lng`, `max_lat`). It must translate these global coordinates into British National Grid meters (SRID 27700) and run a fast database search to find and display all the matching property boundary shapes inside that specific view.

FR6: Non-Compensatory Algorithmic Circuit Breaker (Stage 1 Risk)
  The core decision engine, governed by Jacek Malczewski's Multi-Criteria Decision Analysis (MCDA) framework, MUST run a preliminary non-compensatory check on property tenure and financial layout constraints. If an absolute structural friction point is matched (e.g., Leasehold tenure paired with a high-holding-cost Council Tax Band G or H), the system MUST trigger an immediate circuit breaker, bypassing standard additive calculations to hardcode the risk score to a maximum value of 1.00 (RED classification status).

FR7: User-Driven Compensatory Weight Tuning (Stage 2 Risk)
  If an asset successfully clears the Stage 1 boundary gate, the system MUST compute a Weighted Linear Combination (WLC) score across continuous operational vectors. The backend MUST accept explicit URL argument weight parameters passed by frontend dashboard sliders (`legal_w`, `env_w`, `econ_w`), enabling stakeholders to interactively adjust coefficients and trigger dynamic real-time score updates.

2)  Non-Functional Requirements 

These requirements will define the structural constraints, performance parameters, safety rules, and security boundaries governing the system.

NFR1: Numeric Type Safety and Relational Integrity
  The database schemas MUST strictly enforce relational integrity and numeric type safety across joins by anchoring property nodes to the master Ordnance Survey UPRN column using a native `BigInt` data type constraint, systematically rejecting alphanumeric string adaptations to preserve indexing speed.

NFR2: Viewport Performance Safety Throttling
  To prevent the application from lagging or crashing, the system must automatically restrict spatial searches. The backend must calculate the size of the user's current screen view in real time. If the viewed area is larger than 5 square kilometers, the system must halt the query and return a warning message asking the user to zoom in. This protects the server from overload and keeps the map interface smooth and responsive.

NFR3: Asynchronous Interface Updates
  The web interface must update the map, display property shapes, and change sidebar values without forcing the user to reload the entire web page. The app must use background requests (AJAX/Fetch) to send and receive data smoothly, keeping the user experience fast and uninterrupted.

NFR4: Map Display Limits
  To prevent the user's web browser from lagging or crashing, the map must never try to draw too many property shapes at the same time. The backend database must strictly limit its output to a maximum of 150 property boundary shapes per screen view (`.limit(150)`) to protect the client-side WebGL engine (Mapbox GL JS) from running out of memory.

NFR5: Database Protection and Data Safety
  To keep the core database safe and uncorrupted, all original public datasets (like CSVs and boundary files) must remain completely locked and unedited. Any temporary user actions—such as adjusting the risk-weight sliders or adding custom map drawings—must be kept entirely in the user's local web browser session, ensuring the main production tables are never modified or damaged.