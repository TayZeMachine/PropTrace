import os
import warnings
import pandas as pd
from sqlalchemy import create_engine, text

# Silence pandas deprecation and future warnings
warnings.filterwarnings("ignore")

# 1. Database Connection Parameters
DATABASE_URL = "postgresql://postgres:Mahdia123!@localhost:5432/proptrace_msc"
engine = create_engine(DATABASE_URL)

# 2. File Path and Schema Configuration
CSV_PATH = os.path.join("..", "NSUL_E126_MAY_2026_WM.csv") 
SCHEMA_NAME = "staging"
TABLE_NAME = "raw_nsul_birmingham"
DATA_EPOCH = "May_2026"

def ingest_birmingham_data():
    print("Starting targeted ingestion process...")
    
    if not os.path.exists(CSV_PATH):
        fallback_path = "NSUL_E126_MAY_2026_WM.csv"
        path = fallback_path if os.path.exists(fallback_path) else None
        if not path:
            print(f"Error: Could not find the file at {CSV_PATH}")
            return
    else:
        path = CSV_PATH

    # ONS GSS code for Birmingham City Council
    BIRMINGHAM_CODE = "E08000025"
    TARGET_COL = "lad25cd"
    
    # Use 'pcds' here because that is the original lowercase name in the ONS CSV
    COLUMNS_TO_KEEP = ['uprn', 'pcds', 'lsoa21cd', 'gridgb1e', 'gridgb1n']
    
    chunk_size = 50000  
    first_chunk = True
    total_rows_inserted = 0

    try:
        for chunk in pd.read_csv(path, chunksize=chunk_size, low_memory=False):
            # Lowercase for seamless Postgres interaction
            chunk.columns = [col.lower() for col in chunk.columns]
            
            # Filter solely for Birmingham records
            if TARGET_COL in chunk.columns:
                filtered_chunk = chunk[chunk[TARGET_COL].astype(str).str.strip() == BIRMINGHAM_CODE]
            else:
                filtered_chunk = pd.DataFrame()

            if not filtered_chunk.empty:
                # Isolate the requested features using the real CSV names
                filtered_chunk = filtered_chunk[COLUMNS_TO_KEEP]
                
                # Cleanly rename 'pcds' to your preferred 'postcode' name on the fly
                filtered_chunk = filtered_chunk.rename(columns={'pcds': 'postcode'})
                
                # Append the explicit epoch column to track the dataset's era timeline
                filtered_chunk['snapshot_epoch'] = DATA_EPOCH
                
                if first_chunk:
                    filtered_chunk.to_sql(TABLE_NAME, schema=SCHEMA_NAME, con=engine, if_exists='replace', index=False)
                    first_chunk = False
                else:
                    filtered_chunk.to_sql(TABLE_NAME, schema=SCHEMA_NAME, con=engine, if_exists='append', index=False)
                
                total_rows_inserted += len(filtered_chunk)
                print(f"Filtered & Inserted {len(filtered_chunk)} rows... (Total: {total_rows_inserted})")

        # Enforce Primary Key constraint on the final table inside DataGrip staging schema
        if total_rows_inserted > 0:
            print("Applying primary key optimization constraints...")
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {SCHEMA_NAME}.{TABLE_NAME} ADD PRIMARY KEY (uprn, snapshot_epoch);"))

        print(f"\nSuccessfully ingested {total_rows_inserted} Birmingham records into '{SCHEMA_NAME}.{TABLE_NAME}' table!")

    except Exception as e:
        print(f"An error occurred during ingestion: {e}")

if __name__ == "__main__":
    ingest_birmingham_data()