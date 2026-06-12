import argparse
import json
import os

from city_configs import CITY_CONFIGS

def compress_json(input_path, output_path, min_lat, max_lat, min_lon, max_lon):
    print(f"Reading {input_path}...")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    elements = data.get('elements', [])
    compressed_elements = []
    skipped_bbox = 0
    skipped_name = 0
    
    for el in elements:
        # We only care about nodes with valid coordinates
        is_node = el.get('type') == 'node' or ('lat' in el and 'lon' in el)
        if is_node and el.get('lat') is not None and el.get('lon') is not None:
            lat = el['lat']
            lon = el['lon']
            
            # Filter by bounding box
            if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
                skipped_bbox += 1
                continue
                
            # Extract name
            name = el.get('name')
            if not name:
                tags = el.get('tags', {})
                name = tags.get('name')
                
            # Discard nameless stops completely
            if not name or not name.strip():
                skipped_name += 1
                continue
            
            compressed_el = {
                'id': el['id'],
                'lat': lat,
                'lon': lon,
                'name': name.strip()
            }
            compressed_elements.append(compressed_el)
            
    output_data = {
        'elements': compressed_elements
    }
    
    print(f"Filtered out {skipped_bbox} stops outside bounding box, {skipped_name} nameless stops.")
    print(f"Remaining stops: {len(compressed_elements)}")
    print(f"Writing compressed JSON to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        # Write compact JSON (no indentation/extra spaces) to minimize file size
        json.dump(output_data, f, separators=(',', ':'), ensure_ascii=False)
        
    print("Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean and compress raw OSM bus stops JSON.")
    parser.add_argument("--city", type=str, default="hcmc", choices=["hcmc", "hanoi"], help="Select city to compress stops for")
    parser.add_argument("--min-lat", type=float, help="Override minimum latitude")
    parser.add_argument("--max-lat", type=float, help="Override maximum latitude")
    parser.add_argument("--min-lon", type=float, help="Override minimum longitude")
    parser.add_argument("--max-lon", type=float, help="Override maximum longitude")
    args = parser.parse_args()

    config = CITY_CONFIGS.get(args.city, {"min_lat": -90.0, "max_lat": 90.0, "min_lon": -180.0, "max_lon": 180.0})
    min_lat = args.min_lat if args.min_lat is not None else config["min_lat"]
    max_lat = args.max_lat if args.max_lat is not None else config["max_lat"]
    min_lon = args.min_lon if args.min_lon is not None else config["min_lon"]
    max_lon = args.max_lon if args.max_lon is not None else config["max_lon"]

    base_dir = os.path.dirname(os.path.abspath(__file__))
    city_path = os.path.join(base_dir, args.city, f"{args.city}_bus_stops.json")
    
    # Try raw file first, then fall back to in-place compression
    raw_path = os.path.join(base_dir, args.city, f"raw_{args.city}_bus_stops.json")
    if os.path.exists(raw_path):
        compress_json(raw_path, city_path, min_lat, max_lat, min_lon, max_lon)
    else:
        if os.path.exists(city_path):
            compress_json(city_path, city_path, min_lat, max_lat, min_lon, max_lon)
        else:
            print(f"Error: Stops file not found at {city_path} or {raw_path}")
