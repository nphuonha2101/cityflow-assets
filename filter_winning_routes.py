#!/usr/bin/env python3
import json
import os
import sys

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


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(base_dir, "hcmc", "hcmc_bid_routes.json")

    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found. Run download_bid_routes.py first.")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        all_routes = json.load(f)

    print(f"Total bid routes loaded: {len(all_routes)}")
    print(f"Winning route codes to match: {len(WINNING_ROUTE_CODES)}")

    matched = []
    matched_codes = set()
    for route in all_routes:
        rn = str(route.get("routeNumber", ""))
        if rn in WINNING_ROUTE_CODES:
            matched.append(route)
            matched_codes.add(rn)

    missing = sorted(WINNING_ROUTE_CODES - matched_codes, key=lambda x: int(x))

    print(f"\nMatched: {len(matched_codes)} / {len(WINNING_ROUTE_CODES)} winning codes")
    print(f"Total matched route objects: {len(matched)}")
    if missing:
        print(f"\nMissing ({len(missing)}): {', '.join(missing)}")

    output_path = os.path.join(base_dir, "hcmc", "hcmc_bid_routes.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(matched, f, indent=2, ensure_ascii=False)
    print(f"\nWrote filtered routes to {output_path}")


if __name__ == "__main__":
    main()
