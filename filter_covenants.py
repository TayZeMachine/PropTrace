import pandas as pd
import os
import time

# Update these paths to match your exact computer paths
raw_giant_file = r"C:\Users\User\Downloads\RES_COV_FULL_2026_06\restrictive_covenants.csv.csv"
output_clean_file = "birmingham_covenants.csv"

print("⏳ Sifting through the nationwide dataset... This will take a moment.")
start_time = time.time()

chunk_size = 50000
total_matched_rows = 0
is_first_chunk = True

# Read the file in memory-safe chunks
for chunk in pd.read_csv(raw_giant_file, chunksize=chunk_size, low_memory=False):
    # Standardize column headers to lowercase to avoid casing mismatches
    chunk.columns = [col.lower().strip() for col in chunk.columns]
    
    # Filter for West Midlands rows using either the 'county' or 'region' columns
    filtered_chunk = chunk[
        (chunk['county'].str.contains('West Midlands', case=False, na=False)) |
        (chunk['region'].str.contains('West Midlands', case=False, na=False))
    ]
    
    # If we found matches in this chunk, write them out immediately
    if not filtered_chunk.empty:
        total_matched_rows += len(filtered_chunk)
        # Append rows dynamically. If it's the first batch, write headers; otherwise skip headers.
        filtered_chunk.to_csv(output_clean_file, mode='a', index=False, header=is_first_chunk)
        is_first_chunk = False

elapsed_time = time.time() - start_time
print(f"✅ Completed! Sliced down to {total_matched_rows} regional covenant rows.")
print(f"🚀 Saved a pristine copy to: {os.path.abspath(output_clean_file)} in {elapsed_time:.1f} seconds.")