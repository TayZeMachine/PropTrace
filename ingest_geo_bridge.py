import pandas as pd
import requests
from sqlalchemy import create_engine

DATABASE_URL = "postgresql://postgres:Mahdia123!@localhost:5432/proptrace_msc"
engine = create_engine(DATABASE_URL)

print("🔍 Pulling distinct postcodes from your master database...")
query = "SELECT DISTINCT postcode FROM core.birmingham_properties_master WHERE postcode IS NOT NULL;"
df_postcodes = pd.read_sql(query, con=engine)
postcodes_list = df_postcodes['postcode'].tolist()
print(f"📦 Found {len(postcodes_list)} unique postcodes to map.")

bridge_data = []
# Process lookups in optimized batches of 100 to respect API guidelines
batch_size = 100

print("🚀 Starting batch API geolocation mapping via postcodes.io...")
for i in range(0, len(postcodes_list), batch_size):
    batch = postcodes_list[i:i + batch_size]
    
    try:
        response = requests.post("https://api.postcodes.io/postcodes", json={"postcodes": batch}, timeout=10)
        if response.status_code == 200:
            results = response.json().get('result', [])
            for entry in results:
                if entry and entry.get('result'):
                    pc = entry['query']
                    lsoa = entry['result'].get('codes', {}).get('lsoa')
                    if lsoa:
                        bridge_data.append({"postcode": pc, "lsoa_code": lsoa})
        
        # Simple progress logger
        if len(bridge_data) % 500 == 0 and len(bridge_data) > 0:
            print(f"📥 Mapped {len(bridge_data)} postcodes so far...")
            
    except Exception as e:
        print(f"⚠️ Batch error encountered: {e}")
        continue

# Stream the completed bridge matrix straight into your database schema
if bridge_data:
    df_bridge = pd.DataFrame(bridge_data)
    df_bridge.to_sql('postcode_lsoa_bridge', con=engine, schema='geo', if_exists='append', index=False)
    print(f"✅ Success! Geocoded and saved {len(df_bridge)} rows into geo.postcode_lsoa_bridge.")
else:
    print("❌ No matching coordinates returned from lookup.")