#!/usr/bin/env python3
import os
import sys
import json
import struct
import zlib

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
            
        routes_hive_path = os.path.join(city_dir, f"{city}_routes_graph.hive")
        with open(routes_hive_path, 'wb') as f:
            for key, val in routes_data.items():
                val_str = json.dumps(val) if isinstance(val, (dict, list)) else (str(val) if val is not None else "")
                f.write(build_hive_frame(key, val_str))
        print(f"Successfully compiled routes to: {routes_hive_path} ({os.path.getsize(routes_hive_path)} bytes)")
    else:
        print(f"Note: {routes_json_path} not found, skipping routes compilation.")
        
    print("Done!")

if __name__ == '__main__':
    main()
