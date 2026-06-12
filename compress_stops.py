import argparse
import json
import os

def compress_json(input_path, output_path):
    print(f"Reading {input_path}...")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    elements = data.get('elements', [])
    compressed_elements = []
    
    for el in elements:
        # We only care about nodes with valid coordinates
        is_node = el.get('type') == 'node' or ('lat' in el and 'lon' in el)
        if is_node and el.get('lat') is not None and el.get('lon') is not None:
            # Extract name
            name = el.get('name')
            if not name:
                tags = el.get('tags', {})
                name = tags.get('name', 'Trạm ẩn danh')
            
            compressed_el = {
                'id': el['id'],
                'lat': el['lat'],
                'lon': el['lon'],
                'name': name
            }
            compressed_elements.append(compressed_el)
            
    output_data = {
        'elements': compressed_elements
    }
    
    print(f"Writing compressed JSON to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        # Write compact JSON (no indentation/extra spaces) to minimize file size
        json.dump(output_data, f, separators=(',', ':'), ensure_ascii=False)
        
    print("Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean and compress raw OSM bus stops JSON.")
    parser.add_argument("--city", type=str, default="hcmc", help="Select city to compress stops for")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    city_path = os.path.join(base_dir, args.city, f"{args.city}_bus_stops.json")
    
    # Try raw file first, then fall back to in-place compression
    raw_path = os.path.join(base_dir, args.city, f"raw_{args.city}_bus_stops.json")
    if os.path.exists(raw_path):
        compress_json(raw_path, city_path)
    else:
        if os.path.exists(city_path):
            compress_json(city_path, city_path)
        else:
            print(f"Error: Stops file not found at {city_path} or {raw_path}")
