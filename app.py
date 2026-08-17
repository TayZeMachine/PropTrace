import os
import math
import urllib.parse
import json
from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from geoalchemy2 import Geometry
from sqlalchemy import text, func
from dotenv import load_dotenv
from geoalchemy2.functions import (
    ST_AsGeoJSON,
    ST_Transform,
    ST_Intersects,
    ST_MakeEnvelope,
    ST_Touches,
    ST_SimplifyPreserveTopology 
)

load_dotenv()
app = Flask(__name__)
CORS(app)

# --- DATABASE CONFIGURATION ---
db_user = os.getenv("DB_USER", "postgres")
db_password = os.getenv("DB_PASSWORD", "")
db_host = os.getenv("DB_HOST", "localhost")
db_port = os.getenv("DB_PORT", "5432")
db_name = os.getenv("DB_NAME", "proptrace_msc")

encoded_password = urllib.parse.quote_plus(db_password)
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'max_overflow': 20,
    'pool_recycle': 1800,
    'pool_pre_ping': True  # Recovers from dropped connections without raising 500 errors
}
db = SQLAlchemy(app)
@app.route('/')
def home():
    return render_template('index.html')

# --- ORM MODELS WITH EXPLICIT FOREIGN KEY RELATIONSHIP ---
class BirminghamGeometry(db.Model):
    __tablename__ = 'birmingham_polygons'
    __table_args__ = {'schema': 'geo'}
    inspireid = db.Column(db.BigInteger, primary_key=True)
    geometry = db.Column(Geometry(geometry_type='POLYGON', srid=27700))

class BirminghamProperty(db.Model):
    __tablename__ = 'birmingham_properties_master'
    __table_args__ = {'schema': 'core'}
    id = db.Column(db.Integer, primary_key=True)
    uprn = db.Column(db.BigInteger, unique=True, nullable=False)
    postcode = db.Column(db.String(10), nullable=False)
    
    # FK linking tabular attributes to spatial boundaries
    inspireid = db.Column(db.BigInteger, db.ForeignKey('geo.birmingham_polygons.inspireid')) 
    
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    epc_rating = db.Column(db.String(2))
    dominant_building_era = db.Column(db.String(5))
    potential_epc_rating = db.Column(db.String(2))
    tenure = db.Column(db.String(2))
    has_recorded_covenant = db.Column(db.Boolean, nullable=True)
    in_flood_zone_3 = db.Column(db.Boolean, nullable=True)

    # Explicit ORM relationship enabling lazy joined loading
    polygon = db.relationship('BirminghamGeometry', backref=db.backref('properties', lazy='select'))

# --- STAGE 2 WEIGHT PARSING ---
def parse_weights(args):
    """Safely extracts client-side WLC weights from the request arguments."""
    try:
        legal_weight = float(args.get('legal_weight', 0.4))
        env_weight = float(args.get('env_weight', 0.3))
        econ_weight = float(args.get('econ_weight', 0.3))
    except (TypeError, ValueError):
        legal_weight, env_weight, econ_weight = 0.4, 0.3, 0.3

    total = legal_weight + env_weight + econ_weight
    if total <= 0:
        return 0.4, 0.3, 0.3
    return legal_weight / total, env_weight / total, econ_weight / total

# --- BBOX LIMIT CALCULATION ---
BBOX_LIMIT_METRES = 5000
_EARTH_RADIUS_METRES = 6371000.0

def bbox_diagonal_metres(w, s, e, n):
    lat1, lat2 = math.radians(s), math.radians(n)
    dlat = math.radians(n - s)
    dlng = math.radians(e - w)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * _EARTH_RADIUS_METRES * math.asin(math.sqrt(a))

def simplify_profile_for_zoom(zoom):
    try:
        zoom = float(zoom)
    except (TypeError, ValueError):
        zoom = 13.0
    if zoom < 14:
        return 0.00015, 5
    elif zoom < 16:
        return 0.00003, 6
    else:
        return 0.000005, 7

era_map = {
    'A': 'Pre-1900', 'B': '1900-1918', 'C': '1919-1929', 'D': '1930-1939',
    'E': '1945-1954', 'F': '1955-1964', 'G': '1965-1972', 'H': '1973-1982',
    'I': '1983-1992', 'J': '1993-1999', 'K': '2000-2008', 'L': '2009-2021'
}

# --- CPSI SCORING ENGINE ---
def calculate_cpsi_score(prop, legal_weight=0.4, env_weight=0.3, econ_weight=0.3):
    """
    Executes two-stage hybrid MCDA and returns score along with full math breakdown.
    
    Tier 1 (Legal): Tenure friction + Restrictive Covenants (Stage 1 Gate)
    Tier 2 (Environmental): Flood Zone 3 risk (Stage 1 Gate & Tier 2 Env Score)
    Tier 3 (Structural & Energy / Econ): Combined EPC Rating + Dominant Building Era
    """
    
    # --- TIER 1: LEGAL SUB-SCORE ---
    legal_sub_score = 0.4 if prop.tenure == 'LH' else (0.1 if prop.tenure else 0.0)

    # --- TIER 2: SPATIAL & ENVIRONMENTAL HAZARD SUB-SCORE (Flood Risk) ---
    has_flood_risk = getattr(prop, 'in_flood_zone_3', False) is True
    env_sub_score = 1.0 if has_flood_risk else 0.0

    # --- TIER 3: STRUCTURAL & ENERGY PERFORMANCE SUB-SCORE (EPC + Building Era) ---
    # 1. EPC Rating Component (0.0 = A, 1.0 = G)
    epc_map = {'A': 0.0, 'B': 0.1, 'C': 0.3, 'D': 0.5, 'E': 0.7, 'F': 0.9, 'G': 1.0}
    epc_score = epc_map.get((prop.epc_rating or '').upper(), None) if prop.epc_rating else None

    # 2. Building Era Component (0.00 = Modern, 1.00 = Pre-1900)
    era_code = (prop.dominant_building_era or '').upper().strip()
    era_score = None
    if era_code == 'A':
        era_score = 1.00
    elif era_code in ['B', 'C', 'D']:
        era_score = 0.75
    elif era_code in ['E', 'F', 'G']:
        era_score = 0.50
    elif era_code in ['H', 'I', 'J']:
        era_score = 0.25
    elif era_code in ['K', 'L']:
        era_score = 0.00

    # Combine EPC & Building Era into Tier 3 Sub-Score
    if epc_score is not None and era_score is not None:
        econ_sub_score = round((epc_score + era_score) / 2.0, 3)
    elif epc_score is not None:
        econ_sub_score = epc_score
    elif era_score is not None:
        econ_sub_score = era_score
    else:
        econ_sub_score = 0.0

    # --- STAGE 2 WEIGHTED CONTRIBUTIONS ---
    legal_contrib = round(legal_sub_score * legal_weight, 3)
    env_contrib = round(env_sub_score * env_weight, 3)
    econ_contrib = round(econ_sub_score * econ_weight, 3)
    uncapped_sum = round(legal_contrib + env_contrib + econ_contrib, 3)

    # --- STAGE 1 (Non-Compensatory Gates) CHECK ---
    has_covenant = getattr(prop, 'has_recorded_covenant', False) is True
    is_override = False
    
    if has_covenant or has_flood_risk:
        composite_risk = 1.00
        rag = "RED"
        is_override = True
        notes = "CRITICAL OVERRIDE: Non-compensatory hazard detected."
    else:
        composite_risk = max(0.0, min(uncapped_sum, 1.0))
        if composite_risk >= 0.75:
            rag = "RED"
        elif composite_risk >= 0.40:
            rag = "AMBER"
        else:
            rag = "GREEN"
        notes = "Index metrics derived via standard compensatory WLC matrix models."

    breakdown = {
        "weights_used": {
            "legal": legal_weight,
            "env": env_weight,
            "econ": econ_weight
        },
        "sub_scores": {
            "legal": legal_sub_score,
            "env": env_sub_score,
            "econ": econ_sub_score,
            "tier3_breakdown": {
                "epc_score": epc_score,
                "era_score": era_score
            }
        },
        "contributions": {
            "legal": legal_contrib,
            "env": env_contrib,
            "econ": econ_contrib
        },
        "uncapped_sum": uncapped_sum,
        "final_cpsi": composite_risk,
        "is_override": is_override
    }

    return composite_risk, rag, notes, breakdown

# --- ROUTE 1: POSTCODE SEARCH ---
@app.route('/api/properties/<postcode>', methods=['GET'])
def get_properties_by_postcode(postcode):
    clean_postcode = postcode.upper().replace("-", "").replace(" ", "").strip()

    query = db.session.query(
        BirminghamProperty,
        ST_AsGeoJSON(ST_Transform(BirminghamGeometry.geometry, 4326)).label('geojson')
    ).outerjoin(
        BirminghamGeometry, BirminghamProperty.inspireid == BirminghamGeometry.inspireid
    ).filter(
        func.replace(BirminghamProperty.postcode, ' ', '') == clean_postcode
    ).all()

    if not query:
        return jsonify({"status": "error", "message": "No matching regional assets found."}), 404

    legal_w, env_w, econ_w = parse_weights(request.args)

    results = []
    for prop, geojson in query:
        cpsi, rag, notes, _ = calculate_cpsi_score(prop, legal_w, env_w, econ_w)
        results.append({
            "uprn": prop.uprn,
            "postcode": prop.postcode,
            "epc_rating": prop.epc_rating,
            "dominant_building_era": prop.dominant_building_era,
            "tenure": prop.tenure,
            "has_recorded_covenant": prop.has_recorded_covenant,
            "in_flood_zone_3": prop.in_flood_zone_3,
            "rag_status": rag,
            "cpsi_score": cpsi,
            "geometry_geojson": geojson
        })

    return jsonify({"status": "success", "properties": results}), 200

# --- ROUTE 2: BBOX SEARCH ---
@app.route('/api/spatial/parcels', methods=['GET'])
def get_parcels_in_bbox():
    bounds = request.args.get('bounds')
    arbitrage_mode = request.args.get('filter')
    zoom = request.args.get('zoom', 13)
    include_debug = request.args.get('debug') == '1'

    if not bounds:
        return jsonify({"status": "error"}), 400

    try:
        w, s, e, n = map(float, bounds.split(','))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Malformed bounds parameter."}), 400

    diagonal = bbox_diagonal_metres(w, s, e, n)
    if diagonal > BBOX_LIMIT_METRES:
        return jsonify({"status": "error", "message": "Please zoom in to view parcel data."}), 400

    center_lng = (w + e) / 2.0
    center_lat = (s + n) / 2.0
    simplify_tol, geojson_precision = simplify_profile_for_zoom(zoom)

    arbitrage_clause = ""
    if arbitrage_mode == 'retrofit':
        arbitrage_clause = "AND p.epc_rating IN ('E', 'F', 'G')"
    elif arbitrage_mode == 'hmo':
        arbitrage_clause = "AND p.dominant_building_era IN ('A', 'B', 'C', 'D')"

    parcels_sql = text(f"""
        WITH viewport AS MATERIALIZED (
            SELECT ST_Transform(ST_MakeEnvelope(:w, :s, :e, :n, 4326), 27700) AS bbox_bng
        ),
        candidates AS (
            SELECT
                p.uprn, p.inspireid, p.epc_rating, p.dominant_building_era,
                p.tenure, p.has_recorded_covenant, p.in_flood_zone_3,
                g.geometry AS geom_bng
            FROM core.birmingham_properties_master p
            JOIN geo.birmingham_polygons g ON g.inspireid = p.inspireid
            CROSS JOIN viewport v
            WHERE g.geometry IS NOT NULL
              AND ST_Intersects(g.geometry, v.bbox_bng)
              {arbitrage_clause}
            ORDER BY (p.longitude - :center_lng) * (p.longitude - :center_lng)
                   + (p.latitude - :center_lat) * (p.latitude - :center_lat)
            LIMIT 350
        )
        SELECT
            uprn, inspireid, epc_rating, dominant_building_era, tenure,
            has_recorded_covenant, in_flood_zone_3,
            ST_AsGeoJSON(
                ST_SimplifyPreserveTopology(ST_Transform(geom_bng, 4326), :simplify_tol),
                :geojson_precision
            ) AS geojson
        FROM candidates
    """)

    rows = db.session.execute(parcels_sql, {
        "w": w, "s": s, "e": e, "n": n,
        "center_lng": center_lng, "center_lat": center_lat,
        "simplify_tol": simplify_tol, "geojson_precision": geojson_precision
    }).all()

    legal_w, env_w, econ_w = parse_weights(request.args)

    features = []
    for row in rows:
        cpsi, rag, notes, _ = calculate_cpsi_score(row, legal_w, env_w, econ_w)
        features.append({
            "type": "Feature",
            "id": row.inspireid,
            "geometry": json.loads(row.geojson),
            "properties": {
                "uprn": row.uprn,
                "inspireid": row.inspireid,
                "epc_rating": row.epc_rating,
                "dominant_building_era": row.dominant_building_era,
                "tenure": row.tenure,
                "has_recorded_covenant": row.has_recorded_covenant,
                "in_flood_zone_3": row.in_flood_zone_3,
                "rag_status": rag,
                "cpsi_score": cpsi
            }
        })

    payload = {"type": "FeatureCollection", "features": features}
    return jsonify(payload), 200

# --- ROUTE 3: SITE ASSEMBLY ENGINE ---
@app.route('/api/site-assembly/<int:inspireid>', methods=['GET'])
def site_assembly(inspireid):
    try:
        target_geom = db.session.query(BirminghamGeometry.geometry).filter_by(inspireid=inspireid).subquery()
        
        neighbors = db.session.query(
            BirminghamGeometry.inspireid,
            ST_AsGeoJSON(ST_Transform(BirminghamGeometry.geometry, 4326)).label('geojson')
        ).filter(
            ST_Touches(BirminghamGeometry.geometry, target_geom)
        ).all()

        features = []
        for n_inspireid, geojson in neighbors:
            features.append({
                "type": "Feature",
                "geometry": json.loads(geojson),
                "properties": {"inspireid": n_inspireid, "assembly_target": True}
            })

        return jsonify({"status": "success", "features": features}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ROUTE 4: REPORT METADATA ---
@app.route('/api/property/report/<int:uprn>', methods=['GET'])
def get_property_report(uprn):
    prop = BirminghamProperty.query.filter_by(uprn=uprn).first()
    if not prop:
        return jsonify({"status": "error"}), 404

    legal_w, env_w, econ_w = parse_weights(request.args)
    cpsi, rag, notes, breakdown = calculate_cpsi_score(prop, legal_w, env_w, econ_w)

    epc_order = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6}
    current_rank = epc_order.get((prop.epc_rating or '').upper())
    potential_rank = epc_order.get((prop.potential_epc_rating or '').upper())
    epc_gap_bands = (current_rank - potential_rank) if (current_rank is not None and potential_rank is not None) else None

    readable_era = era_map.get(prop.dominant_building_era, prop.dominant_building_era or 'Not sourced')

    # TIER 1: LEGAL
    covenant_flag = prop.has_recorded_covenant
    if covenant_flag is True:
        tier_1_legal = {
            "tenure": "Leasehold" if prop.tenure == 'LH' else ("Freehold" if prop.tenure else "Not sourced"),
            "has_covenant": True,
            "is_verified": True,
            "status_label": "RESTRICTIVE COVENANT",
            "notes": "Active restrictive covenants recorded on Land Registry Title."
        }
    elif covenant_flag is False:
        tier_1_legal = {
            "tenure": "Leasehold" if prop.tenure == 'LH' else ("Freehold" if prop.tenure else "Not sourced"),
            "has_covenant": False,
            "is_verified": True,
            "status_label": "CLEAR TITLE",
            "notes": "No title encumbrances or recorded covenants detected."
        }
    else:
        tier_1_legal = {
            "tenure": "Leasehold" if prop.tenure == 'LH' else ("Freehold" if prop.tenure else "Not sourced"),
            "has_covenant": False,
            "is_verified": False,
            "status_label": "NOT VERIFIED",
            "notes": "Land Registry covenant data not yet sourced for this title — treat as unknown, not clear."
        }

    # TIER 2: ENVIRONMENTAL (Properly synced with DB flood status)
    flood_flag = prop.in_flood_zone_3
    if flood_flag is True:
        tier_2_environmental = {
            "data_available": True,
            "status_label": "FLOOD ZONE 3 (HIGH RISK)",
            "is_high_risk": True,
            "is_verified": True,
            "notes": "Property falls within Environment Agency Flood Zone 3 (High Risk)."
        }
    elif flood_flag is False:
        tier_2_environmental = {
            "data_available": True,
            "status_label": "LOW RISK / ZONE 1",
            "is_high_risk": False,
            "is_verified": True,
            "notes": "Property clear of high-risk flood zone boundaries."
        }
    else:
        tier_2_environmental = {
            "data_available": False,
            "status_label": "NOT VERIFIED",
            "is_high_risk": False,
            "is_verified": False,
            "notes": "Environment Agency flood zone data not yet sourced for this parcel."
        }

    # TIER 3: STRUCTURAL & ENERGY PERFORMANCE
    tier_3_structural = {
        "building_era": readable_era,
        "epc_rating": prop.epc_rating,
        "potential_epc_rating": prop.potential_epc_rating,
        "epc_improvement_bands": epc_gap_bands,
        "notes": f"Thermal performance deficit: {epc_gap_bands} band(s) of headroom between current and potential EPC." if epc_gap_bands else "No significant thermal upgrade headroom calculated."
    }

    gate_failure = None
    if prop.has_recorded_covenant is True:
        gate_failure = {
            "label": "GATE FAILURE: Legal / Restrictive Covenant",
            "explanation": "Active covenant recorded on title. Overrides weighted sum."
        }
    elif prop.in_flood_zone_3 is True:
        gate_failure = {
            "label": "GATE FAILURE: Environmental / Flood Zone 3",
            "explanation": "High flood risk boundary intersection. Overrides weighted sum."
        }

    payload = {
        "uprn": prop.uprn,
        "inspireid": prop.inspireid,
        "postcode": prop.postcode,
        "tenure": tier_1_legal["tenure"], 
        "cpsi_score": cpsi,
        "rag_status": rag,
        "system_notes": notes,
        "gate_failure": gate_failure,
        "score_breakdown": breakdown,
        "tiers": {
            "tier_1_legal": tier_1_legal,
            "tier_2_environmental": tier_2_environmental,
            "tier_3_structural": tier_3_structural
        }
    }
    return jsonify({"status": "success", "report": payload}), 200

# --- ROUTE 5: EXECUTIVE STATS ---
@app.route('/api/spatial/stats', methods=['GET'])
def get_bbox_stats():
    bounds = request.args.get('bounds')
    if not bounds:
        return jsonify({"status": "error", "message": "bounds parameter required"}), 400

    w, s, e, n = map(float, bounds.split(','))
    diagonal = bbox_diagonal_metres(w, s, e, n)
    if diagonal is not None and diagonal > BBOX_LIMIT_METRES:
        return jsonify({"status": "error", "message": "Please zoom in to view parcel data."}), 400

    bbox_bng = func.ST_Transform(func.ST_MakeEnvelope(w, s, e, n, 4326), 27700)

    props_in_view = db.session.query(
        BirminghamProperty.epc_rating,
        BirminghamProperty.dominant_building_era,
        BirminghamProperty.tenure,
        BirminghamProperty.has_recorded_covenant,
        BirminghamProperty.in_flood_zone_3
    ).join(
        BirminghamGeometry, BirminghamProperty.inspireid == BirminghamGeometry.inspireid
    ).filter(
        func.ST_Intersects(BirminghamGeometry.geometry, bbox_bng)
    ).limit(2000).all()

    total = len(props_in_view)
    if total == 0:
        return jsonify({"status": "success", "stats": None, "message": "No properties in current view."}), 200

    era_counts = {}
    for p in props_in_view:
        if p.dominant_building_era and p.epc_rating and p.epc_rating.upper() in ('D', 'E', 'F', 'G'):
            era_counts[p.dominant_building_era] = era_counts.get(p.dominant_building_era, 0) + 1
    dominant_era = max(era_counts, key=era_counts.get) if era_counts else None
    dominant_era_pct = round(100 * era_counts[dominant_era] / total, 1) if dominant_era else None

    RETROFIT_COST_PER_PROPERTY_GBP = 8500
    low_epc_count = sum(1 for p in props_in_view if p.epc_rating and p.epc_rating.upper() in ('E', 'F', 'G'))
    estimated_retrofit_cost_gbp = low_epc_count * RETROFIT_COST_PER_PROPERTY_GBP

    legal_w, env_w, econ_w = parse_weights(request.args)
    lh_scores = [calculate_cpsi_score(p, legal_w, env_w, econ_w)[0] for p in props_in_view if p.tenure == 'LH']
    fh_scores = [calculate_cpsi_score(p, legal_w, env_w, econ_w)[0] for p in props_in_view if p.tenure and p.tenure != 'LH']

    payload = {
        "properties_in_view": total,
        "predictive_driver": {
            "dominant_era": dominant_era,
            "pct_of_view_low_epc_in_that_era": dominant_era_pct,
            "narrative": (
                f"{dominant_era_pct}% of properties in this view were built in era '{dominant_era}' "
                f"and carry an EPC rating of D or below."
                if dominant_era else "Insufficient data to identify a dominant driver in this view."
            )
        },
        "retrofit_capex_estimate": {
            "low_epc_property_count": low_epc_count,
            "cost_per_property_assumption_gbp": RETROFIT_COST_PER_PROPERTY_GBP,
            "estimated_total_gbp": estimated_retrofit_cost_gbp
        },
        "tenure_compliance_comparison": {
            "leasehold_avg_cpsi": round(sum(lh_scores) / len(lh_scores), 3) if lh_scores else None,
            "freehold_avg_cpsi": round(sum(fh_scores) / len(fh_scores), 3) if fh_scores else None,
            "leasehold_count": len(lh_scores),
            "freehold_count": len(fh_scores)
        }
    }
    return jsonify({"status": "success", "stats": payload}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)