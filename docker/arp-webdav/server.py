from wsgidav.wsgidav_app import WsgiDAVApp
from wsgidav.dav_provider import DAVProvider, DAVCollection, DAVNonCollection
from cheroot import wsgi
import json
import os
import sys
import threading
import time
import urllib.parse
import requests
import io

JSON_PATH = os.environ.get('JSON_PATH', '/app/authenticated_links.json')
PORT = int(os.environ.get('PORT', 8080))
HOST = os.environ.get('HOST', '0.0.0.0')

size_cache = {}
session = requests.Session()

def get_real_size(url):
    # Ignore dynamic tokens in URL for caching purposes if possible, but exact match is fine.
    if url in size_cache:
        return size_cache[url]
    try:
        resp = session.head(url, timeout=5, allow_redirects=True)
        if 'content-length' in resp.headers:
            size = int(resp.headers['content-length'])
            size_cache[url] = size
            return size
    except Exception as e:
        print(f"Failed to fetch size for {url}: {e}")
    # Fallback to 50GB if unknown
    return 50 * 1024 * 1024 * 1024

def load_data():
    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading {JSON_PATH}: {e}")
        return {}
        
    tree = {}
    for item in data:
        title = item.get('title', f"Scene_{item.get('id')}")
        # Clean title for directory name
        title = "".join(c for c in title if c.isalnum() or c in " _-()").strip()
        
        vid_url = item.get('video_url')
        mask_url = item.get('mask_url')
        
        if not vid_url: continue
        
        folder = {}
        # Extract filename from URL
        parsed_vid = urllib.parse.urlparse(vid_url)
        vid_filename = os.path.basename(parsed_vid.path) or "video.mp4"
        folder[vid_filename] = vid_url
        
        if mask_url:
            if vid_filename.lower().endswith('.mp4'):
                mask_filename = vid_filename[:-4] + '_XALPHA.mp4'
            else:
                mask_filename = vid_filename + '_XALPHA.mp4'
            folder[mask_filename] = mask_url
            
        tree[title] = folder
    return tree

class VideoFile(DAVNonCollection):
    def __init__(self, path, environ, url):
        super().__init__(path, environ)
        self.url = url
        
    def get_content_length(self):
        return get_real_size(self.url)
        
    def support_ranges(self):
        return True
        
    def get_content(self):
        # The Middleware intercepts GET/HEAD requests, this is just a stub
        return io.BytesIO(b"")
        
    def support_etag(self):
        return True
        
    def get_etag(self):
        return "12345-fake-etag"

class SceneFolder(DAVCollection):
    def __init__(self, path, environ, files):
        super().__init__(path, environ)
        self.files = files
        
    def get_member_names(self):
        return list(self.files.keys())
        
    def get_member(self, name):
        if name in self.files:
            return VideoFile(self.path + name, self.environ, self.files[name])
        return None

class RootFolder(DAVCollection):
    def __init__(self, path, environ, tree):
        super().__init__(path, environ)
        self.tree = tree
        
    def get_member_names(self):
        return list(self.tree.keys())
        
    def get_member(self, name):
        if name in self.tree:
            return SceneFolder(self.path + name + "/", self.environ, self.tree[name])
        return None

class DynamicProvider(DAVProvider):
    def __init__(self):
        super().__init__()
        self.tree = load_data()
        self.last_load = time.time()
        
    def _refresh(self):
        # Refresh JSON if it was modified
        if os.path.exists(JSON_PATH):
            mtime = os.path.getmtime(JSON_PATH)
            if mtime > self.last_load:
                self.tree = load_data()
                self.last_load = mtime
                
    def get_resource_inst(self, path, environ):
        self._refresh()
        if path == "/":
            return RootFolder("/", environ, self.tree)
            
        parts = [p for p in path.split('/') if p]
        if len(parts) == 1:
            if parts[0] in self.tree:
                return SceneFolder(path + "/", environ, self.tree[parts[0]])
        elif len(parts) == 2:
            if parts[0] in self.tree and parts[1] in self.tree[parts[0]]:
                return VideoFile(path, environ, self.tree[parts[0]][parts[1]])
        return None

class RedirectMiddleware:
    """Intercepts GET/HEAD requests and returns a 302 redirect."""
    def __init__(self, app, provider):
        self.app = app
        self.provider = provider
        
    def __call__(self, environ, start_response):
        if environ['REQUEST_METHOD'] in ('GET', 'HEAD'):
            path_info = environ.get('PATH_INFO', '')
            try:
                path_info = path_info.encode('latin-1').decode('utf-8')
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            path = urllib.parse.unquote(path_info)
            parts = [p for p in path.split('/') if p]
            if len(parts) == 2:
                self.provider._refresh()
                scene = parts[0]
                filename = parts[1]
                if scene in self.provider.tree and filename in self.provider.tree[scene]:
                    url = self.provider.tree[scene][filename]
                    print(f"Redirecting {path} -> {url}")
                    sys.stdout.flush()
                    start_response('302 Found', [('Location', url)])
                    return [b""]
                else:
                    print(f"File not found in tree: {path} (scene: {scene!r}, filename: {filename!r})")
                    sys.stdout.flush()
        # Pass through to WsgiDAV for PROPFIND, etc.
        return self.app(environ, start_response)

def main():
    if not os.path.exists(JSON_PATH):
        print(f"Warning: {JSON_PATH} not found. Waiting for it to appear...")
        
    provider = DynamicProvider()
    
    config = {
        "host": HOST,
        "port": PORT,
        "provider_mapping": {"/": provider},
        "simple_dc": {"user_mapping": {"*": True}}, # Anonymous access
        "verbose": 1
    }

    app = WsgiDAVApp(config)
    app = RedirectMiddleware(app, provider)

    print(f"Serving WebDAV on {HOST}:{PORT}, monitoring {JSON_PATH}")
    server = wsgi.Server((config["host"], config["port"]), app)
    server.start()

if __name__ == '__main__':
    main()
