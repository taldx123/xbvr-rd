import subprocess
import urllib.request
import re
import difflib
import json
import sys
import os
import concurrent.futures
from html.parser import HTMLParser

class StudioParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_link = False
        self.current_uuid = None
        self.studios = {}

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for attr in attrs:
                if attr[0] == 'href' and attr[1].startswith('/studio/'):
                    self.in_link = True
                    self.current_uuid = attr[1].split('/studio/')[1]

    def handle_data(self, data):
        if self.in_link and self.current_uuid:
            name = data.strip()
            if name:
                self.studios[name] = self.current_uuid

    def handle_endtag(self, tag):
        if tag == 'a':
            self.in_link = False
            self.current_uuid = None

def normalize(name):
    # Remove strings in parentheses, e.g. "PT Porn (SLR)" -> "PT Porn "
    name = re.sub(r'\(.*?\)', '', name)
    return re.sub(r'[^a-z0-9]', '', name.lower())

def match_studio(db_name, api_studios):
    norm_db = normalize(db_name)
    best_match = None
    best_score = 0
    
    for api_name, uuid in api_studios.items():
        norm_api = normalize(api_name)
        if norm_db == norm_api:
            return uuid, api_name
        
        score = difflib.SequenceMatcher(None, norm_db, norm_api).ratio()
        if score > best_score:
            best_score = score
            best_match = (uuid, api_name)
            
    if best_score > 0.85:
        return best_match
    return None, None

def download_uuid(uuid, name):
    url = f"https://timestamp.trade/export-xbvr-cuepoints-studio/{uuid}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = urllib.request.urlopen(req, timeout=60).read().decode('utf-8')
        tmp_file = f"/tmp/cuepoints_{uuid}.json"
        with open(tmp_file, 'w') as f:
            f.write(data)
        return uuid, name, tmp_file, None
    except Exception as e:
        return uuid, name, None, str(e)

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 download_cuepoints.py <db_user> <db_pass> <db_name>")
        sys.exit(1)
        
    db_user = sys.argv[1]
    db_pass = sys.argv[2]
    db_name = sys.argv[3]

    print("Fetching studios from timestamp.trade...")
    req = urllib.request.Request("https://timestamp.trade/studios", headers={'User-Agent': 'Mozilla/5.0'})
    try:
        html = urllib.request.urlopen(req, timeout=30).read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching studios: {e}")
        return

    parser = StudioParser()
    parser.feed(html)
    api_studios = parser.studios
    print(f"Found {len(api_studios)} studios on timestamp.trade")

    cmd = [
        "docker", "exec", "xbvr-mariadb", "mariadb", 
        f"-u{db_user}", f"-p{db_pass}", db_name, 
        "--skip-column-names", "-e", 
        "SELECT DISTINCT s.studio, s.site FROM scenes s LEFT JOIN scene_cuepoints c ON c.scene_id = s.id WHERE c.id IS NULL AND ((s.studio IS NOT NULL AND s.studio != '') OR (s.site IS NOT NULL AND s.site != ''));"
    ]
    
    print("Querying database for studio and site combinations...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing db query: {result.stderr}")
        return
        
    rows = [line.strip().split('\t') for line in result.stdout.split('\n') if line.strip()]
    print(f"Found {len(rows)} unique studio/site combinations in database.")
    
    matched_studios = {}
    matched_count = 0
    missed_count = 0
    
    for row in rows:
        studio = row[0] if len(row) > 0 and row[0] != 'NULL' else ""
        site = row[1] if len(row) > 1 and row[1] != 'NULL' else ""
        
        uuid = None
        matched_name = None
        match_source = ""
        
        if studio:
            uuid, matched_name = match_studio(studio, api_studios)
            match_source = f"studio '{studio}'"
            
        if not uuid and site:
            uuid, matched_name = match_studio(site, api_studios)
            match_source = f"site '{site}'"
            
        if uuid:
            print(f"  [MATCH] {match_source} -> '{matched_name}'")
            matched_studios[uuid] = matched_name
            matched_count += 1
        else:
            print(f"  [MISS]  studio '{studio}' / site '{site}' - No match found")
            missed_count += 1

    if not matched_studios:
        print("No matched studios found. Exiting.")
        return

    print(f"\nDownloading cuepoints for {len(matched_studios)} matched studios (max 10 parallel)...")
    success_files = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(download_uuid, u, name): u for u, name in matched_studios.items()}
        for future in concurrent.futures.as_completed(futures):
            u, name, tmp_file, err = future.result()
            if err:
                print(f"  [ERROR] Failed downloading for '{name}' (uuid {u}): {err}")
            else:
                success_files.append((u, name, tmp_file))
                print(f"  [OK] Downloaded '{name}' to {tmp_file}")

    final_json = {
        "timestamp": "2026-07-12T00:00:00.000Z",
        "bundleVersion": "2.1",
        "volumes": None,
        "playlists": None,
        "sites": None,
        "scenes": [],
        "sceneCuepoints": [],
        "actions": [],
        "sceneFileLinks": [],
        "sceneHistory": []
    }

    total_scenes = 0
    total_cuepoints = 0
    
    print("\nMerging downloaded JSONs...")
    for uuid, name, tmp_file in success_files:
        try:
            with open(tmp_file, 'r') as f:
                j = json.load(f)
                
            scenes_count = len(j.get("scenes", []))
            cuepoints_count = len(j.get("sceneCuepoints", []))
                
            if "scenes" in j and j["scenes"]:
                final_json["scenes"].extend(j["scenes"])
                total_scenes += scenes_count
            if "sceneCuepoints" in j and j["sceneCuepoints"]:
                final_json["sceneCuepoints"].extend(j["sceneCuepoints"])
                total_cuepoints += cuepoints_count
            if "actions" in j and j["actions"]:
                final_json["actions"].extend(j["actions"])
            if "sceneFileLinks" in j and j["sceneFileLinks"]:
                final_json["sceneFileLinks"].extend(j["sceneFileLinks"])
            if "sceneHistory" in j and j["sceneHistory"]:
                final_json["sceneHistory"].extend(j["sceneHistory"])
                
            print(f"  Merged {scenes_count} scenes and {cuepoints_count} cuepoints for '{name}'")
        except Exception as e:
            print(f"  [ERROR] Failed to read/parse {tmp_file} for '{name}': {e}")

    output_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'xbvr', 'cuepoints.json'))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print(f"\nWriting combined JSON to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(final_json, f, separators=(',', ':'))
        
    print(f"\n======================================")
    print(f"         EXECUTION SUMMARY            ")
    print(f"======================================")
    print(f"  Total distinct DB records:      {len(rows)}")
    print(f"  Records matched on timestamp:   {matched_count}")
    print(f"  Records not matched:            {missed_count}")
    print(f"  Total unique studios fetched:   {len(matched_studios)}")
    print(f"  Successful downloads:           {len(success_files)}")
    print(f"  Failed downloads:               {len(matched_studios) - len(success_files)}")
    print(f"  Total scenes merged:            {total_scenes}")
    print(f"  Total cuepoints merged:         {total_cuepoints}")
    print(f"  Output file:                    {output_path}")
    print(f"======================================\n")

if __name__ == "__main__":
    main()
