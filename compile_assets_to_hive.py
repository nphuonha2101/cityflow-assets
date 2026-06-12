#!/usr/bin/env python3
import os
import sys
import json
import struct
import zlib
import math

def calculate_distance(lat1, lon1, lat2, lon2):
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat/2)**2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return c * 6371.0  # in km

def decode_polyline(polyline_str):
    coordinates = []
    index = 0
    lat = 0
    lng = 0
    try:
        while index < len(polyline_str):
            shift = 0
            result = 0
            while True:
                b = ord(polyline_str[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if not (b & 0x20):
                    break
            dlat = ~(result >> 1) if (result & 1) else (result >> 1)
            lat += dlat
            
            shift = 0
            result = 0
            while True:
                b = ord(polyline_str[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if not (b & 0x20):
                    break
            dlng = ~(result >> 1) if (result & 1) else (result >> 1)
            lng += dlng
            coordinates.append((lat / 1e5, lng / 1e5))
    except Exception:
        pass
    return coordinates

def calculate_polyline_distance(polyline_str):
    coords = decode_polyline(polyline_str)
    if not coords:
        return 0.0
    dist = 0.0
    for i in range(len(coords) - 1):
        dist += calculate_distance(coords[i][0], coords[i][1], coords[i+1][0], coords[i+1][1])
    return dist * 1000.0  # in meters

def write_varint(value):
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7f) | 0x80)
        value >>= 7
    out.append(value)
    return out

def build_hive_frame(key_str, value_str):
    key_bytes = key_str.encode('utf-8')
    key_len_varint = write_varint(len(key_bytes))
    
    value_bytes = value_str.encode('utf-8')
    value_len_bytes = struct.pack('<I', len(value_bytes))
    
    payload = bytearray()
    payload.append(1) # String key type
    payload.extend(key_len_varint)
    payload.extend(key_bytes)
    payload.append(4) # String value type
    payload.extend(value_len_bytes)
    payload.extend(value_bytes)
    
    frame_size = 4 + len(payload) + 4
    size_bytes = struct.pack('<I', frame_size)
    
    crc_input = size_bytes + payload
    crc = zlib.crc32(crc_input) & 0xffffffff
    checksum_bytes = struct.pack('<I', crc)
    
    return size_bytes + payload + checksum_bytes

def main():
    city = sys.argv[1] if len(sys.argv) > 1 else 'hcmc'
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Detect if we are in Flutter repo or standalone assets repo
    is_flutter_repo = os.path.exists(os.path.join(base_dir, 'assets', 'data'))
    if is_flutter_repo:
        city_dir = os.path.join(base_dir, 'assets', 'data', city)
    else:
        city_dir = os.path.join(base_dir, city)
        
    print("=== CityFlow Assets Python Hive Compiler ===")
    print(f"Target City: {city}")
    print(f"Directory: {city_dir}")
    
    # 1. Compile Bus Stops
    stops_json_path = os.path.join(city_dir, f"{city}_bus_stops.json")
    if os.path.exists(stops_json_path):
        print(f"Compiling stops from {stops_json_path}...")
        with open(stops_json_path, 'r', encoding='utf-8') as f:
            stops_json_str = f.read()
            
        # Validate JSON format
        try:
            json.loads(stops_json_str)
        except Exception as e:
            print(f"Error: Invalid JSON format in {stops_json_path}: {e}")
            sys.exit(1)
            
        stops_hive_path = os.path.join(city_dir, f"{city}_bus_stops.hive")
        with open(stops_hive_path, 'wb') as f:
            f.write(build_hive_frame('stops', stops_json_str))
        print(f"Successfully compiled stops to: {stops_hive_path} ({os.path.getsize(stops_hive_path)} bytes)")
    else:
        print(f"Warning: {stops_json_path} not found, skipping stops compilation.")
        
    # 2. Compile Precalculated Routes
    routes_json_path = os.path.join(city_dir, f"{city}_routes_graph.json")
    if os.path.exists(routes_json_path):
        print(f"Compiling routes from {routes_json_path}...")
        with open(routes_json_path, 'r', encoding='utf-8') as f:
            routes_data = json.load(f)
            
        print(f"Loaded {len(routes_data)} routes. Optimizing symmetric pairs...")
        
        processed_keys = set()
        deduped_routes = {}
        symmetric_count = 0
        asymmetric_count = 0
        single_count = 0
        
        for key, val in routes_data.items():
            if key in processed_keys:
                continue
                
            parts = key.split('-')
            if len(parts) != 2:
                deduped_routes[key] = val
                continue
                
            stop_a, stop_b = parts[0], parts[1]
            rev_key = f"{stop_b}-{stop_a}"
            
            if rev_key in routes_data:
                polyline_a = val
                polyline_b = routes_data[rev_key]
                
                dist_a = calculate_polyline_distance(polyline_a)
                dist_b = calculate_polyline_distance(polyline_b)
                
                max_dist = max(dist_a, dist_b, 1.0)
                diff = abs(dist_a - dist_b) / max_dist
                
                if diff < 0.05:
                    canonical_key = key if key < rev_key else rev_key
                    canonical_val = routes_data[canonical_key]
                    deduped_routes[canonical_key] = canonical_val
                    symmetric_count += 1
                else:
                    deduped_routes[key] = val
                    deduped_routes[rev_key] = routes_data[rev_key]
                    asymmetric_count += 2
                    
                processed_keys.add(key)
                processed_keys.add(rev_key)
            else:
                deduped_routes[key] = val
                processed_keys.add(key)
                single_count += 1
                
        print(f"Deduplication complete:")
        print(f"  - Symmetric pairs detected: {symmetric_count} (removed {symmetric_count} redundant routes)")
        print(f"  - Asymmetric pairs (kept both): {asymmetric_count}")
        print(f"  - Single-direction routes: {single_count}")
        print(f"  - Final routing graph size: {len(deduped_routes)} / {len(routes_data)} routes ({len(deduped_routes)/len(routes_data)*100:.1f}%)")
        
        routes_hive_path = os.path.join(city_dir, f"{city}_routes_graph.hive")
        with open(routes_hive_path, 'wb') as f:
            for key, val in deduped_routes.items():
                val_str = json.dumps(val) if isinstance(val, (dict, list)) else (str(val) if val is not None else "")
                f.write(build_hive_frame(key, val_str))
        print(f"Successfully compiled routes to: {routes_hive_path} ({os.path.getsize(routes_hive_path)} bytes)")
    else:
        print(f"Note: {routes_json_path} not found, skipping routes compilation.")
        
    print("Done!")

if __name__ == '__main__':
    main()
