import os # acts as the hand that reaches out the secure env file. works with dotenv
from flask import Flask, jsonify, request # jsonify is a patsing tool that wraps python data structures into structured json headers. request reads data parameters monitoring the traffic
from flask_sqlalchemy import SQLAlchemy # object relational mapper layer, translating database tables into structured python classes.
from flask_cors import CORS # allows frontend and backend to talk to each other even though they have different origins/servers
from geoalchemy2 import Geometry # geospatial extension for SQLAlchemy, geometry just allows us to map spatial data directly onto it
from geoalchemy2.functions import ST_AsGeoJSON, ST_MakeEnvelope, ST_Intersects, ST_Transform, ST_Area # POSTGIS tools allowing python logic to handle this.
from dotenv import load_dotenv # keep environment variables in safe file instead of hardcoding it
import json # used to handle JavaScript Object notation strings. PostGIS converts my shapes into raw text strings. json will parse that data into actual python dicts to pack into my API features array.
import urllib.parse # used for slicing, parsing and manipulating URLS

# Load environment variables from secure .env file
load_dotenv()
# Using load_dotenv isolates configuration secrets from application logic. 
# It prevents credential leakage 
# in version control repositories, satisfies academic security audits, 
# and allows the application to dynamically change environments without modifying the source code.

app = Flask(__name__)
# Enable CORS so your frontend map interface can request data securely
CORS(app)


# DATABASE CONFIGURATION (SECURED VIA ENV VARIABLES)

db_user = os.getenv("DB_USER", "postgres")
raw_password = os.getenv("DB_PASSWORD", "")
db_host = os.getenv("DB_HOST", "localhost")
db_port = os.getenv("DB_PORT", "5432")
db_name = os.getenv("DB_NAME", "proptrace_msc")

# Safely URL-encode the password string to handle special characters (@, !, etc.)
encoded_password = urllib.parse.quote_plus(raw_password)
# Breaks down URI config text into disctinct database parameters to connect to SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ORM DATABASE MODELS


# 1. Textual Risk Attributes Table (core schema)
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
    tenure = db.Column(db.String(2))


# 2. Spatial Polygons Cadastral Table (geo schema - Running on SRID 27700 British National Grid)
class BirminghamGeometry(db.Model):
    __tablename__ = 'birmingham_polygons'
    __table_args__ = {'schema': 'geo'}

    inspireid = db.Column(db.BigInteger, primary_key=True)
    geometry = db.Column(Geometry(geometry_type='POLYGON', srid=27700))


# =========================================================================
# API ROUTE ENDPOINTS
# =========================================================================

# ROUTE 1: Standard Textual Postcode Query Lookup
@app.route('/api/properties/<postcode>', methods=['GET'])
def get_properties_by_postcode(postcode):
    clean_postcode = postcode.upper().replace("-", " ").replace(" ", "").strip()
    if len(clean_postcode) >= 5:
        formatted_postcode = f"{clean_postcode[:-3]} {clean_postcode[-3:]}"
    else:
        formatted_postcode = clean_postcode

    properties = BirminghamProperty.query.filter_by(postcode=formatted_postcode).all()
    if not properties:
        return jsonify({"status": "error", "message": "No properties found for this postcode"}), 404

    results = []
    for prop in properties:
        results.append({
            "id": prop.id,
            "uprn": prop.uprn,
            "postcode": prop.postcode,
            "epc_rating": prop.epc_rating,
            "potential_epc_rating": prop.potential_epc_rating,
            "dominant_building_era": prop.dominant_building_era,
            "estimated_council_tax_band": prop.estimated_council_tax_band,
            "tenure": prop.tenure
        })

    return jsonify({
        "status": "success", 
        "postcode": formatted_postcode, 
        "count": len(results), 
        "data": results
    }), 200


# ROUTE 2: Bounding Box Viewport Spatial Query
# Direct polygon boundary box selection using dynamic PostGIS coordinate transformation
@app.route('/api/spatial/parcels', methods=['GET'])
def get_parcels_in_bbox():
    """
    ST_Intersects Viewport Engine.
    Intercepts Mapbox bounding box tracks (SRID 4326), projects them to
    British National Grid meters (SRID 27700), enforces a 5 sq km performance 
    safety limit, and returns a compiled geoJSON FeatureCollection.
    """
    min_lng = request.args.get('min_lng', type=float)
    min_lat = request.args.get('min_lat', type=float)
    max_lng = request.args.get('max_lng', type=float)
    max_lat = request.args.get('max_lat', type=float)

    if None in [min_lng, min_lat, max_lng, max_lat]:
        return jsonify({"status": "error", "message": "Missing bounding box dimensions"}), 400

    # A. Generate the search envelope bounding box in global coordinates (WGS84 / SRID 4326)
    bbox_4326 = ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326)
    
    # B. Transform the box coordinates into British National Grid (SRID 27700) to match the polygon table data layout
    bbox_27700 = ST_Transform(bbox_4326, 27700)

    # C. Performance Guardrail: If the view area is too wide (zoomed out too far),
    # return an empty collection with a message to prevent database/browser throttling.
    bbox_area_meters = db.session.query(ST_Area(bbox_27700)).scalar()
    if bbox_area_meters > 5000000:  # Cap threshold at 5 square kilometers
        return jsonify({
            "type": "FeatureCollection",
            "count": 0,
            "features": [],
            "message": "Zoom in further to view parcel geometry data layers."
        }), 200

    # D. Query the intersecting polygon rows directly to fetch shapes inside your screen view window
    query_results = db.session.query(
        BirminghamGeometry.inspireid,
        ST_AsGeoJSON(ST_Transform(BirminghamGeometry.geometry, 4326)).label('geojson_geom')
    ).filter(
        ST_Intersects(BirminghamGeometry.geometry, bbox_27700)
    ).limit(150).all()  # Safeguard cap optimized for visual rendering stability

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
    app.run(debug=True, port=5000)