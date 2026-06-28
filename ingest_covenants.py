import pandas as pd
from sqlalchemy import create_engine
import time

# 1. Database Connection Parameters
DATABASE_URL = "postgresql://postgres:Mahdia123!@localhost:5432/proptrace_msc"
engine = create_engine(DATABASE_URL)

# 2. Source File Path
csv_file_path = "birmingham_covenants.csv"

print("🚀 Starting Restrictive Covenants data streaming engine...")
start_time = time.time()

chunk_size = 50000
total_rows = 0

# 3. Memory-Safe Ingestion Loop
for chunk in pd.read_csv(csv_file_path, chunksize=chunk_size, low_memory=False):
    # Standardize column names (force lowercase, strip out hidden spaces)
    chunk.columns = [col.lower().strip() for col in chunk.columns]
    
    # Write chunk directly into the 'staging' schema
    chunk.to_sql(
        name='raw_covenants', 
        con=engine, 
        schema='staging', 
        if_exists='append', 
        index=False
    )
    
    total_rows += len(chunk)
    print(f"📥 Successfully streamed {total_rows} total rows into staging.raw_covenants...")

end_time = time.time()
print(f"✅ Pipeline complete! Loaded {total_rows} covenant records in {end_time - start_time:.1f} seconds.")