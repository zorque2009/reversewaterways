import csv
import os
import sys
import requests
import osmium
import webbrowser
from collections import defaultdict

CSV_FILE = "regions.csv"

# ---------------------------
# Waterway analysis
# ---------------------------
class JunctionCounter(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.node_to_way_start = defaultdict(int)
        self.node_to_way_end = defaultdict(int)
        self.way_endpoints = {}  # way_id -> (start_node, end_node)

    def way(self, w):
        if 'waterway' in w.tags and len(w.nodes) > 1:
            start = w.nodes[0].ref
            end = w.nodes[-1].ref
            self.way_endpoints[w.id] = (start, end)
            self.node_to_way_start[start] += 1
            self.node_to_way_end[end] += 1

def analyze_file(filename):
    print(f"Analyzing {filename}...")
    handler = JunctionCounter()
    handler.apply_file(filename, locations=False)

    # Find junction nodes
    junction_nodes = set()
    for node_id in set(handler.node_to_way_start) | set(handler.node_to_way_end):
        start_count = handler.node_to_way_start.get(node_id, 0)
        end_count = handler.node_to_way_end.get(node_id, 0)
        if (end_count == 2 and start_count == 0) or (start_count == 2 and end_count == 0):
            junction_nodes.add(node_id)

    # Find ways between junctions
    ways_between_junctions = [
        way_id for way_id, (start, end) in handler.way_endpoints.items()
        if start in junction_nodes and end in junction_nodes
    ]

    count = len(ways_between_junctions)
    print(f" {count} ways between junctions")

    # Open links one by one
    

    for i, way_id in enumerate(ways_between_junctions, start=1):
        input("Press Enter to load the next way (or Ctrl+C to quit)...")
        josm_url = f"http://localhost:8111/load_object?objects=way{way_id}"
        print(f"[{i}/{count}] Loading way {way_id} into JOSM...")
        try:
            r = requests.get(josm_url)
            r.raise_for_status()
            print(" Loaded successfully in JOSM")
        except Exception as e:
            print(f" Failed to load into JOSM: {e}")

    input("Press Enter to proceed to next region (or Ctrl+C to quit)...")

    return count

# ---------------------------
# CSV helpers
# ---------------------------
def load_regions(csv_file):
    regions = []
    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, fieldnames=["name", "url", "size", "count"], delimiter="\t")
        for row in reader:
            regions.append(row)
            
    total_count = sum(int(r["count"]) for r in regions if r["count"])
    print(f"Total ways between junctions: {total_count}")
    
    return regions

def save_regions(csv_file, regions):
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "url", "size", "count"], delimiter="\t")
        for r in regions:
            writer.writerow(r)

def parse_size(size_str):
    """Convert '6.9 GB' to bytes for sorting."""
    if not size_str:
        return float("inf")
    num, unit = size_str.replace("(", "").replace(")", "").split()
    num = float(num)
    unit = unit.lower()
    if unit.startswith("kb"): return num * 1024
    if unit.startswith("mb"): return num * 1024**2
    if unit.startswith("gb"): return num * 1024**3
    return num

# ---------------------------
# Selection logic
# ---------------------------
def pick_next_region(regions):
    def get_count(r):
        return float("inf") if not r["count"] else int(r["count"])

    max_count = max(get_count(r) for r in regions)
    candidates = [r for r in regions if get_count(r) == max_count]

    # tiebreaker: smallest file size
    candidates.sort(key=lambda r: parse_size(r["size"]))
    return candidates[0]

# ---------------------------
# Runner
# ---------------------------
def main():
    while True:
        regions = load_regions(CSV_FILE)

        # check if all processed
        if all(r["count"] for r in regions):
            print(" All regions have been processed.")
            break

        region = pick_next_region(regions)
        print(f"\nSelected region: {region['name']} (size {region['size']}")

        filename = os.path.basename(region["url"])

        # Always redownload the file
        if os.path.exists(filename):
            os.remove(filename)

        print(f"Downloading fresh {filename}...")
        with requests.get(region["url"], stream=True) as r:
            r.raise_for_status()
            with open(filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(" Download complete.")

        count = analyze_file(filename)
        region["count"] = str(count)

        save_regions(CSV_FILE, regions)
        print(f"✔ Updated {CSV_FILE} with new count for {region['name']}")

        # Delete the .osm.pbf after processing
        if os.path.exists(filename):
            try:
                os.remove(filename)
                print(f"🗑 Deleted {filename} to save disk space")
            except Exception as e:
                print(f"⚠ Could not delete {filename}: {e}")


if __name__ == "__main__":
    main()
