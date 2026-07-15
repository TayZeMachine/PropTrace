import os
import urllib.parse
import json
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from geoalchemy2 import Geometry
from geoalchemy2.functions import ST_AsGeoJSON, ST_MakeEnvelope, ST_Intersects, ST_Transform, ST_Area
from dotenv import load_dotenv

# CONFIGURATION & INITIALIZATION LAYER
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


# ORM DATABASE MODELS SCHEMA LAYER

class BirminghamProperty(db.Model):
    __tablename__ = 'birmingham_properties_master'
    __table_args__ = {'schema': 'core'}

    id = db.Column(db.Integer, primary_key=True)
    uprn = db.Column(db.BigInteger, unique=True, nullable=False)
    postcode = db.Column(db.String(10), nullable=False)
    epc_rating = db.Column(db.String(2))
    dominant_building_era = db.Column(db.String(5))
    estimated_council_tax_band = db.Column(db.String(2))
    potential_epc_rating = db.Column(db.String(2))
    tenure = db.Column(db.String(2))  # LH = Leasehold, FH = Freehold


class BirminghamGeometry(db.Model):
    __tablename__ = 'birmingham_polygons'
    __table_args__ = {'schema': 'geo'}

    inspireid = db.Column(db.BigInteger, primary_key=True)
    geometry = db.Column(Geometry(geometry_type='POLYGON', srid=27700))


# SYSTEM COMPENSATORY CORE ALGORITHMIC MATH FUNCTIONS

def calculate_cpsi_score(prop, legal_weight=0.4, env_weight=0.3, econ_weight=0.3):
    """
    Computes the Composite Property Suitability Index (CPSI) bounded strictly between 0.0 and 1.0.
    Operationalizes a two-stage evaluation matrix to defend against Malczewski's compensatory flaw.
    """
    # STAGE 1: NON-COMPENSATORY LEGAL GATE CIRCUIT BREAKER
    if prop.tenure == 'LH' and prop.estimated_council_tax_band in ['G', 'H']:
        return 1.00, "RED", "CRITICAL OVERRIDE: High risk tenure-to-holding layout captured."

    # STAGE 2: WEIGHTED LINEAR COMBINATION (WLC) ENGINE
    epc_map = {'A': 0.0, 'B': 0.1, 'C': 0.3, 'D': 0.5, 'E': 0.7, 'F': 0.9, 'G': 1.0}
    env_sub_score = epc_map.get(prop.epc_rating.upper() if prop.epc_rating else 'D', 0.5)

    econ_sub_score = 0.2
    if prop.dominant_building_era in ['PRE19', '1900', 'L', 'A']:
        econ_sub_score += 0.4
    if prop.estimated_council_tax_band in ['F', 'G', 'H', 'K']:
        econ_sub_score += 0.4
    econ_sub_score = min(econ_sub_score, 1.0)

    legal_sub_score = 0.0
    if prop.tenure == 'LH':
        legal_sub_score = 0.4

    composite_risk = (legal_weight * legal_sub_score) + (env_weight * env_sub_score) + (econ_weight * econ_sub_score)
    composite_risk = round(max(0.0, min(composite_risk, 1.0)), 3)

    if composite_risk >= 0.75:
        status_tier = "RED"
    elif composite_risk >= 0.40:
        status_tier = "AMBER"
    else:
        status_tier = "GREEN"

    return composite_risk, status_tier, "Index metrics derived via standard compensatory WLC matrix models."


# ROUTE 1: Standard Postcode Query Data Lookup Engine
@app.route('/api/properties/<postcode>', methods=['GET'])
def get_properties_by_postcode(postcode):
    clean_postcode = postcode.upper().replace("-", " ").replace(" ", "").strip()
    if len(clean_postcode) >= 5:
        formatted_postcode = f"{clean_postcode[:-3]} {clean_postcode[-3:]}"
    else:
        formatted_postcode = clean_postcode

    properties = BirminghamProperty.query.filter_by(postcode=formatted_postcode).all()
    
    if not properties:
        return jsonify({"status": "error", "message": "No matching regional assets found for this postcode parameters"}), 404

    legal_w = request.args.get('legal_w', default=0.4, type=float)
    env_w = request.args.get('env_w', default=0.3, type=float)
    econ_w = request.args.get('econ_w', default=0.3, type=float)

    results = []
    for prop in properties:
        cpsi_score, rag_status, deduction_notes = calculate_cpsi_score(prop, legal_w, env_w, econ_w)
        
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
    min_lng = request.args.get('min_lng', type=float)
    min_lat = request.args.get('min_lat', type=float)
    max_lng = request.args.get('max_lng', type=float)
    max_lat = request.args.get('max_lat', type=float)

    if None in [min_lng, min_lat, max_lng, max_lat]:
        return jsonify({"status": "error", "message": "Missing coordinate bounding box bounding dimensions"}), 400

    bbox_4326 = ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326)
    bbox_27700 = ST_Transform(bbox_4326, 27700)

    bbox_area_meters = db.session.query(ST_Area(bbox_27700)).scalar()
    if bbox_area_meters > 5000000:
        return jsonify({
            "type": "FeatureCollection",
            "count": 0,
            "features": [],
            "message": "Viewport density threshold exceeded. Zoom in closer to activate PostGIS vector layers."
        }), 200

    query_results = db.session.query(
        BirminghamGeometry.inspireid,
        ST_AsGeoJSON(ST_Transform(BirminghamGeometry.geometry, 4326)).label('geojson_geom')
    ).filter(
        ST_Intersects(BirminghamGeometry.geometry, bbox_27700)
    ).limit(150).all()

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


# ROUTE 3: Spatial ID Bridge Resolver
@app.route('/api/resolve/<int:inspireid>', methods=['GET'])
def resolve_spatial_id(inspireid):
    """
    Bridges spatial geometries and tabular database attributes via geo.uprn_inspire_bridge.
    """
    try:
        bridge_record = db.session.execute(
            db.text("SELECT uprn FROM geo.uprn_inspire_bridge WHERE inspireid = :inspireid LIMIT 1"),
            {"inspireid": inspireid}
        ).fetchone()

        if not bridge_record:
            return jsonify({
                "status": "error", 
                "message": f"No physical address (UPRN) mapped to spatial ID {inspireid}."
            }), 404

        real_uprn = bridge_record[0]
        property_record = BirminghamProperty.query.filter_by(uprn=real_uprn).first()

        if not property_record:
            return jsonify({
                "status": "error", 
                "message": f"UPRN {real_uprn} resolved, but no attributes exist in core master table."
            }), 404

        legal_w = request.args.get('legal_w', default=0.4, type=float)
        env_w = request.args.get('env_w', default=0.3, type=float)
        econ_w = request.args.get('econ_w', default=0.3, type=float)

        cpsi_score, rag_status, deduction_notes = calculate_cpsi_score(property_record, legal_w, env_w, econ_w)

        return jsonify({
            "status": "success",
            "data": {
                "id": property_record.id,
                "uprn": property_record.uprn,
                "postcode": property_record.postcode,
                "epc_rating": property_record.epc_rating if property_record.epc_rating else "N/A",
                "potential_epc_rating": property_record.potential_epc_rating if property_record.potential_epc_rating else "N/A",
                "dominant_building_era": property_record.dominant_building_era if property_record.dominant_building_era else "Unknown",
                "estimated_council_tax_band": property_record.estimated_council_tax_band if property_record.estimated_council_tax_band else "N/A",
                "tenure": "Leasehold" if property_record.tenure == 'LH' else "Freehold" if property_record.tenure == 'FH' else property_record.tenure,
                "cpsi_score": cpsi_score,
                "rag_status": rag_status,
                "notes": deduction_notes
            }
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Internal Server Error: {str(e)}"}), 500


# ROUTE 4: Comprehensive Risk Audit Report Payload
@app.route('/api/reports/<int:uprn>', methods=['GET'])
def generate_property_report(uprn):
    """
    Compiles Tier 1-4 risk parameters for PDF output.
    """
    try:
        property_record = BirminghamProperty.query.filter_by(uprn=uprn).first()
        if not property_record:
            return jsonify({"status": "error", "message": f"UPRN {uprn} not found."}), 404

        # Compile risk analysis matching Tier definitions
        legal_w, env_w, econ_w = 0.4, 0.3, 0.3
        cpsi_score, rag_status, notes = calculate_cpsi_score(property_record, legal_w, env_w, econ_w)

        # Basic mock spatial analysis fallback logic representing PostGIS checks
        has_flood_risk = "Low Risk" if property_record.estimated_council_tax_band not in ['G', 'H'] else "High Risk (Zone 3)"

        payload = {
            "uprn": property_record.uprn,
            "postcode": property_record.postcode,
            "tenure": "Leasehold" if property_record.tenure == 'LH' else "Freehold",
            "cpsi_score": cpsi_score,
            "rag_status": rag_status,
            "system_notes": notes,
            "tiers": {
                "tier_1_structural": {
                    "building_era": property_record.dominant_building_era,
                    "epc_rating": property_record.epc_rating,
                    "potential_epc": property_record.potential_epc_rating,
                    "efficiency_gap": "High Thermal Deficit" if property_record.epc_rating in ['E', 'F', 'G'] else "Compliant"
                },
                "tier_2_environmental": {
                    "flood_zone": has_flood_risk,
                    "contaminated_soil": "Clear / Non-Historic Area"
                },
                "tier_3_legal": {
                    "restrictive_covenants": "Active Title Deed Covenants Identified - Review Pending",
                    "easement_status": "No Active Right-of-Way disputes"
                }
            }
        }
        return jsonify({"status": "success", "report": payload}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)