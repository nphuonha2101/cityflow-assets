import json
import math
import os
import urllib.request
import urllib.parse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import argparse

# Setup argument parser
parser = argparse.ArgumentParser(description="Generate OSRM routes for CityFlow cities.")
parser.add_argument("--city", type=str, default="hcmc", choices=["hcmc", "hanoi"], help="Select city to generate routes for")
parser.add_argument("--min-lat", type=float, help="Override minimum latitude")
parser.add_argument("--max-lat", type=float, help="Override maximum latitude")
parser.add_argument("--min-lon", type=float, help="Override minimum longitude")
parser.add_argument("--max-lon", type=float, help="Override maximum longitude")
args, unknown = parser.parse_known_args()

# City configurations matching CityConfig presets in the game
CITY_CONFIGS = {
    "hcmc": {
        "min_lat": 10.30,
        "max_lat": 11.25,
        "min_lon": 106.35,
        "max_lon": 107.25,
        "folder": "hcmc"
    },
    "hanoi": {
        "min_lat": 21.015,
        "max_lat": 21.040,
        "min_lon": 105.840,
        "max_lon": 105.868,
        "folder": "hanoi"
    }
}

config = CITY_CONFIGS[args.city]
MIN_LAT = args.min_lat if args.min_lat is not None else config["min_lat"]
MAX_LAT = args.max_lat if args.max_lat is not None else config["max_lat"]
MIN_LON = args.min_lon if args.min_lon is not None else config["min_lon"]
MAX_LON = args.max_lon if args.max_lon is not None else config["max_lon"]
CITY_FOLDER = config["folder"]

# Closest neighbors to pre-calculate
K_NEIGHBORS = 4
MAX_DISTANCE_DEG = 0.0600  # ~6.6 km max threshold (raised from 5.0 km)

def calculate_distance(lat1, lon1, lat2, lon2):
    return math.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2)

def fetch_pair(stop_a, stop_b, idx, total):
    key = f"{stop_a['id']}-{stop_b['id']}"
    lon1, lat1 = stop_a['lon'], stop_a['lat']
    lon2, lat2 = stop_b['lon'], stop_b['lat']
    
    # Try localhost first (fast local OSRM), then public fallback
    urls = [
        f"http://localhost:5000/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=polyline",
        f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=polyline"
    ]
    
    for url in urls:
        req = urllib.request.Request(url, headers={'User-Agent': 'CityFlow/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                res_data = json.loads(response.read().decode())
                if res_data.get('code') == 'Ok' and 'routes' in res_data and len(res_data['routes']) > 0:
                    polyline_str = res_data['routes'][0]['geometry']
                    netloc = urllib.parse.urlparse(url).netloc
                    return key, polyline_str, f"[{idx+1}/{total}] {stop_a['name']} -> {stop_b['name']}: OK (via {netloc})"
        except Exception:
            # Fail silently and try next URL
            continue
            
    return key, None, f"[{idx+1}/{total}] {stop_a['name']} -> {stop_b['name']}: FAILED"

def generate():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    stops_file = os.path.join(base_dir, CITY_FOLDER, f'{CITY_FOLDER}_bus_stops.json')
    output_file = os.path.join(base_dir, CITY_FOLDER, f'{CITY_FOLDER}_routes_graph.json')

    print(f"Loading stops from {stops_file}...")
    with open(stops_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    elements = data.get('elements', [])
    filtered_stops = []
    
    for el in elements:
        lat, lon = el['lat'], el['lon']
        if MIN_LAT <= lat <= MAX_LAT and MIN_LON <= lon <= MAX_LON:
            filtered_stops.append(el)
            
    print(f"Total {args.city.upper()} filtered stops: {len(filtered_stops)}")
    
    # Identify stop pairs
    pairs_to_fetch = []
    for i, stop_a in enumerate(filtered_stops):
        for j, stop_b in enumerate(filtered_stops):
            if i == j:
                continue
            dist = calculate_distance(stop_a['lat'], stop_a['lon'], stop_b['lat'], stop_b['lon'])
            if dist <= MAX_DISTANCE_DEG:
                pairs_to_fetch.append((stop_a, stop_b))
            
    print(f"Prepared {len(pairs_to_fetch)} stop pairs to fetch routes for.")
    
    # Load existing precalculated routes if file exists to resume/avoid duplicate calls
    routes_cache = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                routes_cache = json.load(f)
            print(f"Loaded {len(routes_cache)} existing routes from cache.")
        except Exception as e:
            print("Could not load existing routes, starting fresh:", e)

    # Filter out already fetched pairs
    needed_pairs = []
    for stop_a, stop_b in pairs_to_fetch:
        key = f"{stop_a['id']}-{stop_b['id']}"
        if key not in routes_cache:
            needed_pairs.append((stop_a, stop_b))
            
    print(f"Already cached: {len(routes_cache)}, Need to fetch: {len(needed_pairs)}")
    
    if not needed_pairs:
        print("All routes already cached!")
        return

    # Use ThreadPoolExecutor to fetch parallelly (16 workers)
    cache_lock = threading.Lock()
    count_success = 0
    count_failed = 0
    
    def save_cache():
        with cache_lock:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(routes_cache, f, separators=(',', ':'), ensure_ascii=False)

    total_to_fetch = len(needed_pairs)
    
    print(f"Starting parallel fetch with 16 workers...")
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {
            executor.submit(fetch_pair, stop_a, stop_b, i, total_to_fetch): (stop_a, stop_b)
            for i, (stop_a, stop_b) in enumerate(needed_pairs)
        }
        
        for future in as_completed(futures):
            key, polyline, message = future.result()
            print(message)
            if polyline:
                with cache_lock:
                    routes_cache[key] = polyline
                    count_success += 1
                # Periodically save progress
                if count_success % 50 == 0:
                    save_cache()
                    print("--- Saved progress ---")
            else:
                count_failed += 1

    # Final save
    save_cache()
    print(f"\nCompleted! Success: {count_success}, Failed: {count_failed}")
    print(f"Total routes saved in cache: {len(routes_cache)}")

if __name__ == "__main__":
    generate()
