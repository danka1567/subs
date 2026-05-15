"""
advanced_streaming_app.py
=========================
Advanced Movie/TV Show Streaming Web App with TMDB Integration
Supports multiple streaming servers with automatic m3u8 extraction and playback

Requirements:
    pip install streamlit requests pycryptodome beautifulsoup4 pillow
"""

import streamlit as st
import requests
import json
import re
import base64
from urllib.parse import quote, quote_plus, urlparse, parse_qs
from typing import Dict, List, Optional, Any
import time
import hashlib

# Page configuration
st.set_page_config(
    page_title="Advanced Streaming Hub",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
<style>
    .stVideo {
        background-color: black;
        border-radius: 10px;
    }
    .server-card {
        padding: 10px;
        border-radius: 5px;
        margin: 5px;
        cursor: pointer;
        transition: all 0.3s;
    }
    .server-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .quality-badge {
        background-color: #4CAF50;
        color: white;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 12px;
        margin-left: 8px;
    }
    .stream-info {
        background-color: #1e1e1e;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .stAlert {
        margin-top: 10px;
    }
</style>
""", unsafe_allow_html=True)

# TMDB Configuration
TMDB_API_KEY = "6fad3f86b8452ee232deb7977d7dcf58"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

# API endpoints
ENCDEC_API = "https://enc-dec.app/api"
BASE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Session state initialization
if 'selected_movie' not in st.session_state:
    st.session_state.selected_movie = None
if 'selected_tv' not in st.session_state:
    st.session_state.selected_tv = None
if 'current_streams' not in st.session_state:
    st.session_state.current_streams = []
if 'current_m3u8' not in st.session_state:
    st.session_state.current_m3u8 = None
if 'current_referer' not in st.session_state:
    st.session_state.current_referer = None

# ============================================================================
# TMDB API Functions
# ============================================================================

@st.cache_data(ttl=3600)
def search_tmdb(query: str, media_type: str = "all") -> List[Dict]:
    """Search TMDB for movies or TV shows"""
    if media_type in ["movie", "all"]:
        movie_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
            "page": 1
        }
        movie_resp = requests.get(movie_url, params=params).json()
        movies = movie_resp.get("results", [])
        for m in movies:
            m["media_type"] = "movie"
    else:
        movies = []
    
    if media_type in ["tv", "all"]:
        tv_url = f"{TMDB_BASE_URL}/search/tv"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
            "page": 1
        }
        tv_resp = requests.get(tv_url, params=params).json()
        shows = tv_resp.get("results", [])
        for s in shows:
            s["media_type"] = "tv"
    else:
        shows = []
    
    results = movies + shows
    return sorted(results, key=lambda x: x.get("popularity", 0), reverse=True)

@st.cache_data(ttl=3600)
def get_movie_details(movie_id: int) -> Dict:
    """Get detailed movie information"""
    url = f"{TMDB_BASE_URL}/movie/{movie_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US",
        "append_to_response": "credits,images,videos"
    }
    return requests.get(url, params=params).json()

@st.cache_data(ttl=3600)
def get_tv_details(tv_id: int) -> Dict:
    """Get detailed TV show information"""
    url = f"{TMDB_BASE_URL}/tv/{tv_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US",
        "append_to_response": "credits,images,videos,season/1"
    }
    return requests.get(url, params=params).json()

@st.cache_data(ttl=3600)
def get_tv_seasons(tv_id: int, season_num: int) -> Dict:
    """Get specific season details"""
    url = f"{TMDB_BASE_URL}/tv/{tv_id}/season/{season_num}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }
    return requests.get(url, params=params).json()

def get_image_url(path: str, size: str = "w500") -> str:
    """Construct image URL"""
    if not path:
        return "https://via.placeholder.com/500x750?text=No+Image"
    return f"{TMDB_IMAGE_BASE}/{size}{path}"

# ============================================================================
# Streaming Server Functions (Adapted from your code)
# ============================================================================

def api_validate(data: dict, path: str):
    """Check API response status"""
    if data.get("status") != 200:
        raise Exception(f"API Error: {data.get('error', 'unknown')}")
    return data["result"]

# PrimeSrc Server
def primesrc_get_servers(tmdb_id: str, media_type: str, season: str = None, episode: str = None) -> List[Dict]:
    """Fetch available servers from PrimeSrc"""
    if media_type == "movie":
        api_url = f"https://primesrc.me/api/v1/s?tmdb={tmdb_id}&type=movie"
    else:
        if not season or not episode:
            return []
        api_url = f"https://primesrc.me/api/v1/s?tmdb={tmdb_id}&season={season}&episode={episode}&type=tv"
    
    try:
        resp = requests.get(api_url, headers={"User-Agent": BASE_UA}, timeout=20).json()
        return resp.get("servers", [])
    except:
        return []

def primesrc_resolve_key(key: str) -> Optional[str]:
    """Resolve server key to embed URL"""
    embed_api = f"https://primesrc.me/api/v1/l?key={key}"
    solve_url = f"{ENCDEC_API}/solve-primesrc?url={quote(embed_api)}"
    try:
        data = requests.get(solve_url, headers={"User-Agent": BASE_UA}, timeout=15).json()
        if data.get("status") == 200:
            return data["result"]
        return None
    except:
        return None

def decrypt_voe(voe_embed_url: str) -> Optional[str]:
    """Decrypt Voe.sx embed to get m3u8 URL"""
    import codecs
    from bs4 import BeautifulSoup
    
    def clean_symbols(s):
        for p in ["@$", "^^", "~@", "%?", "*~", "!!", "#&"]:
            s = re.sub(re.escape(p), "_", s)
        return s
    
    def shift_back(s, n):
        return ''.join(chr(ord(c) - n) for c in s)
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": BASE_UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    
    try:
        html = session.get(voe_embed_url, timeout=20).text
        soup = BeautifulSoup(html, 'html.parser')
        script_tag = soup.find('script', attrs={'type': 'application/json'})
        if not script_tag:
            return None
        
        obfuscated = script_tag.string
        encoded = re.search(r'\["(.*?)"\]', obfuscated).group(1)
        
        decoded = codecs.decode(encoded, 'rot_13')
        decoded = clean_symbols(decoded)
        decoded = decoded.replace("_", "")
        decoded = base64.b64decode(decoded).decode()
        decoded = shift_back(decoded, 3)
        decoded = decoded[::-1]
        decoded = base64.b64decode(decoded).decode()
        data = json.loads(decoded)
        return data.get('source')
    except Exception as e:
        return None

# VidFast Server
def vidfast_extract(tmdb_id: str, media_type: str, season: str = "1", episode: str = "1") -> Optional[str]:
    """Extract stream from VidFast"""
    version = "1"
    headers = {
        "User-Agent": BASE_UA,
        "Referer": "https://vidfast.pro/",
        "X-Requested-With": "XMLHttpRequest",
    }
    
    try:
        base_url = f"https://vidfast.pro/{media_type}/{tmdb_id}/{season}/{episode}/"
        response = requests.get(base_url).text
        
        match = re.search(r'\\"en\\":\\"(.*?)\\"', response)
        if not match:
            return None
        text = match.group(1)
        
        enc_path = f"{ENCDEC_API}/enc-vidfast?text={text}&version={version}"
        parts = api_validate(requests.get(enc_path).json(), enc_path)
        headers["X-CSRF-Token"] = parts["token"]
        
        servers_encrypted = requests.post(parts["servers"], headers=headers).text
        dec_path = f"{ENCDEC_API}/dec-vidfast"
        servers_decrypted = api_validate(
            requests.post(dec_path, json={"text": servers_encrypted, "version": version}).json(),
            dec_path
        )
        
        if servers_decrypted:
            server = servers_decrypted[0]
            stream_url = f"{parts['stream']}/{server['data']}"
            stream_enc = requests.post(stream_url, headers=headers).text
            stream_dec = api_validate(
                requests.post(dec_path, json={"text": stream_enc, "version": version}).json(),
                dec_path
            )
            return stream_dec if isinstance(stream_dec, str) else stream_dec.get("url")
        return None
    except Exception as e:
        return None

# VidLink Server
def vidlink_extract(tmdb_id: str, media_type: str, season: str = "1", episode: str = "1") -> Optional[str]:
    """Extract stream from VidLink"""
    headers = {
        "User-Agent": BASE_UA,
        "Origin": "https://vidlink.pro",
        "Referer": "https://vidlink.pro/",
    }
    
    try:
        enc_path = f"{ENCDEC_API}/enc-vidlink?text={tmdb_id}"
        encrypted = api_validate(requests.get(enc_path).json(), enc_path)
        
        if media_type == "movie":
            url = f"https://vidlink.pro/api/b/movie/{encrypted}"
        else:
            url = f"https://vidlink.pro/api/b/tv/{encrypted}/{season}/{episode}"
        
        data = requests.get(url, headers=headers).json()
        
        # Extract m3u8 from response
        if isinstance(data, dict):
            if "sources" in data and data["sources"]:
                return data["sources"][0].get("file")
            if "url" in data:
                return data["url"]
        return None
    except Exception as e:
        return None

# Videasy Server
def videasy_extract(tmdb_id: str, server: str = "mb-flix") -> Optional[str]:
    """Extract stream from Videasy"""
    headers = {
        "Accept": "*/*",
        "Origin": "https://cineby.sc",
        "Referer": "https://cineby.sc/",
        "User-Agent": BASE_UA,
    }
    
    servers_map = {
        "mb-flix": "api",
        "1movies": "api",
        "moviebox": "api",
        "cdn": "api",
        "primesrcme": "api",
        "primewire": "api",
        "superflix": "api",
    }
    
    api_sub = servers_map.get(server, "api")
    api_url = f"https://{api_sub}.videasy.net/{server}/sources-with-title?mediaType=movie&tmdbId={tmdb_id}"
    
    try:
        encrypted = requests.get(api_url, headers=headers, timeout=30).text
        if not encrypted or len(encrypted.strip()) < 10:
            return None
        
        response = requests.post(
            f"{ENCDEC_API}/dec-videasy",
            json={"text": encrypted, "id": str(tmdb_id)},
            headers={"User-Agent": BASE_UA, "Content-Type": "application/json"},
            timeout=30,
        ).json()
        
        if response.get("status") != 200:
            return None
        
        decrypted = response["result"]
        
        # Extract m3u8 URLs
        def find_streams(obj):
            found = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, str) and "http" in v and (".m3u8" in v or "/master" in v):
                        found.append(v)
                    found.extend(find_streams(v))
            elif isinstance(obj, list):
                for item in obj:
                    found.extend(find_streams(item))
            return found
        
        streams = find_streams(decrypted)
        return streams[0] if streams else None
    except:
        return None

# AnimeKai Server
def animekai_extract(anime_id: str, season: str = "1", episode: str = "1") -> Optional[str]:
    """Extract stream from AnimeKai"""
    headers = {
        "User-Agent": BASE_UA,
        "Referer": "https://animekai.to/",
        "Accept": "application/json",
    }
    
    try:
        # This is simplified - full implementation would need more steps
        # For demo purposes, returning None - implement full pipeline if needed
        return None
    except:
        return None

# Universal stream extractor
def extract_stream(server: str, tmdb_id: str, media_type: str, season: str = "1", episode: str = "1") -> Optional[Dict]:
    """Extract stream URL from selected server"""
    st.write(f"🔄 Extracting from {server}...")
    
    result = {
        "server": server,
        "url": None,
        "referer": None,
        "quality": None,
        "error": None
    }
    
    try:
        if server == "PrimeSrc":
            servers = primesrc_get_servers(tmdb_id, media_type, season, episode)
            for srv in servers:
                link = primesrc_resolve_key(srv.get("key", ""))
                if link and "voe.sx" in link:
                    m3u8 = decrypt_voe(link)
                    if m3u8:
                        result["url"] = m3u8
                        result["quality"] = srv.get("quality", "Unknown")
                        result["referer"] = "https://voe.sx/"
                        break
        
        elif server == "VidFast":
            url = vidfast_extract(tmdb_id, media_type, season, episode)
            if url:
                result["url"] = url
                result["referer"] = "https://vidfast.pro/"
        
        elif server == "VidLink":
            url = vidlink_extract(tmdb_id, media_type, season, episode)
            if url:
                result["url"] = url
                result["referer"] = "https://vidlink.pro/"
        
        elif server == "Videasy":
            url = videasy_extract(tmdb_id)
            if url:
                result["url"] = url
                result["referer"] = "https://player.videasy.net/"
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

# ============================================================================
# Main UI Components
# ============================================================================

def display_movie_card(movie: Dict):
    """Display movie/TV show card in search results"""
    col1, col2 = st.columns([1, 4])
    
    poster_path = movie.get("poster_path")
    if poster_path:
        poster_url = get_image_url(poster_path, "w200")
    else:
        poster_url = "https://via.placeholder.com/200x300?text=No+Image"
    
    with col1:
        st.image(poster_url, use_container_width=True)
    
    with col2:
        title = movie.get("title") or movie.get("name")
        year = ""
        if movie.get("release_date"):
            year = movie.get("release_date", "")[:4]
        elif movie.get("first_air_date"):
            year = movie.get("first_air_date", "")[:4]
        
        st.markdown(f"### {title} ({year})")
        
        if movie.get("vote_average"):
            st.markdown(f"⭐ {movie['vote_average']:.1f}/10")
        
        overview = movie.get("overview", "")
        if overview:
            st.markdown(f"*{overview[:200]}...*" if len(overview) > 200 else f"*{overview}*")
        
        media_type = movie.get("media_type", "movie")
        if media_type == "movie":
            if st.button(f"Watch Movie", key=f"watch_{movie['id']}"):
                st.session_state.selected_movie = movie
                st.session_state.selected_tv = None
                st.session_state.current_streams = []
                st.rerun()
        else:
            if st.button(f"Watch Series", key=f"watch_{movie['id']}"):
                st.session_state.selected_tv = movie
                st.session_state.selected_movie = None
                st.session_state.current_streams = []
                st.rerun()

def video_player(m3u8_url: str, referer: str = None):
    """Display video player with m3u8 stream"""
    import streamlit.components.v1 as components
    
    # Extract quality from URL if possible
    quality = "Unknown"
    if "720" in m3u8_url:
        quality = "720p"
    elif "1080" in m3u8_url:
        quality = "1080p"
    elif "480" in m3u8_url:
        quality = "480p"
    
    st.markdown(f"""
    <div class="stream-info">
        <strong>🎬 Stream URL:</strong> <code>{m3u8_url[:100]}...</code><br>
        <strong>📺 Quality:</strong> <span class="quality-badge">{quality}</span>
        <strong>🔗 Referer:</strong> <code>{referer if referer else 'None'}</code>
    </div>
    """, unsafe_allow_html=True)
    
    # HLS.js player
    player_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <link href="https://vjs.zencdn.net/7.20.3/video-js.css" rel="stylesheet">
        <script src="https://vjs.zencdn.net/7.20.3/video.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/videojs-contrib-hls@5.15.0/dist/videojs-contrib-hls.min.js"></script>
        <style>
            .video-js {{ width: 100%; height: 100%; }}
            body {{ margin: 0; padding: 0; background: black; }}
        </style>
    </head>
    <body>
        <video-js id="my-video" class="vjs-default-skin" controls preload="auto" width="100%" height="500">
            <source src="{m3u8_url}" type="application/x-mpegURL">
        </video-js>
        <script>
            var player = videojs('my-video', {{
                html5: {{
                    hls: {{
                        enableLowInitialPlaylist: true,
                        smoothQualityChange: true,
                        overrideNative: true
                    }}
                }}
            }});
        </script>
    </body>
    </html>
    """
    
    components.html(player_html, height=520)

# ============================================================================
# Main App
# ============================================================================

def main():
    st.title("🎬 Advanced Streaming Hub")
    st.markdown("Stream movies and TV shows from multiple sources with automatic m3u8 extraction")
    
    # Sidebar
    with st.sidebar:
        st.image("https://via.placeholder.com/300x100?text=Streaming+HUB", use_container_width=True)
        st.markdown("---")
        
        # Search section
        st.markdown("### 🔍 Search")
        search_type = st.radio("Type", ["Movies", "TV Shows", "All"], horizontal=True)
        search_query = st.text_input("Enter title:", placeholder="e.g., Inception, Breaking Bad")
        
        if search_query:
            media_type = "movie" if search_type == "Movies" else "tv" if search_type == "TV Shows" else "all"
            results = search_tmdb(search_query, media_type)
            
            if results:
                st.markdown(f"### 📋 Results ({len(results)})")
                for result in results[:10]:
                    title = result.get("title") or result.get("name")
                    year = ""
                    if result.get("release_date"):
                        year = f"({result['release_date'][:4]})"
                    elif result.get("first_air_date"):
                        year = f"({result['first_air_date'][:4]})"
                    
                    if st.button(f"{title} {year}", key=f"sidebar_{result['id']}"):
                        if result.get("media_type") == "movie":
                            st.session_state.selected_movie = result
                            st.session_state.selected_tv = None
                        else:
                            st.session_state.selected_tv = result
                            st.session_state.selected_movie = None
                        st.session_state.current_streams = []
                        st.rerun()
            elif search_query:
                st.info("No results found")
        
        st.markdown("---")
        st.markdown("### ⚙️ Server Configuration")
        st.markdown("""
        **Supported Servers:**
        - 🚀 PrimeSrc (Recommended)
        - ⚡ VidFast
        - 🔗 VidLink
        - 🎥 Videasy
        
        *Streams are extracted on-demand*
        """)
    
    # Main content area
    if st.session_state.selected_movie:
        movie = st.session_state.selected_movie
        movie_id = movie["id"]
        details = get_movie_details(movie_id)
        
        # Display movie info
        col1, col2 = st.columns([1, 2])
        
        with col1:
            poster = get_image_url(details.get("poster_path"), "w300")
            st.image(poster, use_container_width=True)
        
        with col2:
            st.markdown(f"## {details.get('title')} ({details.get('release_date', '')[:4]})")
            if details.get("vote_average"):
                st.markdown(f"**Rating:** ⭐ {details['vote_average']:.1f}/10 ({details.get('vote_count', 0)} votes)")
            if details.get("genres"):
                genres = ", ".join([g["name"] for g in details["genres"]])
                st.markdown(f"**Genres:** {genres}")
            if details.get("runtime"):
                hours = details["runtime"] // 60
                minutes = details["runtime"] % 60
                st.markdown(f"**Duration:** {hours}h {minutes}m")
            st.markdown("---")
            st.markdown("### 📖 Overview")
            st.markdown(details.get("overview", "No overview available"))
        
        # Server selection
        st.markdown("---")
        st.markdown("## 🎥 Select Streaming Source")
        
        servers = ["PrimeSrc", "VidFast", "VidLink", "Videasy"]
        selected_server = st.selectbox("Choose server:", servers, key="movie_server")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("🔍 Extract Stream", type="primary", use_container_width=True):
                with st.spinner(f"Extracting from {selected_server}..."):
                    result = extract_stream(selected_server, str(movie_id), "movie")
                    if result and result["url"]:
                        st.session_state.current_m3u8 = result["url"]
                        st.session_state.current_referer = result["referer"]
                        st.success(f"✅ Stream extracted successfully! Quality: {result.get('quality', 'Unknown')}")
                    else:
                        st.error(f"Failed to extract stream from {selected_server}")
                        if result and result.get("error"):
                            st.error(f"Error: {result['error']}")
        
        with col2:
            if st.session_state.current_m3u8:
                if st.button("🔄 Clear Stream", use_container_width=True):
                    st.session_state.current_m3u8 = None
                    st.session_state.current_referer = None
                    st.rerun()
        
        # Video player
        if st.session_state.current_m3u8:
            st.markdown("---")
            st.markdown("## 📺 Now Playing")
            video_player(st.session_state.current_m3u8, st.session_state.current_referer)
    
    elif st.session_state.selected_tv:
        tv_show = st.session_state.selected_tv
        tv_id = tv_show["id"]
        details = get_tv_details(tv_id)
        
        # Display TV show info
        col1, col2 = st.columns([1, 2])
        
        with col1:
            poster = get_image_url(details.get("poster_path"), "w300")
            st.image(poster, use_container_width=True)
        
        with col2:
            st.markdown(f"## {details.get('name')} ({details.get('first_air_date', '')[:4]})")
            if details.get("vote_average"):
                st.markdown(f"**Rating:** ⭐ {details['vote_average']:.1f}/10 ({details.get('vote_count', 0)} votes)")
            if details.get("genres"):
                genres = ", ".join([g["name"] for g in details["genres"]])
                st.markdown(f"**Genres:** {genres}")
            if details.get("number_of_seasons"):
                st.markdown(f"**Seasons:** {details.get('number_of_seasons')} | **Episodes:** {details.get('number_of_episodes')}")
            st.markdown("---")
            st.markdown("### 📖 Overview")
            st.markdown(details.get("overview", "No overview available"))
        
        # Season/Episode selection
        st.markdown("---")
        st.markdown("## 📺 Season & Episode Selection")
        
        seasons = details.get("seasons", [])
        season_numbers = [s["season_number"] for s in seasons if s["season_number"] > 0]
        
        if season_numbers:
            col1, col2 = st.columns(2)
            with col1:
                selected_season = st.selectbox("Season:", season_numbers, key="tv_season")
            with col2:
                # Get episodes for selected season
                season_data = get_tv_seasons(tv_id, selected_season)
                episodes = season_data.get("episodes", [])
                episode_numbers = [e["episode_number"] for e in episodes]
                selected_episode = st.selectbox("Episode:", episode_numbers, key="tv_episode")
            
            # Server selection
            st.markdown("### 🎥 Select Streaming Source")
            servers = ["PrimeSrc", "VidFast", "VidLink"]
            selected_server = st.selectbox("Choose server:", servers, key="tv_server")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("🔍 Extract Stream", type="primary", use_container_width=True):
                    with st.spinner(f"Extracting S{selected_season}E{selected_episode} from {selected_server}..."):
                        result = extract_stream(
                            selected_server, str(tv_id), "tv",
                            str(selected_season), str(selected_episode)
                        )
                        if result and result["url"]:
                            st.session_state.current_m3u8 = result["url"]
                            st.session_state.current_referer = result["referer"]
                            st.success(f"✅ Stream extracted successfully! Quality: {result.get('quality', 'Unknown')}")
                        else:
                            st.error(f"Failed to extract stream from {selected_server}")
                            if result and result.get("error"):
                                st.error(f"Error: {result['error']}")
            
            with col2:
                if st.session_state.current_m3u8:
                    if st.button("🔄 Clear Stream", use_container_width=True):
                        st.session_state.current_m3u8 = None
                        st.session_state.current_referer = None
                        st.rerun()
            
            # Video player
            if st.session_state.current_m3u8:
                st.markdown("---")
                st.markdown(f"## 📺 Now Playing: S{selected_season}E{selected_episode}")
                video_player(st.session_state.current_m3u8, st.session_state.current_referer)
    
    else:
        # Welcome screen
        st.markdown("""
        <div style="text-align: center; padding: 50px;">
            <h2>🎬 Welcome to Advanced Streaming Hub</h2>
            <p>Search for movies or TV shows in the sidebar to get started</p>
            <br>
            <h4>✨ Features:</h4>
            <ul style="list-style: none; text-align: center;">
                <li>🔍 Search TMDB database for movies and TV shows</li>
                <li>🎥 Multiple streaming servers (PrimeSrc, VidFast, VidLink, Videasy)</li>
                <li>📺 Automatic m3u8 extraction and playback</li>
                <li>🎨 Modern, responsive interface</li>
                <li>⚡ Fast stream extraction</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
        # Featured content
        st.markdown("### 🔥 Popular Now")
        popular_movies = search_tmdb("", "movie")[:6]
        
        cols = st.columns(3)
        for idx, movie in enumerate(popular_movies[:3]):
            with cols[idx]:
                poster = get_image_url(movie.get("poster_path"), "w300")
                st.image(poster, use_container_width=True)
                st.caption(movie.get("title", "")[:30])

if __name__ == "__main__":
    main()