import subprocess
import urllib.request
import urllib.parse
import json
import sys
import os
import re
import time
import concurrent.futures

def clean_scraper_id(s):
    if not s:
        return ""
    s = s.replace('alternate scene ', '')
    s = re.sub(r'-slr$', '', s)
    s = re.sub(r'-\d+$', '', s)
    return s

def search_studio(name):
    if not name:
        return None, None
    query = urllib.parse.quote(name)
    url = f"https://api.sexlikereal.com/v3/search?query={query}&tab=studios"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Client-Type': 'web', 'project': '1'})
    try:
        time.sleep(0.1)
        res = urllib.request.urlopen(req, timeout=30).read().decode('utf-8')
        data = json.loads(res)
        if 'data' in data and len(data['data']) > 0:
            return data['data'][0]['id'], data['data'][0]['name']
    except Exception as e:
        pass
    return None, None

def fetch_studio_scenes(studio_id):
    scenes = []
    page = 1
    while True:
        url = f"https://api.sexlikereal.com/v3/scenes?studios={studio_id}&perPage=36&sort=mostRecent&page={page}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Client-Type': 'web', 'project': '1'})
        try:
            time.sleep(0.2)
            res = urllib.request.urlopen(req, timeout=30).read().decode('utf-8')
            data = json.loads(res)
            if 'data' not in data or not data['data']:
                break
            scenes.extend(data['data'])
            
            meta = data.get('meta', {})
            pagination = meta.get('pagination', {})
            if page >= pagination.get('totalPages', 1):
                break
            page += 1
        except Exception as e:
            print(f"  [ERROR] Failed to fetch page {page} for studio {studio_id}: {e}")
            break
    return scenes

def fetch_single_scene(label):
    url = f"https://api.sexlikereal.com/v3/scenes/{label}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Client-Type': 'web', 'project': '1'})
    try:
        time.sleep(0.2)
        res = urllib.request.urlopen(req, timeout=30).read().decode('utf-8')
        data = json.loads(res)
        if 'data' in data:
            return data['data']
    except Exception as e:
        pass
    return None

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 download_slr_cuepoints.py <db_user> <db_pass> <db_name>")
        sys.exit(1)
        
    db_user = sys.argv[1]
    db_pass = sys.argv[2]
    db_name = sys.argv[3]
    
    script_dir = os.path.dirname(__file__)
    data_dir = os.path.abspath(os.path.join(script_dir, '..', 'data', 'xbvr'))
    cache_path = os.path.join(data_dir, 'slr-studio-cache.tsv')
    
    # Load cache
    studio_cache = {}
    now = time.time()
    ttl = 5 * 24 * 60 * 60 # 5 days
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                parts = line.split('\t')
                if len(parts) >= 4:
                    term, sid, sname, timestamp = parts[0], parts[1], parts[2], float(parts[3])
                    if now - timestamp <= ttl:
                        studio_cache[term] = (int(sid), sname)

    print("Querying database for SLR scenes without cuepoints...")
    
    query = """
    SELECT s.scene_id, s.scene_url, s.studio, s.scraper_id 
    FROM scenes s
    LEFT JOIN scene_cuepoints c ON c.scene_id = s.id
    WHERE s.scene_url LIKE '%sexlikereal.com/scenes/%' AND c.id IS NULL
    UNION
    SELECT s.scene_id, e.external_url, s.studio, e.external_source AS scraper_id 
    FROM external_references e 
    JOIN external_reference_links erl ON e.id = erl.external_reference_id 
    JOIN scenes s ON s.id = erl.internal_db_id 
    LEFT JOIN scene_cuepoints c ON c.scene_id = s.id
    WHERE e.external_url LIKE '%sexlikereal.com/scenes/%' AND c.id IS NULL;
    """
    
    cmd = [
        "docker", "exec", "xbvr-mariadb", "mariadb", 
        f"-u{db_user}", f"-p{db_pass}", db_name, 
        "--skip-column-names", "-e", query
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing db query: {result.stderr}")
        return
        
    label_to_scene_ids = {}
    label_to_search_term = {}
    
    for line in result.stdout.split('\n'):
        line = line.strip()
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) >= 4:
            scene_id = parts[0]
            url = parts[1]
            studio = parts[2] if parts[2] != 'NULL' else ""
            scraper_id = parts[3] if parts[3] != 'NULL' else ""
            
            label = url.rstrip('/').split('/')[-1]
            
            if label not in label_to_scene_ids:
                label_to_scene_ids[label] = []
            if scene_id not in label_to_scene_ids[label]:
                label_to_scene_ids[label].append(scene_id)
                
            cleaned_scraper = clean_scraper_id(scraper_id)
            if cleaned_scraper and cleaned_scraper != 'slr':
                label_to_search_term[label] = cleaned_scraper
            elif studio:
                label_to_search_term[label] = studio
                
    print(f"Found {len(label_to_scene_ids)} unique SLR scenes missing cuepoints in the database.")
    
    if not label_to_scene_ids:
        print("No eligible SLR URLs found (either none exist or all already have cuepoints). Exiting.")
        return

    term_to_labels = {}
    for label, term in label_to_search_term.items():
        if term:
            if term not in term_to_labels:
                term_to_labels[term] = []
            term_to_labels[term].append(label)

    print(f"\nResolving {len(term_to_labels)} unique studio names to SLR Studio IDs (max 10 parallel)...")
    studio_id_to_term = {}
    term_to_studio_id = {}
    
    terms_to_fetch = []
    
    for term in list(term_to_labels.keys()):
        if term in studio_cache:
            sid, sname = studio_cache[term]
            term_to_studio_id[term] = sid
            studio_id_to_term[sid] = sname
            print(f"  [CACHED] '{term}' -> {sid} ({sname})")
        else:
            terms_to_fetch.append(term)
            
    if terms_to_fetch:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_term = {executor.submit(search_studio, term): term for term in terms_to_fetch}
            for future in concurrent.futures.as_completed(future_to_term):
                term = future_to_term[future]
                sid, sname = future.result()
                if sid:
                    term_to_studio_id[term] = sid
                    studio_id_to_term[sid] = sname
                    print(f"  [FETCHED] '{term}' -> {sid} ({sname})")
                    # Write to cache immediately
                    with open(cache_path, 'a') as f:
                        f.write(f"{term}\t{sid}\t{sname}\t{time.time()}\n")
                else:
                    print(f"  [MISS] Could not map '{term}'")

    print(f"\nBatch downloading scenes for {len(studio_id_to_term)} studios (max 10 parallel)...")
    
    final_json = {
        "timestamp": "2026-07-12T00:00:00.000Z",
        "bundleVersion": "2.1",
        "sceneCuepoints": []
    }
    
    processed_labels = set()
    total_cuepoints = 0
    
    if studio_id_to_term:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_sid = {executor.submit(fetch_studio_scenes, sid): sid for sid in studio_id_to_term.keys()}
            for future in concurrent.futures.as_completed(future_to_sid):
                sid = future_to_sid[future]
                sname = studio_id_to_term[sid]
                scenes = future.result()
                matched_in_studio = 0
                for scene in scenes:
                    scene_label = scene.get('label')
                    if scene_label in label_to_scene_ids and scene_label not in processed_labels:
                        timestamps = scene.get('timestamps', [])
                        if timestamps:
                            cuepoints = [{"time_start": float(ts["timestamp"]), "name": ts["name"]} for ts in timestamps]
                            for xbvr_scene_id in label_to_scene_ids[scene_label]:
                                final_json["sceneCuepoints"].append({
                                    "scene_id": xbvr_scene_id,
                                    "cuepoints": cuepoints
                                })
                            total_cuepoints += len(cuepoints)
                        processed_labels.add(scene_label)
                        matched_in_studio += 1
                print(f"  [OK] Fetched all scenes for {sname} (ID: {sid}) -> Found {matched_in_studio} matching scenes.")

    remaining_labels = set(label_to_scene_ids.keys()) - processed_labels
    
    if remaining_labels:
        print(f"\nFalling back to individual fetch for {len(remaining_labels)} remaining scenes (max 10 parallel)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_label = {executor.submit(fetch_single_scene, label): label for label in remaining_labels}
            completed = 0
            for future in concurrent.futures.as_completed(future_to_label):
                label = future_to_label[future]
                scene = future.result()
                completed += 1
                if scene:
                    timestamps = scene.get('timestamps', [])
                    if timestamps:
                        cuepoints = [{"time_start": float(ts["timestamp"]), "name": ts["name"]} for ts in timestamps]
                        for xbvr_scene_id in label_to_scene_ids[label]:
                            final_json["sceneCuepoints"].append({
                                "scene_id": xbvr_scene_id,
                                "cuepoints": cuepoints
                            })
                        total_cuepoints += len(cuepoints)
                    print(f"  [{completed}/{len(remaining_labels)}] [OK] Fetched fallback {label}")
                else:
                    print(f"  [{completed}/{len(remaining_labels)}] [MISS] Failed fallback {label}")
                processed_labels.add(label)

    output_path = os.path.join(data_dir, 'cuepoints.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print(f"\nWriting combined JSON to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(final_json, f, separators=(',', ':'))
        
    print(f"\n======================================")
    print(f"         EXECUTION SUMMARY            ")
    print(f"======================================")
    print(f"  Total eligible scenes in DB:    {len(label_to_scene_ids)}")
    print(f"  Studios mapped via Search API:  {len(studio_id_to_term)}")
    print(f"  Scenes matched via batch:       {len(processed_labels) - len(remaining_labels)}")
    print(f"  Scenes fetched individually:    {len(remaining_labels)}")
    print(f"  Total cuepoints generated:      {total_cuepoints}")
    print(f"  Output file:                    {output_path}")
    print(f"======================================\n")

if __name__ == "__main__":
    main()
