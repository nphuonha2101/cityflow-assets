#!/usr/bin/env python3
import os
import json
import hashlib
import subprocess
import sys

# Target Github repo info
REPO_OWNER = "nphuonha2101"
REPO_NAME = "cityflow-assets"

def get_file_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as file:
        while True:
            chunk = file.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def increment_version(version_str):
    try:
        parts = version_str.split('.')
        if len(parts) == 3:
            parts[2] = str(int(parts[2]) + 1)
            return '.'.join(parts)
    except Exception:
        pass
    return "1.0.0"

def main():
    # Change working directory to script's directory so it works from anywhere
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("=== CityFlow Assets Auto Publisher ===")
    
    # 1. Ask for release tag
    tag = input("Enter release tag (e.g. v1.0.0): ").strip()
    if not tag:
        print("Error: Tag cannot be empty.")
        sys.exit(1)
        
    if not tag.startswith('v'):
        tag = 'v' + tag

    manifest_path = "assets_manifest.json"
    
    # 2. Read existing manifest
    manifest = {
        "manifestVersion": "1.0.0",
        "cities": {}
    }
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to parse existing manifest: {e}. Starting fresh.")

    # 3. Setup city files by scanning configs
    from city_configs import CITY_CONFIGS
    
    upload_filepaths = []
    
    if "cities" not in manifest:
        manifest["cities"] = {}
        
    for city_id, city_conf in CITY_CONFIGS.items():
        folder = city_conf["folder"]
        display_name = city_conf["name"]
        
        map_filename = f"{city_id}_map.pmtiles"
        routes_filename = f"{city_id}_routes_graph.hive"
        stops_filename = f"{city_id}_bus_stops.hive"
        
        map_path = os.path.join(folder, map_filename)
        routes_path = os.path.join(folder, routes_filename)
        stops_path = os.path.join(folder, stops_filename)
        
        # We only process if all three files exist for the city in its folder
        if not os.path.exists(map_path) or not os.path.exists(routes_path) or not os.path.exists(stops_path):
            print(f"Skipping city '{city_id}' (some files not found in '{folder}/')")
            continue
            
        print(f"\nProcessing city '{city_id}' ({display_name})...")
        
        existing_assets = {}
        if city_id in manifest["cities"] and "assets" in manifest["cities"][city_id]:
            for asset in manifest["cities"][city_id]["assets"]:
                existing_assets[asset["name"]] = asset

        new_assets = []
        for filename, filepath in [(map_filename, map_path), (routes_filename, routes_path), (stops_filename, stops_path)]:
            print(f"  Processing '{filepath}'...")
            size = os.path.getsize(filepath)
            sha256_hash = get_file_sha256(filepath)
            
            # Check if changed
            existing = existing_assets.get(filename)
            version = "1.0.0"
            
            if existing and existing.get("sha256") == sha256_hash and existing.get("sizeBytes") == size:
                version = existing.get("version", "1.0.0")
                download_url = existing.get("url")
                print(f"    -> File has NOT changed. Keeping version {version} and URL.")
            else:
                if existing:
                    old_version = existing.get("version", "1.0.0")
                    version = increment_version(old_version)
                    print(f"    -> File CHANGED! Auto-incrementing version {old_version} -> {version}.")
                else:
                    print(f"    -> File is new. Starting version {version}.")
                
                download_url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{tag}/{filename}"
                upload_filepaths.append(filepath)

            new_assets.append({
                "name": filename,
                "url": download_url,
                "sha256": sha256_hash,
                "sizeBytes": size,
                "version": version
            })

        # Update manifest
        manifest["cities"][city_id] = {
            "displayName": display_name,
            "assets": new_assets
        }

    if not upload_filepaths:
        print("Warning: No changed city assets found to upload. Manifest will be updated locally.")
        confirm = input("\nDo you want to commit/push the updated manifest anyway? (y/n): ").strip().lower()
        if confirm != 'y':
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            print(f"Manifest successfully updated and written to '{manifest_path}'.")
            sys.exit(0)
            
        # If yes, we save and commit without gh release create
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        print(f"Manifest successfully updated and written to '{manifest_path}'.")
        try:
            print("\nAdding and committing manifest...")
            subprocess.run(["git", "add", manifest_path], check=True)
            status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            if status.stdout.strip():
                subprocess.run(["git", "commit", "-m", f"Update manifest for release {tag}"], check=True)
            print("Pushing to main branch...")
            subprocess.run(["git", "push", "origin", "main"], check=True)
            print("\n=== SUCCESS! Manifest pushed successfully! ===")
        except subprocess.CalledProcessError as e:
            print(f"\nError occurred during git deployment: {e}")
            sys.exit(1)
        sys.exit(0)

    # 4. Save manifest
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nManifest successfully updated and written to '{manifest_path}'.")

    # 5. Confirm and deploy
    confirm = input(f"\nDo you want to commit/push and publish release '{tag}' now? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Publishing cancelled. Manifest remains updated locally.")
        sys.exit(0)

    try:
        # Commit & push manifest
        print("\nAdding and committing manifest...")
        subprocess.run(["git", "add", manifest_path], check=True)
        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", f"Update manifest for release {tag}"], check=True)
        
        print("Pushing to main branch...")
        subprocess.run(["git", "push", "origin", "main"], check=True)

        # Create GH Release and upload assets
        print(f"Creating GitHub Release '{tag}' and uploading assets...")
        release_cmd = [
            "gh", "release", "create", tag,
            *upload_filepaths,
            "--title", f"Release {tag}",
            "--notes", f"Auto-generated asset release for {tag}"
        ]
        subprocess.run(release_cmd, check=True)
        
        print("\n=== SUCCESS! Assets and Manifest published successfully! ===")
        print(f"Raw Manifest URL: https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/{manifest_path}")

    except subprocess.CalledProcessError as e:
        print(f"\nError occurred during deployment: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
