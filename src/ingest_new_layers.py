import pandas as pd
from sqlalchemy import create_engine, text
import time

# 1. Establish localized database connection pooling
DB_URI = "postgresql://postgres:Mahdia123!@localhost:5432/proptrace_msc"
engine = create_engine(DB_URI)

def ingest_voa():
    start_time = time.time()
    print("⏳ Processing VOA Dwelling Age & Council Tax metric profiles...")
    
    # Read local dataset
    df = pd.read_csv("dwellingages.csv")
    df.columns = df.columns.str.lower()
    
    # Python automatically creates the table structural framework on execution
    df.to_sql(
        name="raw_voa_metrics",
        con=engine,
        schema="staging",
        if_exists="replace", # Refreshes the baseline lookup array completely
        index=False
    )
    print(f"🎉 VOA Ingestion complete in {time.time() - start_time:.2f} seconds.\n")

def ingest_epc():
    start_time = time.time()
    print("⏳ Running chunked pipeline for EPC Ratings (Filtering for B & NG)...")
    
    # Process in memory-safe 50k blocks to accommodate your local system limits
    chunks = pd.read_csv("EPC_RATINGS.CSV.csv", chunksize=50000, low_memory=False)
    total_rows = 0
    
    for i, chunk in enumerate(chunks):
        chunk.columns = chunk.columns.str.lower()
        
        # Isolate target regions right at the stream source layer
        filtered_chunk = chunk[chunk['postcode'].str.startswith(('B', 'NG'), na=False)].copy()
        
        if not filtered_chunk.empty:
            # Map explicit columns to match our planned data models
            columns_to_keep = [
                'lmk_key', 'address1', 'address2', 'address3', 
                'postcode', 'current_energy_rating', 'potential_energy_rating', 'inspection_date'
            ]
            valid_cols = [c for c in columns_to_keep if c in filtered_chunk.columns]
            
            # Continuously append incoming filtered frames into the staging target
            filtered_chunk[valid_cols].to_sql(
                name="raw_epc",
                con=engine,
                schema="staging",
                if_exists="append",
                index=False
            )
            total_rows += len(filtered_chunk)
            print(f"✅ Chunk {i+1}: Ingested {len(filtered_chunk)} regional records.")

    # 2. Performance Enhancement: Build optimization index via Python command execution
    print("⚡ Optimizing table indexes for Phase 2 cross-table joins...")
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_raw_epc_postcode ON staging.raw_epc(postcode);"))

    print(f"🎉 EPC Ingestion complete! Loaded {total_rows} rows in {time.time() - start_time:.2f} seconds.")

if __name__ == "__main__":
    ingest_voa()
    ingest_epc()