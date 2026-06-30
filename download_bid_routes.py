#!/usr/bin/env python3
import os
import sys
import json
import time
import urllib.request
import urllib.parse
import argparse
import re
import random

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter"
]

from city_configs import CITY_CONFIGS


WINNING_ROUTE_CODES = {
    "01", "03", "04", "06", "07", "08", "09", "10",
    "13", "15", "16", "17", "18", "19", "20",
    "22", "23", "24", "25", "27", "28", "29", "30",
    "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "45", "46", "47", "48", "49", "50", "52", "53", "55",
    "56", "57", "58", "59", "60", "61", "62", "64", "65",
    "66", "68", "69", "70", "71", "72", "73", "74", "75",
    "76", "77", "78", "79", "81", "83", "84", "85", "86",
    "87", "88", "89", "90", "91", "93", "94", "95", "96",
    "99", "100", "101", "102", "103", "104", "107", "109",
    "110", "119", "120", "122", "123", "124", "126", "127",
    "128", "139", "140", "141", "144", "145", "146", "148",
    "149", "150", "151", "152",
}


def get_overpass_query(min_lat, min_lon, max_lat, max_lon):
    return f"""[out:json][timeout:120];
(
  relation["type"="route"]["route"="bus"]({min_lat},{min_lon},{max_lat},{max_lon});
);
out body;
>;
out skel qt;"""


def check_status_wait_time(interpreter_url):
    status_url = interpreter_url.replace('/interpreter', '/status')
    print(f"Checking Overpass status at: {status_url}")
    req = urllib.request.Request(status_url, headers={'User-Agent': 'CityFlow/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status_text = response.read().decode('utf-8')

            slots_match = re.search(r'(\d+)\s+slots\s+available\s+now', status_text)
            if slots_match and int(slots_match.group(1)) > 0:
                print(f"Status: {slots_match.group(1)} slot(s) available now.")
                return 1

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

                parsed = json.loads(res_data.decode('utf-8'))

                if "remark" in parsed and "error" in parsed.get("remark", "").lower():
                    print(f"Overpass Server Remark Error: {parsed['remark']}")
                    raise Exception("Overpass runtime error")

                with open(output_path, 'wb') as f:
                    f.write(res_data)

                elements_count = len(parsed.get('elements', []))
                print(f"Success! Downloaded {elements_count} elements to {output_path}")
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

            endpoint_idx = (endpoint_idx + 1) % len(OVERPASS_ENDPOINTS)

        except Exception as e:
            print(f"Network error or json parsing error: {e}")
            print(f"Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff *= 2
            endpoint_idx = (endpoint_idx + 1) % len(OVERPASS_ENDPOINTS)

    return False


def load_stop_ids(stops_json_path):
    """Load compressed bus stops JSON and build a set of valid node IDs."""
    if not os.path.exists(stops_json_path):
        print(f"Warning: Bus stops file not found at {stops_json_path}")
        return set()

    with open(stops_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    elements = data.get('elements', [])
    return {el['id'] for el in elements if el.get('id') is not None}


def extract_route_templates(raw_data, valid_stop_ids, city_id, min_stops=4):
    """Extract game-compatible route templates from raw Overpass data."""
    elements = raw_data.get('elements', [])

    node_map = {}
    for el in elements:
        if el.get('type') == 'node' and el.get('id') is not None:
            node_map[el['id']] = el

    relations = [el for el in elements if el.get('type') == 'relation' and el.get('id') is not None]

    print(f"\nFound {len(relations)} bus route relations.")

    from collections import defaultdict
    route_groups = defaultdict(list)

    skipped_few_stops = 0
    skipped_few_valid = 0

    for rel in relations:
        tags = rel.get('tags', {})
        route_ref = tags.get('ref', '')
        route_name = tags.get('name', '')
        route_from = tags.get('from', '')
        route_to = tags.get('to', '')

        members = rel.get('members', [])
        stop_members = [
            m for m in members
            if m.get('type') == 'node' and m.get('role', '') in ('stop', 'platform', '')
        ]

        if len(stop_members) < 2:
            skipped_few_stops += 1
            continue

        all_stop_ids = []
        seen = set()
        for m in stop_members:
            nid = m['ref']
            if nid not in seen:
                all_stop_ids.append(nid)
                seen.add(nid)

        valid_stop_ids_in_route = [nid for nid in all_stop_ids if nid in valid_stop_ids]

        if len(valid_stop_ids_in_route) < min_stops:
            skipped_few_valid += 1
            continue

        route_groups[route_ref].append({
            'name': route_name,
            'from': route_from,
            'to': route_to,
            'stop_ids': valid_stop_ids_in_route,
        })

    templates = []
    skipped_too_short = 0

    for route_ref, variants in route_groups.items():
        if len(variants) == 1:
            v = variants[0]
            outbound_ids = v['stop_ids']
            inbound_ids = list(reversed(outbound_ids))
        else:
            longest = max(variants, key=lambda v: len(v['stop_ids']))
            outbound_ids = longest['stop_ids']
            other = [v for v in variants if v is not longest]
            inbound_ids = other[0]['stop_ids'] if other else list(reversed(outbound_ids))

        if len(outbound_ids) < 2 or len(inbound_ids) < 2:
            skipped_too_short += 1
            continue

        v = variants[0]
        if v['from'] and v['to']:
            title = f"Tuyến {route_ref}: {v['from']} - {v['to']}" if route_ref else f"{v['from']} - {v['to']}"
        elif v['name']:
            title = v['name']
        elif route_ref:
            title = f"Tuyến {route_ref}"
        else:
            title = f"Tuyến {city_id.upper()} #{len(templates) + 1}"

        num_stops = max(len(outbound_ids), len(inbound_ids))
        duration_days = max(30, min(180, num_stops * 5))
        max_ticket_price = round(max(4.0, min(12.0, 3.0 + num_stops * 0.15)), 1)

        try:
            ref_num = int(route_ref)
        except (ValueError, TypeError):
            ref_num = 50

        required_headway_minutes = max(5, min(20, 5 + (ref_num % 10)))
        min_vehicle_condition = round(max(0.65, min(0.90, 0.60 + num_stops * 0.005)), 2)
        base_subsidized_value = round(max(10.0, min(30.0, num_stops * 0.5)), 1)

        template = {
            'id': f'bid_{city_id}_{route_ref or f"r{len(templates)+1:03d}"}',
            'routeNumber': route_ref or f'T-{10 + len(templates) % 90}',
            'title': title,
            'outboundStopIds': outbound_ids,
            'inboundStopIds': inbound_ids,
            'durationDays': duration_days,
            'maxTicketPrice': max_ticket_price,
            'requiredHeadwayMinutes': required_headway_minutes,
            'minVehicleCondition': min_vehicle_condition,
            'baseSubsidizedValue': base_subsidized_value,
        }
        templates.append(template)

    print(f"\nProcessed {len(templates)} valid route templates.")
    print(f"Skipped: {skipped_few_stops} routes with <2 stop members, {skipped_few_valid} routes with <{min_stops} valid stops, {skipped_too_short} routes too short.")

    return templates


def main():
    parser = argparse.ArgumentParser(description="Download HCMC bus route relations from OSM Overpass API.")
    parser.add_argument("--city", type=str, default="hcmc", choices=list(CITY_CONFIGS.keys()))
    parser.add_argument("--max-routes", type=int, default=50, help="Maximum number of routes to output")
    parser.add_argument("--min-stops", type=int, default=4, help="Minimum valid stops required per route")
    parser.add_argument("--winning-only", action="store_true", help="Only include winning route codes")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    city_dir = os.path.join(base_dir, args.city)
    os.makedirs(city_dir, exist_ok=True)

    raw_output = os.path.join(city_dir, f"raw_{args.city}_bid_routes.json")
    final_output = os.path.join(city_dir, f"{args.city}_bid_routes.json")
    stops_json_path = os.path.join(city_dir, f"{args.city}_bus_stops.json")

    config = CITY_CONFIGS[args.city]
    min_lat = config['min_lat']
    max_lat = config['max_lat']
    min_lon = config['min_lon']
    max_lon = config['max_lon']

    print("=== CityFlow Overpass Bid Routes Downloader ===")
    print(f"City: {args.city.upper()}")
    print(f"Bounding Box: ({min_lat}, {min_lon}) -> ({max_lat}, {max_lon})")
    print(f"Raw Output: {raw_output}")
    print(f"Final Output: {final_output}")

    valid_stop_ids = load_stop_ids(stops_json_path)
    print(f"Loaded {len(valid_stop_ids)} valid stop IDs from {stops_json_path}")

    query = get_overpass_query(min_lat, min_lon, max_lat, max_lon)

    success = fetch_with_retry(query, raw_output)
    if not success:
        print("\nFailed to download bus route data after multiple retries.")
        sys.exit(1)

    with open(raw_output, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    templates = extract_route_templates(raw_data, valid_stop_ids, args.city, min_stops=args.min_stops)

    if args.winning_only:
        before = len(templates)
        templates = [t for t in templates if str(t.get("routeNumber", "")) in WINNING_ROUTE_CODES]
        print(f"\nFiltered to winning routes: {len(templates)} / {before}")

    if args.max_routes and len(templates) > args.max_routes:
        print(f"\nLimiting from {len(templates)} to {args.max_routes} routes.")
        templates = templates[:args.max_routes]

    with open(final_output, 'w', encoding='utf-8') as f:
        json.dump(templates, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(templates)} bid route templates to {final_output}")
    print("All steps completed successfully!")


if __name__ == '__main__':
    main()
