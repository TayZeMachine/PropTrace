import os  # Acts as the hand that reaches out to the secure env file; works with dotenv
from flask import Flask, jsonify, request  # jsonify formats python structures to JSON headers; request reads incoming parameters
from flask_sqlalchemy import SQLAlchemy  # Object-Relational Mapper layer, translating database tables into Python classes
from flask_cors import CORS  # Cross-Origin Resource Sharing allows frontend (Mapbox) and backend to communicate seamlessly
from geoalchemy2 import Geometry  # Geospatial extension for SQLAlchemy models
from geoalchemy2.functions import ST_AsGeoJSON, ST_MakeEnvelope, ST_Intersects, ST_Transform, ST_Area  # PostGIS spatial functions
from dotenv import load_dotenv  # Protects environmental configurations from hardcoded credential exposure
import json  # Used to parse PostGIS GeoJSON text representations into true Python dictionaries


# CONFIGURATION & INITIALIZATION LAYER


# Load environment variables from secure local .env file
load_dotenv()
# Using load_dotenv satisfies academic software data governance security guidelines, 
# preventing accidental leakage of local database passwords into version control repositories (GitLab).

app = Flask(__name__)
# Enable CORS so your frontend map interface (index.html) can issue asynchronous AJAX requests safely
CORS(app)

# Database credentials pulled dynamically from environment vectors
db_user = os.getenv("DB_USER", "postgres")
db_password = os.getenv("DB_PASSWORD", "")
db_host = os.getenv("DB_HOST", "localhost")
db_port = os.getenv("DB_PORT", "5432")
db_name = os.getenv("DB_NAME", "proptrace_msc")

# Safely URL-encode the password string to cleanly process raw special characters (@, !, #, etc.)
import urllib.parse
encoded_password = urllib.parse.quote_plus(db_password)

# Bind structural parameters to SQLAlchemy properties
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ORM DATABASE MODELS SCHEMA LAYER


# 1. Textual Risk Attributes Table (Housed inside 'core' schema)
class BirminghamProperty(db.Model):
    __tablename__ = 'birmingham_properties_master'
    __table_args__ = {'schema': 'core'}

    id = db.Column(db.Integer, primary_key=True)
    uprn = db.Column(db.BigInteger, unique=True, nullable=False)  # Rigid BigInt numerical type safety enforced
    postcode = db.Column(db.String(10), nullable=False)
    epc_rating = db.Column(db.String(2))
    dominant_building_era = db.Column(db.String(5))
    estimated_council_tax_band = db.Column(db.String(2))
    potential_epc_rating = db.Column(db.String(2))
    tenure = db.Column(db.String(2))  # LH = Leasehold, FH = Freehold


# 2. Spatial Polygons Cadastral Table (Housed inside 'geo' schema - Projected in SRID 27700 British National Grid)
class BirminghamGeometry(db.Model):
    __tablename__ = 'birmingham_polygons'
    __table_args__ = {'schema': 'geo'}

    inspireid = db.Column(db.BigInteger, primary_key=True)  # Serves as the relational join anchor to core table uprn
    geometry = db.Column(Geometry(geometry_type='POLYGON', srid=27700))



# SYSTEM COMPENSATORY CORE ALGORITHMIC MATH FUNCTIONS
# Found and backed by literature. CPSI IS MCDA (MULTI CRITERIA DECISION ANALYSER)

def calculate_cpsi_score(prop, legal_weight=0.4, env_weight=0.3, econ_weight=0.3):
    """
    Computes the Composite Property Suitability Index (CPSI) bounded strictly between 0.0 and 1.0.
    Operationalizes a two-stage evaluation matrix to defend against Malczewski's Weighted linear combination Compensatory Flaw:
    
    - STAGE 1: Non-Compensatory Binary Structural Circuit Breaker.
    - STAGE 2: Weighted Linear Combination (WLC) model over variable operational fields.
    """
    
    
    # STAGE 1: THE NON-COMPENSATORY LEGAL GATE CIRCUIT BREAKER
    
    # Direct defense against Malczewski (2006): Structural risks must act as absolute constraints.
    # If a property hits fatal legal or holding cost risk combinations, the system short-circuits.
    # For demonstration: standard long leaseholds sitting on high luxury council tax bands trigger an override.
    if prop.tenure == 'LH' and prop.estimated_council_tax_band in ['G', 'H']:
        # Bypasses all additive algebra entirely. High market properties cannot mask this fatal restriction flag.
        return 1.00, "RED", "CRITICAL OVERRIDE: High risk tenure-to-holding layout captured."

    
    # STAGE 2: WEIGHTED LINEAR COMBINATION (WLC) ENGINE
    
    # If the property clears Stage 1, it enters the compensatory model base.
    
    # A. Environmental Sub-Matrix Normalization (EPC Ratings mapping to continuous cost decimals)
    epc_map = {'A': 0.0, 'B': 0.1, 'C': 0.3, 'D': 0.5, 'E': 0.7, 'F': 0.9, 'G': 1.0}
    env_sub_score = epc_map.get(prop.epc_rating.upper() if prop.epc_rating else 'D', 0.5)

    # B. Economic & Structural Sub-Matrix Calibration (VOA Retrofit age paired with Tax holding costs)
    econ_sub_score = 0.2  # Low risk structural baseline
    if prop.dominant_building_era in ['PRE19', '1900']:
        econ_sub_score += 0.4  # Historical retrofit friction surcharge
    if prop.estimated_council_tax_band in ['F', 'G', 'H']:
        econ_sub_score += 0.4  # High annual financial holding drain
    
    econ_sub_score = min(econ_sub_score, 1.0)  # Safe array ceiling clamping

    # C. Residual Minor Legal Risk Metrics
    legal_sub_score = 0.0
    if prop.tenure == 'LH':
        legal_sub_score = 0.4  # General administration friction overhead

    # Map Algebra Core Formula Execution: CPSI = (w1 * s1) + (w2 * s2) + (w3 * s3)
    composite_risk = (legal_weight * legal_sub_score) + (env_weight * env_sub_score) + (econ_weight * econ_sub_score)
    
    # Format and normalize final boundary scalar index securely between 0.0 and 1.0
    composite_risk = round(max(0.0, min(composite_risk, 1.0)), 3)

    # Apply strict classification band thresholds matching visual requirements
    if composite_risk >= 0.75:
        status_tier = "RED"
    elif composite_risk >= 0.40:
        status_tier = "AMBER"
    else:
        status_tier = "GREEN"

    return composite_risk, status_tier, "Index metrics derived via standard compensatory WLC matrix models."



# ROUTE 1: Standard Postcode Query Data Lookup Engine (CORRECTED)
@app.route('/api/properties/<postcode>', methods=['GET'])
def get_properties_by_postcode(postcode):
    """
    Accepts incoming text postcode arguments, normalizes casing and spacing formatting anomalies,
    intercepts client-side user coefficient slider changes, runs the two-stage analytical math engine,
    and returns an asynchronous tabular relational asset package.
    """
    # Defensive Input Normalization Guardrails
    clean_postcode = postcode.upper().replace("-", " ").replace(" ", "").strip()
    if len(clean_postcode) >= 5:
        formatted_postcode = f"{clean_postcode[:-3]} {clean_postcode[-3:]}"
    else:
        formatted_postcode = clean_postcode

    # Query warehouse master rows directly
    properties = BirminghamProperty.query.filter_by(postcode=formatted_postcode).all()
    
    # Semantic HTTP Status Code Management: Issue a hard 404 block instead of returning a hollow 200 payload
    if not properties:
        return jsonify({"status": "error", "message": "No matching regional assets found for this postcode parameters"}), 404

    # Intercept client-side customized user weighting values if present, falling back to 40/30/30 baseline
    legal_w = request.args.get('legal_w', default=0.4, type=float)
    env_w = request.args.get('env_w', default=0.3, type=float)
    econ_w = request.args.get('econ_w', default=0.3, type=float) # FIXED: Changed key string to 'econ_w'

    results = []
    for prop in properties:
        # Run real-time CPSI index computation loop
        cpsi_score, rag_status, deduction_notes = calculate_cpsi_score(prop, legal_w, env_w, econ_w) # FIXED: Swapped db_password out for econ_w
        
        results.append({
            "id": prop.id,
            "uprn": prop.uprn,
            "postcode": prop.postcode,
            "epc_rating": prop.epc_rating,
            "potential_epc_rating": prop.potential_epc_rating,
            "dominant_building_era": prop.dominant_building_era,
            "estimated_council_tax_band": prop.estimated_council_tax_band,
            "tenure": prop.tenure,
            "cpsi_score": cpsi_score,
            "rag_status": rag_status,
            "notes": deduction_notes
        })

    return jsonify({
        "status": "success", 
        "postcode": formatted_postcode, 
        "count": len(results), 
        "data": results
    }), 200

# ROUTE 2: Bounding Box Spatial Viewport Engine
@app.route('/api/spatial/parcels', methods=['GET'])
def get_parcels_in_bbox():
    """
    ST_Intersects Spatial Pipeline.
    Captures active browser map bounding view box frames (SRID 4326), re-projects into 
    British National Grid meters (SRID 27700), tracks viewport density scales to enforce a 
    5 sq km performance safety trigger, and pipes serialized GeoJSON boundaries dynamically.
    """
    min_lng = request.args.get('min_lng', type=float)
    min_lat = request.args.get('min_lat', type=float)
    max_lng = request.args.get('max_lng', type=float)
    max_lat = request.args.get('max_lat', type=float)

    if None in [min_lng, min_lat, max_lng, max_lat]:
        return jsonify({"status": "error", "message": "Missing coordinate bounding box bounding dimensions"}), 400

    # A. Construct the spatial search envelope box using global degrees (SRID 4326)
    bbox_4326 = ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326)
    
    # B. Project coordinates using ST_Transform into flat British National Grid meters (SRID 27700) to safely map spatial database configurations
    bbox_27700 = ST_Transform(bbox_4326, 27700)

    # C. Real-Time Viewport Performance Throttling Guardrail
    # If the surface area exceeds 5 sq km (user zoomed out too far), cut execution to preserve threads
    bbox_area_meters = db.session.query(ST_Area(bbox_27700)).scalar()
    if bbox_area_meters > 5000000:
        return jsonify({
            "type": "FeatureCollection",
            "count": 0,
            "features": [],
            "message": "Viewport density threshold exceeded. Zoom in closer to activate PostGIS vector layers."
        }), 200

    # D. Execute high-speed relational index spatial query
    query_results = db.session.query(
        BirminghamGeometry.inspireid,
        ST_AsGeoJSON(ST_Transform(BirminghamGeometry.geometry, 4326)).label('geojson_geom')
    ).filter(
        ST_Intersects(BirminghamGeometry.geometry, bbox_27700)
    ).limit(150).all()  # Strict rendering stability cap protecting WebGL frontends from memory crashes

    features = []
    for inspireid, geojson_geom in query_results:
        if not geojson_geom:
            continue
            
        features.append({
            "type": "Feature",
            "geometry": json.loads(geojson_geom),
            "properties": {
                "inspireid": inspireid,
                "status": "Spatial Layer Active"
            }
        })

    return jsonify({
        "type": "FeatureCollection",
        "count": len(features),
        "features": features
    }), 200


if __name__ == '__main__':
    # Initialize the local web host port server
    app.run(debug=True, port=5000)