# CityFlow Assets Repository

Hosts the remote map and routing assets for the CityFlow / City Bus Connect game, along with the central `assets_manifest.json`.

## File list
- `hcmc_map.pmtiles`: HCMC Offline Vector Map (MapLibre compatible).
- `hcmc_routes_graph.hive`: HCMC Routing Graph (Hive binary representation).
- `assets_manifest.json`: Manifest tracking file sizes, URLs, hashes, and versions.

## How to Publish Assets
To update assets and release a new version:

1. Copy the updated `hcmc_map.pmtiles` and `hcmc_routes_graph.hive` into this directory.
2. Run the automated publisher script:
   ```bash
   ./publish.py
   ```
3. Enter the release version tag (e.g. `v1.0.0`) when prompted.
4. The tool will:
   - Calculate sizes and SHA256 checksums.
   - Increment individual file versions if their hashes changed.
   - Generate/update `assets_manifest.json`.
   - Commit and push `assets_manifest.json` to the GitHub repository.
   - Create a new GitHub Release with the specified tag and upload the asset files.
