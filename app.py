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
    ST_SetSRID,
    ST_MakePoint,
    ST_Centroid,
    # [UPDATED] Replaced ST_Simplify with ST_SimplifyPreserveTopology to prevent invalid geometries
    ST_SimplifyPreserveTopology 
)
# [PERF] ST_Distance dropped — bbox_diagonal_metres no longer round-trips the DB (see below).

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
db = SQLAlchemy(app)

@app.route('/')
def home():
    return render_template('index.html')

# --- ORM MODELS ---
class BirminghamProperty(db.Model):
    __tablename__ = 'birmingham_properties_master'
    __table_args__ = {'schema': 'core'}
    id = db.Column(db.Integer, primary_key=True)
    uprn = db.Column(db.BigInteger, unique=True, nullable=False)
    postcode = db.Column(db.String(10), nullable=False)
    inspireid = db.Column(db.BigInteger) 
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    epc_rating = db.Column(db.String(2))
    dominant_building_era = db.Column(db.String(5))
    potential_epc_rating = db.Column(db.String(2))
    tenure = db.Column(db.String(2))
    # [FIX] No default=False — a row that has never had this field checked
    # must be able to store NULL. Silently defaulting an unsourced field to
    # False makes "we never checked" and "we checked and it's clear" render
    # identically downstream (sidebar, PDF), which is a false-assurance bug,
    # not a cosmetic one. NULL now means "not yet sourced"; True/False mean
    # an actual verified result.
    has_recorded_covenant = db.Column(db.Boolean, nullable=True)
    in_flood_zone_3 = db.Column(db.Boolean, nullable=True)

class BirminghamGeometry(db.Model):
    __tablename__ = 'birmingham_polygons'
    __table_args__ = {'schema': 'geo'}
    inspireid = db.Column(db.BigInteger, primary_key=True)
    geometry = db.Column(Geometry(geometry_type='POLYGON', srid=27700))

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
    """Great-circle diagonal of the viewport.

    [PERF] This used to be a round-trip to Postgres (ST_Distance on two
    ST_MakePoint/geography casts) on every single /parcels and /stats
    request. That's a full network+planner+executor round trip just to
    evaluate a haversine formula on four floats already sitting in memory.
    Computing it in Python removes that round trip entirely — worth doing
    even before anything else, since it's on the hot path of *every*
    pan/zoom event.
    """
    lat1, lat2 = math.radians(s), math.radians(n)
    dlat = math.radians(n - s)
    dlng = math.radians(e - w)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    a = min(1.0, max(0.0, a))  # guard against float rounding pushing a fractionally out of [0,1]
    return 2 * _EARTH_RADIUS_METRES * math.asin(math.sqrt(a))


def simplify_profile_for_zoom(zoom):
    """Zoom-adaptive (tolerance_degrees, geojson_coordinate_precision).

    [PERF] A single fixed 0.00001 simplify tolerance and Postgres's default
    9-decimal-place GeoJSON precision were being used at every zoom level.
    At low zoom (zoomed-out, wide viewport) that's massive over-precision —
    9 decimal places of a WGS84 degree is sub-millimetre, transmitted for
    every vertex of every polygon, for boundaries the user can't
    perceptually distinguish at that scale. Coarsening both simplification
    and coordinate precision at low zoom cuts payload size and
    ST_SimplifyPreserveTopology CPU cost substantially, while full fidelity
    is preserved once the user is zoomed in enough to actually see parcel
    boundaries clearly.
    """
    try:
        zoom = float(zoom)
    except (TypeError, ValueError):
        zoom = 13.0
    if zoom < 14:
        return 0.00015, 5   # ~15m tolerance, ~1.1m coordinate precision
    elif zoom < 16:
        return 0.00003, 6   # ~3m tolerance, ~11cm coordinate precision
    else:
        return 0.000005, 7  # ~0.5m tolerance, near-full topology fidelity


# --- [UPDATED] VOA ERA DICTIONARY MAPPING ---
# Cleaned up to reflect the exact date ranges from the VOA source dataset
era_map = {
    'A': 'Pre-1900', 
    'B': '1900-1918', 
    'C': '1919-1929',
    'D': '1930-1939', 
    'E': '1945-1954', 
    'F': '1955-1964',
    'G': '1965-1972', 
    'H': '1973-1982', 
    'I': '1983-1992',
    'J': '1993-1999', 
    'K': '2000-2008', 
    'L': '2009-2021'
}

# --- CPSI SCORING ENGINE ---
def calculate_cpsi_score(prop, legal_weight=0.4, env_weight=0.3, econ_weight=0.3):
    """Executes the two-stage hybrid MCDA framework to compute property risk."""
    
    # STAGE 1 (Non-Compensatory Gates): Instant overrides for critical hazards.
    # These columns are now nullable (None = not sourced). None is falsy in
    # Python, so an unsourced parcel correctly does NOT trigger a RED override
    # here — it just isn't scored as risky by the *number*. The report-facing
    # tri-state labelling below is what stops it from being described as
    # "clear" in the PDF/sidebar copy, which is a separate concern from the
    # numeric score.
    if getattr(prop, 'has_recorded_covenant', False):
        return 1.00, "RED", "CRITICAL OVERRIDE: Active restrictive covenant detected on Land Registry title."
    
    if getattr(prop, 'in_flood_zone_3', False):
        return 1.00, "RED", "CRITICAL OVERRIDE: Property intersects EA Flood Zone 3 (High Risk)."

    # STAGE 2 (Compensatory Weights): Base normalization mappings
    epc_map = {'A': 0.0, 'B': 0.1, 'C': 0.3, 'D': 0.5, 'E': 0.7, 'F': 0.9, 'G': 1.0}
    env_sub_score = epc_map.get((prop.epc_rating or '').upper(), 0.5)

    # [UPDATED] Removed dead string checks, aligned with single-char VOA dict
    era_code = (prop.dominant_building_era or '').upper().strip()
    era_score = 0.2  # Default base score if unknown
    
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

    econ_sub_score = min(era_score, 1.0)
    
    # Legal sub-score adds fractional risk to leaseholds
    legal_sub_score = 0.4 if prop.tenure == 'LH' else 0.1

    # WLC Algebra & RAG Status Compilation
    composite_risk = (legal_weight * legal_sub_score) + (env_weight * env_sub_score) + (econ_weight * econ_sub_score)
    composite_risk = round(max(0.0, min(composite_risk, 1.0)), 3)

    if composite_risk >= 0.75:
        rag = "RED"
    elif composite_risk >= 0.40:
        rag = "AMBER"
    else:
        rag = "GREEN"

    return composite_risk, rag, "Index metrics derived via standard compensatory WLC matrix models."


# --- ROUTE 1: POSTCODE SEARCH ---
@app.route('/api/properties/<postcode>', methods=['GET'])
def get_properties_by_postcode(postcode):
    """Normalized text search resolving to spatial features."""
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
        cpsi, rag, notes = calculate_cpsi_score(prop, legal_w, env_w, econ_w)
        results.append({
            "uprn": prop.uprn,
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


# --- ROUTE 2: BBOX SEARCH WITH FIXED ARBITRAGE FILTERS ---
#
# [PERF] This route was rewritten from the ORM version for three reasons:
#
# 1. The old WHERE clause did ST_Intersects(ST_Transform(geometry, 4326), bbox_4326) —
#    transforming EVERY candidate polygon out of its native 27700 SRID before
#    comparing it. That defeats a GiST index on the raw `geometry` column,
#    because the index is built on 27700 coordinates, not the on-the-fly
#    reprojected ones. Transforming the (tiny, single) *viewport* bbox into
#    27700 instead, and comparing it directly against the untouched
#    `geometry` column, lets Postgres use the GiST index as intended.
#
# 2. ST_SimplifyPreserveTopology + ST_AsGeoJSON were in the SELECT list of a
#    query with ORDER BY + LIMIT — with the ORM building one flat SELECT,
#    there's no boundary stopping Postgres from evaluating those (relatively
#    expensive) functions on every row that matches the spatial filter
#    before sorting/limiting. Structuring it as an inner query that does the
#    filter + order + LIMIT 350 first, wrapped by an outer SELECT that only
#    then simplifies/serializes, guarantees those functions run at most 350
#    times per request, no matter how many thousands of parcels are in view.
#
# 3. Column projection — the ORM was hydrating full BirminghamProperty
#    model instances (every column) for up to 350 rows just to read 7
#    fields out of each. The raw query selects only what's rendered.
@app.route('/api/spatial/parcels', methods=['GET'])
def get_parcels_in_bbox():
    """Live spatial intersection query serving the Mapbox GL JS frontend."""
    bounds = request.args.get('bounds')
    arbitrage_mode = request.args.get('filter')  # 'retrofit' or 'hmo'
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

    # arbitrage_mode is constrained to two known enum values above, so this
    # is a fixed, safe SQL fragment — never built from raw user input.
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
            -- Ultra-fast numeric coordinate distance directly on lat/long
            -- columns avoids running ST_Centroid on complex geometry polygons
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
        cpsi, rag, notes = calculate_cpsi_score(row, legal_w, env_w, econ_w)
        features.append({
            "type": "Feature",
            "id": row.inspireid,  # lets Mapbox GL use setFeatureState for cheap re-styling
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

    # [PERF] The old COUNT() over the full lat/long range ran on every single
    # request just to populate a debug field never shown in the main UI.
    # Gated behind ?debug=1 so production panning doesn't pay for it.
    if include_debug:
        total_in_bbox = db.session.query(BirminghamProperty).filter(
            BirminghamProperty.longitude >= w, BirminghamProperty.longitude <= e,
            BirminghamProperty.latitude >= s, BirminghamProperty.latitude <= n
        ).count()
        payload["debug"] = {
            "properties_in_bbox_by_coordinate": total_in_bbox,
            "properties_with_renderable_geometry": len(features)
        }

    return jsonify(payload), 200


# --- ROUTE 3: SITE ASSEMBLY ENGINE ---
@app.route('/api/site-assembly/<int:inspireid>', methods=['GET'])
def site_assembly(inspireid):
    """Executes an ST_Touches spatial join to find contiguous plots."""
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
    """Populates the detailed sidebar and PDF audit templates."""
    prop = BirminghamProperty.query.filter_by(uprn=uprn).first()
    if not prop:
        return jsonify({"status": "error"}), 404

    legal_w, env_w, econ_w = parse_weights(request.args)
    cpsi, rag, notes = calculate_cpsi_score(prop, legal_w, env_w, econ_w)

    epc_order = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6}
    current_rank = epc_order.get((prop.epc_rating or '').upper())
    potential_rank = epc_order.get((prop.potential_epc_rating or '').upper())
    epc_gap_bands = (current_rank - potential_rank) if (current_rank is not None and potential_rank is not None) else None

    # [UPDATED] Uses the global era_map dictionary cleanly
    readable_era = era_map.get(prop.dominant_building_era, prop.dominant_building_era or 'Not sourced')

    tier_1_structural = {
        "building_era": readable_era,
        "epc_rating": prop.epc_rating,
        "potential_epc_rating": prop.potential_epc_rating,
        "epc_improvement_bands": epc_gap_bands,
        "notes": f"Thermal performance deficit: {epc_gap_bands} band(s) of headroom between current and potential EPC." if epc_gap_bands else "No significant thermal upgrade headroom calculated."
    }

    # [FIX] Tri-state, not boolean. `is None` means the EA flood layer was
    # never sourced for this parcel — that must never render as "low risk",
    # because we don't actually know that.
    flood_flag = prop.in_flood_zone_3
    if flood_flag is True:
        tier_2_environmental = {
            "data_available": True,
            "status_label": "FLOOD ZONE 3 (HIGH RISK)",
            "is_high_risk": True,
            "is_verified": True,
            "notes": "Property falls within EA Flood Zone 3 (high probability of river/sea flooding)."
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
            "notes": "Environment Agency flood zone data not yet sourced for this parcel — treat as unknown, not low risk."
        }

    # [FIX] Same tri-state treatment for the legal title gate. `has_covenant`
    # driving the "CLEAR TITLE" badge used to collapse NULL and False into
    # the same "no covenant" outcome — see calculate_cpsi_score/report notes
    # above. This is the one that produced the "CLEAR TITLE ... Verified
    # against HM Land Registry" contradiction next to a "Not sourced" tenure
    # field in the generated PDF.
    covenant_flag = prop.has_recorded_covenant
    if covenant_flag is True:
        tier_3_legal = {
            "tenure": "Leasehold" if prop.tenure == 'LH' else ("Freehold" if prop.tenure else "Not sourced"),
            "has_covenant": True,
            "is_verified": True,
            "status_label": "RESTRICTIVE COVENANT",
            "notes": "Active restrictive covenants recorded on Land Registry Title."
        }
    elif covenant_flag is False:
        tier_3_legal = {
            "tenure": "Leasehold" if prop.tenure == 'LH' else ("Freehold" if prop.tenure else "Not sourced"),
            "has_covenant": False,
            "is_verified": True,
            "status_label": "CLEAR TITLE",
            "notes": "No title encumbrances or recorded covenants detected."
        }
    else:
        tier_3_legal = {
            "tenure": "Leasehold" if prop.tenure == 'LH' else ("Freehold" if prop.tenure else "Not sourced"),
            "has_covenant": False,
            "is_verified": False,
            "status_label": "NOT VERIFIED",
            "notes": "Land Registry covenant data not yet sourced for this title — treat as unknown, not clear."
        }

    payload = {
        "uprn": prop.uprn,
        "inspireid": prop.inspireid,
        "postcode": prop.postcode,
        "tenure": tier_3_legal["tenure"], 
        "cpsi_score": cpsi,
        "rag_status": rag,
        "system_notes": notes,
        "tiers": {
            "tier_1_structural": tier_1_structural,
            "tier_2_environmental": tier_2_environmental,
            "tier_3_legal": tier_3_legal
        }
    }
    return jsonify({"status": "success", "report": payload}), 200


# --- ROUTE 5: EXECUTIVE RISK ASSESSMENT ---
@app.route('/api/spatial/stats', methods=['GET'])
def get_bbox_stats():
    bounds = request.args.get('bounds')
    if not bounds:
        return jsonify({"status": "error", "message": "bounds parameter required"}), 400

    w, s, e, n = map(float, bounds.split(','))

    diagonal = bbox_diagonal_metres(w, s, e, n)
    if diagonal is not None and diagonal > BBOX_LIMIT_METRES:
        return jsonify({"status": "error", "message": "Please zoom in to view parcel data."}), 400

    bbox_poly = ST_MakeEnvelope(w, s, e, n, 4326)

    bbox_bng = func.ST_Transform(func.ST_MakeEnvelope(w, s, e, n, 4326), 27700)

    # [PERF] This used to hydrate full BirminghamProperty ORM instances
    # (every column, incl. geometry-adjacent fields) for up to 2000 rows on
    # every executive-tab open AND every subsequent pan while that tab stays
    # open. calculate_cpsi_score only ever touches 5 fields, so project just
    # those instead of paying for a full row hydration each time.
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