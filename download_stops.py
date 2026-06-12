#!/usr/bin/env python3
import os
import sys
import json
import time
import urllib.request
import urllib.parse
import argparse
import re

# Public Overpass API instances for server rotation
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter"
]

# City OSM Area Names Mapping
CITY_AREAS = {
    "hcmc": "Thành phố Hồ Chí Minh",
    "hanoi": "Thành phố Hà Nội"
}

def get_overpass_query(area_name):
    return f"""[out:json][timeout:90];
area["name"="{area_name}"]->.searchArea;
(
  node["highway"="bus_stop"](area.searchArea);
  node["public_transport"="platform"]["bus"="yes"](area.searchArea);
);
out body;
>;
out skel qt;"""

def check_status_wait_time(interpreter_url):
    """
    Query the status page of the Overpass instance to see if a slot is available
    or how long we need to wait before a slot clears.
    """
    status_url = interpreter_url.replace('/interpreter', '/status')
    print(f"Checking Overpass status at: {status_url}")
    req = urllib.request.Request(status_url, headers={'User-Agent': 'CityFlow/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status_text = response.read().decode('utf-8')
            
            # Check if there are slots available immediately
            slots_match = re.search(r'(\d+)\s+slots\s+available\s+now', status_text)
            if slots_match and int(slots_match.group(1)) > 0:
                print(f"Status: {slots_match.group(1)} slot(s) available now.")
                return 1
                
            # If wait is required, find slot available time
            wait_match = re.search(r'Slot\s+available\s+after:\s+([0-9\-T\:Z]+)(?:\s+\(in\s+(\d+)\s+seconds\))?', status_text)
            if wait_match:
                if wait_match.group(2):
                    seconds = int(wait_match.group(2))
                    print(f"Status: Slot available in {seconds} seconds.")
                    return seconds
                else:
                    print(f"Status: Slot available after {wait_match.group(1)} (estimated 15s delay).")
                    return 15
                    
            if "Currently running queries" in status_text:
                print("Status: Queries are currently running, slot busy.")
                return 10
    except Exception as e:
        print(f"Could not read status page: {e}")
    return 0

def fetch_with_retry(query, output_path):
    endpoint_idx = 0
    max_retries = 6
    backoff = 5.0
    
    for attempt in range(max_retries):
        endpoint = OVERPASS_ENDPOINTS[endpoint_idx]
        print(f"\n[Attempt {attempt + 1}/{max_retries}] Contacting: {endpoint}")
        
        # Prepare POST payload
        data = urllib.parse.urlencode({'data': query}).encode('utf-8')
        req = urllib.request.Request(
            endpoint, 
            data=data,
            headers={'User-Agent': 'CityFlow/1.0 (https://github.com/nphuonha/cityflow)'}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                print("Connected! Downloading data...")
                res_data = response.read()
                
                # Validate JSON format
                parsed = json.loads(res_data.decode('utf-8'))
                
                # Check for Overpass runtime errors reported in JSON remarks
                if "remark" in parsed and "error" in parsed.get("remark", "").lower():
                    print(f"Overpass Server Remark Error: {parsed['remark']}")
                    raise Exception("Overpass runtime error")
                    
                with open(output_path, 'wb') as f:
                    f.write(res_data)
                
                elements_count = len(parsed.get('elements', []))
                print(f"Success! Downloaded {elements_count} stops to {output_path}")
                return True
                
        except urllib.error.HTTPError as e:
            print(f"HTTP Error {e.code}: {e.reason}")
            
            if e.code == 429:
                print("Rate limited (HTTP 429). Initiating status check...")
                wait_seconds = check_status_wait_time(endpoint)
                sleep_duration = wait_seconds + 2 if wait_seconds > 0 else backoff
                print(f"Sleeping for {sleep_duration} seconds before retry...")
                time.sleep(sleep_duration)
                backoff *= 2
            else:
                print(f"Server returned HTTP {e.code}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff *= 2
                
            # Rotate to next endpoint to spread out queries
            endpoint_idx = (endpoint_idx + 1) % len(OVERPASS_ENDPOINTS)
            
        except Exception as e:
            print(f"Network error or json parsing error: {e}")
            print(f"Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff *= 2
            endpoint_idx = (endpoint_idx + 1) % len(OVERPASS_ENDPOINTS)
            
    return False

def main():
    parser = argparse.ArgumentParser(description="Download city bus stops from OSM Overpass API with HTTP 429 handling.")
    parser.add_argument("--city", type=str, default="hcmc", choices=["hcmc", "hanoi"], help="Select city to download stops for")
    parser.add_argument("--area-name", type=str, help="Override OSM area query name")
    args = parser.parse_args()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    city_dir = os.path.join(base_dir, args.city)
    os.makedirs(city_dir, exist_ok=True)
    
    output_file = os.path.join(city_dir, f"raw_{args.city}_bus_stops.json")
    
    area_name = args.area_name if args.area_name else CITY_AREAS[args.city]
    
    print("=== CityFlow OSM Overpass Downloader ===")
    print(f"City: {args.city.upper()}")
    print(f"OSM Area Name: {area_name}")
    print(f"Output Path: {output_file}")
    
    query = get_overpass_query(area_name)
    
    success = fetch_with_retry(query, output_file)
    if success:
        print("\nAll steps completed successfully!")
    else:
        print("\nFailed to download stops after multiple retries.")
        sys.exit(1)

if __name__ == '__main__':
    main()
