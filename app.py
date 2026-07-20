import os
import urllib.parse
import json
from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from geoalchemy2 import Geometry
from geoalchemy2.functions import ST_AsGeoJSON, ST_MakeEnvelope, ST_Intersects, ST_Transform, ST_Area, ST_Touches
from sqlalchemy import text, func
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app)

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
    inspireid = db.Column(db.BigInteger)  # backfilled directly via spatial ST_Contains join, not via uprn_inspire_bridge
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    epc_rating = db.Column(db.String(2))
    dominant_building_era = db.Column(db.String(5))
    estimated_council_tax_band = db.Column(db.String(2))
    potential_epc_rating = db.Column(db.String(2))
    tenure = db.Column(db.String(2))

class BirminghamGeometry(db.Model):
    __tablename__ = 'birmingham_polygons'
    __table_args__ = {'schema': 'geo'}
    inspireid = db.Column(db.BigInteger, primary_key=True)
    geometry = db.Column(Geometry(geometry_type='POLYGON', srid=27700))  # confirmed via ST_Extent(): genuinely British National Grid

class UprnInspireBridge(db.Model):
    """LEGACY — no longer used in any route. Its uprn column is on the
    internal 32xxxxxx numbering scheme, not the national UPRNs used
    everywhere else post-NSUL-migration, so joining on it against
    BirminghamProperty.uprn silently matched almost nothing. Kept only in
    case something elsewhere still references the raw table; routes now use
    BirminghamProperty.inspireid directly instead."""
    __tablename__ = 'uprn_inspire_bridge'
    __table_args__ = {'schema': 'geo'}
    inspireid = db.Column(db.BigInteger, primary_key=True)
    uprn = db.Column(db.BigInteger, primary_key=True)

# --- WEIGHT PARSING (Stage 2 WLC sliders) ---
def parse_weights(args):
    """Reads legal/env/econ weights from query params (dashboard sliders) and
    normalizes them to sum to 1.0 regardless of what the frontend sends, so a
    slider combination can never silently break the composite score math."""
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


# --- 5KM BBOX SAFETY GATE ---
BBOX_LIMIT_METRES = 5000

def bbox_diagonal_metres(w, s, e, n):
    """Great-circle distance between the SW and NE corners of the requested
    bbox, in metres. Used to reject overly-wide viewport queries before they
    hit the spatial join."""
    result = db.session.execute(
        text("""
            SELECT ST_Distance(
                ST_SetSRID(ST_MakePoint(:w, :s), 4326)::geography,
                ST_SetSRID(ST_MakePoint(:e, :n), 4326)::geography
            )
        """),
        {"w": w, "s": s, "e": e, "n": n}
    ).scalar()
    return result


# --- CPSI SCORING ENGINE ---
def calculate_cpsi_score(prop, legal_weight=0.4, env_weight=0.3, econ_weight=0.3):
    # STAGE 1: Non-compensatory legal gate.
    # NOTE: estimated_council_tax_band is still unsourced — no table in this
    # project provides it (flagged when we first hit it; still your decision:
    # source the VOA Council Tax Valuation List separately, drop the field,
    # or use price as an explicitly-labelled proxy). Until that's resolved,
    # this condition can never be true and the gate is structurally present
    # but inert. Left as-is rather than silently substituting a different
    # trigger — that's a real modelling decision, not mine to make for you.
    if prop.tenure == 'LH' and prop.estimated_council_tax_band in ['G', 'H']:
        return 1.00, "RED", "CRITICAL OVERRIDE: High risk tenure-to-holding layout captured."

    epc_map = {'A': 0.0, 'B': 0.1, 'C': 0.3, 'D': 0.5, 'E': 0.7, 'F': 0.9, 'G': 1.0}
    env_sub_score = epc_map.get(prop.epc_rating.upper() if prop.epc_rating else 'D', 0.5)

    econ_sub_score = 0.2
    if prop.dominant_building_era in ['PRE19', '1900', 'L', 'A']:
        econ_sub_score += 0.4
    if prop.estimated_council_tax_band in ['F', 'G', 'H', 'K']:
        econ_sub_score += 0.4
    econ_sub_score = min(econ_sub_score, 1.0)

    legal_sub_score = 0.4 if prop.tenure == 'LH' else 0.1

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
    clean_postcode = postcode.upper().replace("-", "").replace(" ", "").strip()

    # Compare fully-stripped postcode on both sides rather than trying to
    # reconstruct a single "correct" spacing convention — more robust against
    # whatever spacing the source data actually stored.
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
            "tenure": prop.tenure,
            "rag_status": rag,
            "cpsi_score": cpsi,
            "geometry_geojson": geojson  # may be null — property matched but has no parcel geometry yet
        })

    return jsonify({"status": "success", "properties": results}), 200


# --- ROUTE 2: BBOX SEARCH WITH ARBITRAGE FILTERS ---
@app.route('/api/spatial/parcels', methods=['GET'])
def get_parcels_in_bbox():
    bounds = request.args.get('bounds')
    arbitrage_mode = request.args.get('filter') # 'retrofit' or 'hmo'
    
    if not bounds:
        return jsonify({"status": "error"}), 400
    
    w, s, e, n = map(float, bounds.split(','))

    diagonal = bbox_diagonal_metres(w, s, e, n)
    if diagonal is not None and diagonal > BBOX_LIMIT_METRES:
        return jsonify({"status": "error", "message": "Please zoom in to view parcel data."}), 400

    bbox_poly = ST_MakeEnvelope(w, s, e, n, 4326)

    # Diagnostic: how many properties actually fall in this bbox by
    # coordinate alone (nearly all rows have lat/long), versus how many have
    # a matched polygon to actually draw. Cheap, and answers "is this a join
    # bug or a data-coverage gap" without a separate round trip.
    total_in_bbox = db.session.query(BirminghamProperty).filter(
        BirminghamProperty.longitude >= w, BirminghamProperty.longitude <= e,
        BirminghamProperty.latitude >= s, BirminghamProperty.latitude <= n
    ).count()

    base_query = db.session.query(
        BirminghamProperty,
        ST_AsGeoJSON(ST_Transform(BirminghamGeometry.geometry, 4326)).label('geojson')
    ).join(
        BirminghamGeometry, BirminghamProperty.inspireid == BirminghamGeometry.inspireid
    ).filter(ST_Intersects(ST_Transform(BirminghamGeometry.geometry, 4326), bbox_poly))

    # ARBITRAGE FILTERING LOGIC
    if arbitrage_mode == 'retrofit':
        base_query = base_query.filter(BirminghamProperty.epc_rating.in_(['E', 'F', 'G']))
    elif arbitrage_mode == 'hmo':
        base_query = base_query.filter(BirminghamProperty.estimated_council_tax_band.in_(['A', 'B']))

    query_results = base_query.limit(150).all()

    legal_w, env_w, econ_w = parse_weights(request.args)

    features = []
    for prop, geojson in query_results:
        cpsi, rag, notes = calculate_cpsi_score(prop, legal_w, env_w, econ_w)
        features.append({
            "type": "Feature",
            "geometry": json.loads(geojson),
            "properties": {
                "uprn": prop.uprn,
                "inspireid": prop.inspireid,
                "rag_status": rag
            }
        })

    return jsonify({
        "type": "FeatureCollection",
        "features": features,
        "debug": {"properties_in_bbox_by_coordinate": total_in_bbox, "properties_with_renderable_geometry": len(features)}
    }), 200


# --- ROUTE 3: SITE ASSEMBLY ENGINE (ST_TOUCHES) ---
@app.route('/api/site-assembly/<int:inspireid>', methods=['GET'])
def site_assembly(inspireid):
    """Finds all contiguous plots sharing a boundary with the target ID."""
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


# --- ROUTE 4: REPORT/CLICK METADATA (3-TIER AUDIT) ---
@app.route('/api/property/report/<int:uprn>', methods=['GET'])
def get_property_report(uprn):
    prop = BirminghamProperty.query.filter_by(uprn=uprn).first()
    if not prop:
        return jsonify({"status": "error"}), 404

    legal_w, env_w, econ_w = parse_weights(request.args)
    cpsi, rag, notes = calculate_cpsi_score(prop, legal_w, env_w, econ_w)

    inspireid = prop.inspireid

    # --- Tier 1: Structural & Energy Performance ---
    epc_order = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6}
    current_rank = epc_order.get((prop.epc_rating or '').upper())
    potential_rank = epc_order.get((prop.potential_epc_rating or '').upper())
    epc_gap_bands = (current_rank - potential_rank) if (current_rank is not None and potential_rank is not None) else None

    tier_1_structural = {
        "building_era": prop.dominant_building_era,
        "epc_rating": prop.epc_rating,
        "potential_epc_rating": prop.potential_epc_rating,
        "epc_improvement_bands": epc_gap_bands,
        "notes": f"Thermal performance deficit: {epc_gap_bands} band(s) of headroom between current and potential EPC." if epc_gap_bands else None
    }

    # --- Tier 2: Spatial & Environmental Hazards ---
    # Not yet sourced: no flood zone / brownfield layer is ingested into this
    # schema. Structured so a future EA Flood API / brownfield ingest can
    # slot straight into this shape without a breaking change.
    tier_2_environmental = {
        "data_available": False,
        "status_label": "Pending EA Ingest",
        "flood_zone": None,
        "contaminated_land_flag": None,
        "notes": "Environmental hazard data not yet integrated — pending Environment Agency flood zone / brownfield ingest."
    }

    # --- Tier 3: Legal & Tenure Restrictions ---
    tier_3_legal = {
        "tenure": "Leasehold" if prop.tenure == 'LH' else ("Freehold" if prop.tenure else None),
        "notes": "Leasehold tenure typically carries mandatory structural maintenance fund obligations; Freehold relies on individual capital." if prop.tenure else None
    }

    payload = {
        "uprn": prop.uprn,
        "inspireid": inspireid,
        "postcode": prop.postcode,
        "tenure": tier_3_legal["tenure"],  # kept at top level too — index.html reads p.tenure directly today
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

# --- ROUTE 5: EXECUTIVE RISK ASSESSMENT — REAL BBOX AGGREGATION ---
@app.route('/api/spatial/stats', methods=['GET'])
def get_bbox_stats():
    """Computed, live equivalent of the 'Executive Risk Assessment' cards —
    every figure here is derived from the properties actually in view, not a
    fixed narrative string. Reuses the same 5km gate as Route 2."""
    bounds = request.args.get('bounds')
    if not bounds:
        return jsonify({"status": "error", "message": "bounds parameter required"}), 400

    w, s, e, n = map(float, bounds.split(','))

    diagonal = bbox_diagonal_metres(w, s, e, n)
    if diagonal is not None and diagonal > BBOX_LIMIT_METRES:
        return jsonify({"status": "error", "message": "Please zoom in to view parcel data."}), 400

    bbox_poly = ST_MakeEnvelope(w, s, e, n, 4326)

    props_in_view = db.session.query(BirminghamProperty).join(
        BirminghamGeometry, BirminghamProperty.inspireid == BirminghamGeometry.inspireid
    ).filter(
        ST_Intersects(ST_Transform(BirminghamGeometry.geometry, 4326), bbox_poly)
    ).limit(2000).all()

    total = len(props_in_view)
    if total == 0:
        return jsonify({"status": "success", "stats": None, "message": "No properties in current view."}), 200

    # Q1 — Predictive driver: genuine correlation between building era and
    # sub-D EPC ratings among properties actually in view, not a fixed string.
    era_counts = {}
    for p in props_in_view:
        if p.dominant_building_era and p.epc_rating and p.epc_rating.upper() in ('D', 'E', 'F', 'G'):
            era_counts[p.dominant_building_era] = era_counts.get(p.dominant_building_era, 0) + 1
    dominant_era = max(era_counts, key=era_counts.get) if era_counts else None
    dominant_era_pct = round(100 * era_counts[dominant_era] / total, 1) if dominant_era else None

    # Q2 — Retrofit capex estimate: real E/F/G count x a documented assumption
    # (not a discovered fact — label it as an estimate wherever it's shown).
    RETROFIT_COST_PER_PROPERTY_GBP = 8500
    low_epc_count = sum(1 for p in props_in_view if p.epc_rating and p.epc_rating.upper() in ('E', 'F', 'G'))
    estimated_retrofit_cost_gbp = low_epc_count * RETROFIT_COST_PER_PROPERTY_GBP

    # Q3 — Tenure compliance comparison: real average CPSI score per tenure
    # type among properties in view.
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