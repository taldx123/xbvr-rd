import os
import json
import subprocess
import sys
import re

def generate_slug(title):
    title = title.lower()
    title = title.replace('&', 'and')
    # Strip bracketed tags entirely, e.g. [Trans] Naughty Notes -> Naughty Notes
    title = re.sub(r'\[.*?\]', '', title)
    # Strip common punctuation that causes slug divergence
    title = title.replace("'", "")
    title = title.replace("’", "")
    title = title.replace("é", "e")
    title = title.replace("*", "")
    title = title.replace(",", "")
    title = title.replace(".", "")
    title = title.replace("!", "")
    title = title.replace("?", "")
    slug = re.sub(r'[^a-z0-9]+', '-', title)
    return slug.strip('-')

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 download_arp_cuepoints.py <db_user> <db_pass> <db_name>")
        sys.exit(1)
        
    db_user = sys.argv[1]
    db_pass = sys.argv[2]
    db_name = sys.argv[3]
    
    arp_json_path = os.path.expanduser("~/work/projects/arp/scraped/authenticated_full.json")
    if not os.path.exists(arp_json_path):
        print(f"Error: ARP JSON file not found at {arp_json_path}")
        print("Please run the scraper (Option 3 in ARP project) first.")
        sys.exit(1)
        
    print(f"Loading {arp_json_path}...")
    try:
        with open(arp_json_path, 'r') as f:
            arp_data = json.load(f)
    except Exception as e:
        print(f"Error reading ARP JSON: {e}")
        sys.exit(1)
        
    print(f"Loaded {len(arp_data)} scenes from ARP JSON.")
    
    # Query XBVR database for all scenes with arporn.com URLs
    cmd = [
        "docker", "exec", "xbvr-mariadb", "mariadb",
        f"-u{db_user}", f"-p{db_pass}", db_name,
        "--skip-column-names", "-e",
        "SELECT scene_id, scene_url FROM scenes WHERE scene_url LIKE '%arporn.com/video/%';"
    ]
    
    print("Querying database for AR Porn scenes...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing db query: {result.stderr}")
        return
        
    slug_to_scene_id = {}
    for line in result.stdout.split('\n'):
        line = line.strip()
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) >= 2:
            scene_id = parts[0]
            url = parts[1]
            # Extract slug from URL: https://arporn.com/video/can-i-stay-for-just-a-bit-longer/
            slug = url.rstrip('/').split('/')[-1]
            slug_to_scene_id[slug] = scene_id
            
    print(f"Found {len(slug_to_scene_id)} AR Porn scenes in database.")
    
    final_json = {
        "timestamp": "2026-08-29T00:00:00.000Z",
        "bundleVersion": "2.1",
        "sceneCuepoints": []
    }
    
    total_cuepoints = 0
    matched_scenes = 0
    
    for item in arp_data:
        title = item.get("title", "")
        slug = generate_slug(title)
        
        if slug in slug_to_scene_id:
            scene_id = slug_to_scene_id[slug]
            
            details = item.get("details", [])
            if details and len(details) > 0:
                markers = details[0].get("timeline_markers", [])
                cuepoints = []
                for m in markers:
                    # Some markers only have 'tilt', we only want those with a 'title'
                    if "title" in m:
                        time_s = float(m["time"]) / 1000.0
                        cuepoints.append({
                            "time_start": time_s,
                            "name": m["title"]
                        })
                
                if cuepoints:
                    final_json["sceneCuepoints"].append({
                        "scene_id": scene_id,
                        "cuepoints": cuepoints
                    })
                    total_cuepoints += len(cuepoints)
                    matched_scenes += 1
                    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.abspath(os.path.join(script_dir, '..', 'data', 'xbvr', 'cuepoints.json'))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print(f"\nWriting combined JSON to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(final_json, f, separators=(',', ':'))
        
    print(f"\n======================================")
    print(f"         EXECUTION SUMMARY            ")
    print(f"======================================")
    print(f"  ARP JSON Scenes:                {len(arp_data)}")
    print(f"  DB ARP Scenes:                  {len(slug_to_scene_id)}")
    print(f"  Matched Scenes w/ Cuepoints:    {matched_scenes}")
    print(f"  Total Cuepoints Generated:      {total_cuepoints}")
    print(f"  Output file:                    {output_path}")
    print(f"======================================\n")

if __name__ == "__main__":
    main()
