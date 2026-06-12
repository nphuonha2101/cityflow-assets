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

    # 3. Setup HCMC files
    hcmc_files = ["hcmc_map.pmtiles", "hcmc_routes_graph.hive"]
    existing_hcmc_assets = {}
    
    if "cities" in manifest and "hcmc" in manifest["cities"] and "assets" in manifest["cities"]["hcmc"]:
        for asset in manifest["cities"]["hcmc"]["assets"]:
            existing_hcmc_assets[asset["name"]] = asset

    new_assets = []
    
    for filename in hcmc_files:
        if not os.path.exists(filename):
            print(f"Error: Required file '{filename}' not found in current directory.")
            sys.exit(1)

        print(f"Processing '{filename}'...")
        size = os.path.getsize(filename)
        sha256_hash = get_file_sha256(filename)
        
        # Check if changed
        existing = existing_hcmc_assets.get(filename)
        version = "1.0.0"
        
        if existing:
            if existing.get("sha256") == sha256_hash and existing.get("sizeBytes") == size:
                version = existing.get("version", "1.0.0")
                print(f"  -> File '{filename}' has NOT changed. Keeping version {version}.")
            else:
                old_version = existing.get("version", "1.0.0")
                version = increment_version(old_version)
                print(f"  -> File '{filename}' CHANGED! Auto-incrementing version {old_version} -> {version}.")
        else:
            print(f"  -> File '{filename}' is new. Starting version {version}.")

        download_url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{tag}/{filename}"
        
        new_assets.append({
            "name": filename,
            "url": download_url,
            "sha256": sha256_hash,
            "sizeBytes": size,
            "version": version
        })

    # Update manifest
    manifest["cities"]["hcmc"] = {
        "displayName": "TP. Hồ Chí Minh",
        "assets": new_assets
    }

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
            "hcmc_map.pmtiles", "hcmc_routes_graph.hive",
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
