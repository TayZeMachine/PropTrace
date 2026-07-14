import pandas as pd
from sqlalchemy import create_engine
import time

DATABASE_URL = "postgresql://postgres:Mahdia123!@localhost:5432/proptrace_msc"
engine = create_engine(DATABASE_URL)


csv_file_path = "birmingham_uprns.csv"

print("🚀 Starting UPRN data streaming engine...")
start_time = time.time()

chunk_size = 25000
total_rows = 0

for chunk in pd.read_csv(csv_file_path, chunksize=chunk_size):

    chunk.columns = [col.lower().strip() for col in chunk.columns]
    
    chunk.to_sql(
        name='birmingham_uprns', 
        con=engine, 
        schema='geo', 
        if_exists='append', 
        index=False
    )
    
    total_rows += len(chunk)
    print(f"📥 Successfully streamed {total_rows} total rows into geo.birmingham_uprns...")

end_time = time.time()
print(f"✅ Pipeline complete! Loaded {total_rows} property nodes in {round(end_time - start_time, 2)} seconds.")