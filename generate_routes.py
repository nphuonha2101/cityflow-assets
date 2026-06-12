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
parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers (default: 4)")
parser.add_argument("--close-dist-km", type=float, default=1.0, help="Radius (in km) within which all stop pairs are precalculated")
parser.add_argument("--k-neighbors", type=int, default=10, help="Number of nearest neighbors to keep within the maximum distance")
parser.add_argument("--max-dist-km", type=float, default=6.0, help="Maximum distance (in km) to consider for route generation")
args, unknown = parser.parse_known_args()


from city_configs import CITY_CONFIGS

config = CITY_CONFIGS[args.city]
MIN_LAT = args.min_lat if args.min_lat is not None else config["min_lat"]
MAX_LAT = args.max_lat if args.max_lat is not None else config["max_lat"]
MIN_LON = args.min_lon if args.min_lon is not None else config["min_lon"]
MAX_LON = args.max_lon if args.max_lon is not None else config["max_lon"]
CITY_FOLDER = config["folder"]

MAX_DISTANCE_KM = args.max_dist_km
CLOSE_DISTANCE_KM = args.close_dist_km
K_NEIGHBORS = args.k_neighbors

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on the earth (in km)
    """
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat/2)**2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return c * 6371.0

def fetch_pair(stop_a, stop_b, idx, total):
    key = f"{stop_a['id']}-{stop_b['id']}"
    lon1, lat1 = stop_a['lon'], stop_a['lat']
    lon2, lat2 = stop_b['lon'], stop_b['lat']
    
    # Try localhost first (fast local OSRM), then public fallback
    urls = [
        f"http://localhost:5000/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=polyline",
        # f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=polyline"
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
    
    # ── [1/5] Compute Adaptive Radii (Adaptive Radius with Power Scaling) ──
    print("Computing adaptive radii for all stops...")
    n_stops = len(filtered_stops)
    
    # Compute all pairwise distances (in km)
    distances_matrix = [[0.0] * n_stops for _ in range(n_stops)]
    for i in range(n_stops):
        stop_a = filtered_stops[i]
        for j in range(i + 1, n_stops):
            stop_b = filtered_stops[j]
            d = calculate_distance(stop_a['lat'], stop_a['lon'], stop_b['lat'], stop_b['lon'])
            distances_matrix[i][j] = d
            distances_matrix[j][i] = d

    # For each stop, compute the average distance to its k-nearest neighbors (k=6)
    k_val = min(6, n_stops - 1)
    avg_neighbor_dists = []
    for i in range(n_stops):
        dists = sorted([distances_matrix[i][j] for j in range(n_stops) if i != j])
        k_dists = dists[:k_val]
        avg_d = sum(k_dists) / len(k_dists) if k_dists else 0.5
        avg_neighbor_dists.append(avg_d)
        
    global_avg = sum(avg_neighbor_dists) / len(avg_neighbor_dists) if avg_neighbor_dists else 0.5
    
    # Calculate adaptive radii: base_radius * (avg_neighbor_dist / global_avg) ** power
    base_r = CLOSE_DISTANCE_KM
    min_r = 0.2
    max_r = MAX_DISTANCE_KM
    power = 0.7
    
    radii = []
    for avg_d in avg_neighbor_dists:
        r = base_r * (avg_d / global_avg) ** power if global_avg > 0 else base_r
        r = max(min_r, min(max_r, r))
        radii.append(r)
        
    # Generate candidate edges
    edges = set()
    for i in range(n_stops):
        r = radii[i]
        for j in range(n_stops):
            if i == j:
                continue
            if distances_matrix[i][j] <= r:
                edges.add((i, j))
                
    print(f"Generated {len(edges)} candidate edges using adaptive radius.")

    # ── [1.5/5] Add Sector-Based Nearest Neighbors (Directional/Cross-river Connectivity) ──
    print("Adding Sector-Based Nearest Neighbors...")
    NUM_SECTORS = 8
    sector_edges_added = 0
    for i in range(n_stops):
        stop_a = filtered_stops[i]
        # Keep track of the closest stop in each of the 8 sectors: (distance, index)
        closest_in_sectors = [None] * NUM_SECTORS
        
        for j in range(n_stops):
            if i == j:
                continue
            d = distances_matrix[i][j]
            if d > MAX_DISTANCE_KM:
                continue
                
            stop_b = filtered_stops[j]
            # Calculate angle / bearing from stop_a to stop_b
            dlon = stop_b['lon'] - stop_a['lon']
            dlat = stop_b['lat'] - stop_a['lat']
            angle = math.atan2(dlon, dlat) # bearing in radians between [-pi, pi]
            
            # Map to sector [0..7]
            sector_idx = int(((angle + math.pi) / (2 * math.pi)) * NUM_SECTORS) % NUM_SECTORS
            
            current_best = closest_in_sectors[sector_idx]
            if current_best is None or d < current_best[0]:
                closest_in_sectors[sector_idx] = (d, j)
                
        # Add the closest stop in each sector to edges
        for item in closest_in_sectors:
            if item is not None:
                _, j = item
                if (i, j) not in edges:
                    edges.add((i, j))
                    sector_edges_added += 1
                    
    print(f"Sector-based connectivity added {sector_edges_added} additional directed edges.")
    
    # ── [1.7/5] Add Cross-River Nearest Neighbors for HCMC ──
    if args.city == "hcmc":
        print("Adding HCMC Cross-River Nearest Neighbors...")
        
        def get_side(lat, lon):
            if lat > 10.82:
                river_lon = 106.72
            elif lat > 10.79:
                river_lon = 106.72
            elif lat > 10.77:
                river_lon = 106.708 + 0.6 * (lat - 10.77)
            elif lat > 10.75:
                river_lon = 106.708 + 0.7 * (10.77 - lat)
            else:
                river_lon = 106.722 + 1.3 * (10.75 - lat)
            return 0 if lon < river_lon else 1

        # Classify all stops
        sides = [get_side(stop['lat'], stop['lon']) for stop in filtered_stops]
        
        cross_edges_added = 0
        K_CROSS = 4 # Connect each stop to its 4 nearest neighbors on the opposite side
        
        for i in range(n_stops):
            stop_a = filtered_stops[i]
            side_a = sides[i]
            
            # Find all opposite side stops within MAX_DISTANCE_KM
            opposite_candidates = []
            for j in range(n_stops):
                if sides[j] != side_a:
                    d = distances_matrix[i][j]
                    if d <= MAX_DISTANCE_KM:
                        opposite_candidates.append((d, j))
            
            opposite_candidates.sort(key=lambda x: x[0])
            for d, j in opposite_candidates[:K_CROSS]:
                if (i, j) not in edges:
                    edges.add((i, j))
                    cross_edges_added += 1
                if (j, i) not in edges:
                    edges.add((j, i))
                    cross_edges_added += 1
                    
        print(f"HCMC Cross-river connectivity added {cross_edges_added} additional directed edges.")
    
    # ── [2/5] Ensure Sequential Connectivity (Gap Bridging) ──
    print("Running Gap Bridging to ensure sequential connectivity...")
    in_degrees = [0] * n_stops
    out_degrees = [0] * n_stops
    for u, v in edges:
        out_degrees[u] += 1
        in_degrees[v] += 1
        
    isolated = [n for n in range(n_stops) if in_degrees[n] == 0 or out_degrees[n] == 0]
    print(f"Found {len(isolated)} isolated stops (in/out degree = 0).")
    
    new_edges_added = 0
    max_gap_km = 15.0
    for node in isolated:
        for multiplier in [2.0, 3.0, 5.0, 10.0]:
            extended_r = radii[node] * multiplier
            if extended_r > max_gap_km:
                break
            
            candidates = []
            for j in range(n_stops):
                if j == node:
                    continue
                d = distances_matrix[node][j]
                if d <= extended_r:
                    candidates.append((d, j))
                    
            candidates.sort(key=lambda x: x[0])
            if len(candidates) >= 2:
                for d, j in candidates[:3]:
                    if (node, j) not in edges:
                        edges.add((node, j))
                        new_edges_added += 1
                    if (j, node) not in edges:
                        edges.add((j, node))
                        new_edges_added += 1
                break
                
    print(f"Gap bridging added {new_edges_added} additional directed edges.")
    
    # Convert edges to stop pairs
    pairs_to_fetch = []
    for u, v in edges:
        pairs_to_fetch.append((filtered_stops[u], filtered_stops[v]))
    
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
    
    print(f"Starting parallel fetch with {args.workers} workers in batches of 5000...")
    batch_size = 5000
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for batch_start in range(0, total_to_fetch, batch_size):
            batch_pairs = needed_pairs[batch_start:batch_start + batch_size]
            print(f"\nProcessing batch {batch_start//batch_size + 1} ({batch_start} to {batch_start + len(batch_pairs)} of {total_to_fetch})...")
            
            futures = {
                executor.submit(fetch_pair, stop_a, stop_b, batch_start + i, total_to_fetch): (stop_a, stop_b)
                for i, (stop_a, stop_b) in enumerate(batch_pairs)
            }
            
            for future in as_completed(futures):
                key, polyline, message = future.result()
                print(message)
                if polyline:
                    with cache_lock:
                        routes_cache[key] = polyline
                        count_success += 1
                else:
                    count_failed += 1
            
            # Save progress after each batch
            save_cache()
            print(f"--- Saved progress. Total success: {count_success}, Failed: {count_failed} ---")

    print(f"\nCompleted! Success: {count_success}, Failed: {count_failed}")
    
    # Prune cache to only contain currently requested pairs (reduces file size)
    active_keys = {f"{stop_a['id']}-{stop_b['id']}" for stop_a, stop_b in pairs_to_fetch}
    pruned_cache = {k: v for k, v in routes_cache.items() if k in active_keys}
    pruning_diff = len(routes_cache) - len(pruned_cache)
    if pruning_diff > 0:
        print(f"Pruning cache: removed {pruning_diff} stale/unused routes. Active size: {len(pruned_cache)}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(pruned_cache, f, separators=(',', ':'), ensure_ascii=False)
    else:
        print(f"Total active routes saved in cache: {len(routes_cache)}")

if __name__ == "__main__":
    generate()
