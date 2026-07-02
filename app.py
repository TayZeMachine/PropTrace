from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# 🔌 Link directly to your local enriched PostgreSQL database warehouse
app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://postgres:Mahdia123!@localhost:5432/proptrace_msc"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 📑 Define the Object-Relational Model mapping to your core production table
class BirminghamProperty(db.Model):
    __tablename__ = 'birmingham_properties_master'
    __table_args__ = {'schema': 'core'}
    
    id = db.Column(db.Integer, primary_key=True)
    uprn = db.Column(db.BigInteger, nullable=False)
    postcode = db.Column(db.String(10), nullable=False)
    tenure = db.Column(db.String(5))
    epc_rating = db.Column(db.String(5))
    potential_epc_rating = db.Column(db.String(5))
    dominant_building_era = db.Column(db.String(5))
    estimated_council_tax_band = db.Column(db.String(5))

    def to_dict(self):
        return {
            "id": self.id,
            "uprn": self.uprn,
            "postcode": self.postcode,
            "tenure": self.tenure,
            "epc_rating": self.epc_rating,
            "potential_epc_rating": self.potential_epc_rating,
            "dominant_building_era": self.dominant_building_era,
            "estimated_council_tax_band": self.estimated_council_tax_band
        }

# 🗺️ 1. Test Route
@app.route('/')
def home():
    return jsonify({"status": "success", "message": "LegacyTrace UK API Layer is live!"})

# 🚀 2. Live Data API Route for your Frontend Map
@app.route('/api/properties/<string:postcode>', methods=['GET'])
def get_properties_by_postcode(postcode):
    # Standardize input string format to match database clean indices
    clean_postcode = postcode.upper().replace("-", " ").strip()
    
    properties = BirminghamProperty.query.filter_by(postcode=clean_postcode).all()
    
    if not properties:
        return jsonify({"status": "error", "message": f"No properties found for postcode: {clean_postcode}"}), 404
        
    return jsonify({
        "status": "success",
        "postcode": clean_postcode,
        "count": len(properties),
        "data": [p.to_dict() for p in properties]
    })

if __name__ == '__main__':
    app.run(debug=True)