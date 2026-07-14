import pandas as pd
from sqlalchemy import create_engine
import time

# 1. Database Connection Parameters
DATABASE_URL = "postgresql://postgres:Mahdia123!@localhost:5432/proptrace_msc"
engine = create_engine(DATABASE_URL)

# 2. Source File Path 
csv_file_path = "pp-complete.csv" 

# Official HM Land Registry column schema (Includes the 16th 'record_status' column)
column_names = [
    "transaction_id", "price", "transfer_date", "postcode", "property_type",
    "is_new_build", "duration", "paon", "saon", "street", 
    "locality", "town_city", "district", "county", "ppd_category", "record_status"
]

print("🚀 Starting memory-safe Price Paid Data (PPD) extraction engine...")
start_time = time.time()

chunk_size = 50000
total_inserted_rows = 0

# 3. Stream and Filter on the Fly
# Added index_col=False to strictly prevent data column shifting
for i, chunk in enumerate(pd.read_csv(csv_file_path, names=column_names, index_col=False, chunksize=chunk_size, low_memory=False)):
    # Isolate only rows belonging to Birmingham safely handling potential empty/null cells
    filtered_chunk = chunk[chunk["town_city"].astype(str).str.upper() == "BIRMINGHAM"]
    
    if not filtered_chunk.empty:
        # Load filtered chunk straight into the staging schema
        filtered_chunk.to_sql(
            name="price_paid_data", 
            con=engine, 
            schema="staging", 
            if_exists="append" if total_inserted_rows > 0 else "replace", 
            index=False
        )
        total_inserted_rows += len(filtered_chunk)
        print(f"✅ Processed chunk {i+1}: Added {len(filtered_chunk)} Birmingham records to staging.")

end_time = time.time()
print(f"🏆 Ingestion complete! Successfully parsed and loaded {total_inserted_rows} Birmingham transaction rows in {round(end_time - start_time, 2)} seconds.")