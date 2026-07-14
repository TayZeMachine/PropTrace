import geopandas as gpd
from sqlalchemy import create_engine
import time

# 1. Database Connection Parameters
DATABASE_URL = "postgresql://postgres:Mahdia123!@localhost:5432/proptrace_msc"
engine = create_engine(DATABASE_URL)

# 2. Source File Path (Updated to look directly in the root folder)
gml_file_path = "Land_Registry_Cadastral_Parcels.gml"

print("🗺️ Starting spatial data ingestion engine (GML -> PostGIS via Pyogrio)...")
start_time = time.time()

try:
    print("⏳ Reading geographic layers from GML file... (This may take a moment)")
    # Using engine="pyogrio" bypasses the Fiona compilation bug and reads faster
    gdf = gpd.read_file(gml_file_path, engine="pyogrio")
    
    # Force column names to lowercase for database schema consistency
    gdf.columns = map(str.lower, gdf.columns)
    
    print(f"📊 Extracted {len(gdf)} spatial boundary polygons. Writing to 'geo' schema...")
    
    # 4. Stream geographic features directly into your geo schema
    gdf.to_postgis(
        name="birmingham_polygons",
        con=engine,
        schema="geo",
        if_exists="replace",
        index=False
    )
    
    end_time = time.time()
    print(f"🏆 Spatial data loaded! Successfully populated geo.birmingham_polygons in {round(end_time - start_time, 2)} seconds.")

except Exception as e:
    print(f"❌ Ingestion failed: {str(e)}")