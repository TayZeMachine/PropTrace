import geopandas as gpd
from sqlalchemy import create_engine

# 1. Point directly to the .shp file inside your extracted folder
shp_path = r"C:\Users\User\Downloads\Flood_Zones_2_3_Rivers_and_Sea\Flood_Zones_2_3_Rivers_and_SeaPolygon.shp"

# 2. Load shapefile into GeoDataFrame
print("Reading shapefile...")
gdf = gpd.read_file(shp_path)

# Ensure CRS is set to British National Grid (EPSG:27700)
if gdf.crs != "EPSG:27700":
    gdf = gdf.to_crs(epsg=27700)

# 3. SQLAlchemy connection to PostGIS database
# Adjust user, password, port, and database name to match DataGrip setup
db_url = "postgresql://postgres:Mahdia123!@localhost:5432/proptrace_msc"
engine = create_engine(db_url)

# 4. Ingest into your chosen schema
target_schema = "staging"
table_name = "ea_flood_zones"

print(f"Uploading to {target_schema}.{table_name}...")
gdf.to_postgis(
    name=table_name,
    con=engine,
    schema=target_schema,
    if_exists="replace",
    index=False
)

print("Ingestion complete!")