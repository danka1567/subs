"""
enc_dec_streamlit.py
====================
Advanced Streamlit UI for enc-dec.app multi-site decryptor.
Features:
  - TMDB search (movies & TV) with poster art, cast, ratings
  - Auto-fills all IDs (TMDB, IMDB) + episode/season pickers
  - Real-time extraction logs streamed into the UI
  - Per-site configuration panels
  - Downloadable results (JSON / plain)
  - Dark themed, responsive layout

Run:
    pip install streamlit requests pycryptodome json5 beautifulsoup4
    streamlit run enc_dec_streamlit.py
"""

import codecs
import hashlib
import json
import re
import sys
import time
import base64
import threading
import queue
from base64 import b64decode
from io import StringIO
from urllib.parse import quote, quote_plus, urlparse, parse_qs, unquote

import requests
import streamlit as st
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
API            = "https://enc-dec.app/api"
TMDB_API_KEY   = "6fad3f86b8452ee232deb7977d7dcf58"
TMDB_BASE      = "https://api.themoviedb.org/3"
TMDB_IMG_BASE  = "https://image.tmdb.org/t/p/w342"
BASE_UA        = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36"
)
QUALITY_RANK   = ["360p", "480p", "720p", "1080p", "2160p", "4k"]

VIDEASY_SERVERS = [
    ("mb-flix","api"),("1movies","api"),("moviebox","api"),("cdn","api"),
    ("primesrcme","api"),("primewire","api"),("m4uhd","api2"),("hdmovie","api"),
    ("lamovie","api"),("superflix","api"),("cuevana","api2"),("overflix","api2"),
    ("visioncine","api"),("meine","api"),
]

YFLIX_SUPPORTED_HOSTS = {
    "yflix.to":          "https://yflix.to",
    "www.yflix.to":      "https://yflix.to",
    "1movies.bz":        "https://1movies.bz",
    "www.1movies.bz":    "https://1movies.bz",
    "solarmovie.fi":     "https://solarmovie.fi",
    "www.solarmovie.fi": "https://solarmovie.fi",
}

SITE_DESCRIPTIONS = {
    "Videasy":      "player.videasy.net — Multi-server M3U8 pipeline",
    "VidSync":      "vidsync.xyz — Encrypted stream resolver",
    "VidLink":      "vidlink.pro — Encrypted ID resolver",
    "VidFast":      "vidfast.pro — CSRF-protected stream extractor",
    "Hexa/Flixer":  "hexa.su / flixer.su — AES key exchange decryptor",
    "LordFlix":     "lordflix.org — Signed URL resolver",
    "Abyss":        "playhydrax.com — Variable-based decryptor",
    "KissKH":       "kisskh.do — Drama/subtitle resolver",
    "OneTouchTV":   "api3.devcorp.me — VOD decryptor",
    "PrimeSrc":     "primesrc.me — Full pipeline + Voe M3U8",
    "Reanime":      "reanime.to — Anime M3U8 token resolver",
    "XPrime":       "mznxiwqjdiq00239q.space — PoW-protected extractor",
    "AnimeKai":     "animekai.to — Full sub/dub/softsub pipeline",
    "YFlix/1Movies":"yflix.to / 1movies.bz — Full server pipeline",
}

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="enc-dec.app Extractor",
    page_icon="🔓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* ── Global ── */
  [data-testid="stAppViewContainer"] { background: #0e1117; }
  [data-testid="stSidebar"] { background: #161b22; border-right: 1px solid #30363d; }
  h1, h2, h3 { color: #e6edf3; }

  /* ── Media card ── */
  .media-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 14px;
    cursor: pointer;
    transition: all .2s ease;
    display: flex;
    gap: 14px;
    align-items: flex-start;
  }
  .media-card:hover { border-color: #58a6ff; background: #1c2128; transform: translateY(-2px); }
  .media-card.selected { border-color: #3fb950; background: #1a2b1c; }
  .media-card img { border-radius: 8px; width: 70px; min-width: 70px; height: 105px; object-fit: cover; }
  .card-body { flex: 1; }
  .card-title { color: #e6edf3; font-weight: 700; font-size: 15px; margin-bottom: 4px; }
  .card-meta  { color: #8b949e; font-size: 12px; margin-bottom: 6px; }
  .card-overview { color: #c9d1d9; font-size: 12px; line-height: 1.5;
                   display: -webkit-box; -webkit-line-clamp: 3;
                   -webkit-box-orient: vertical; overflow: hidden; }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 20px;
    font-size: 11px; font-weight: 600; margin-right: 4px;
  }
  .badge-movie { background: #1f6feb; color: #fff; }
  .badge-tv    { background: #6e40c9; color: #fff; }
  .badge-score { background: #1a3a1a; color: #3fb950; border: 1px solid #3fb950; }

  /* ── Log box ── */
  .log-container {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 14px;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    max-height: 400px;
    overflow-y: auto;
    color: #c9d1d9;
  }
  .log-ok   { color: #3fb950; }
  .log-err  { color: #f85149; }
  .log-info { color: #58a6ff; }
  .log-warn { color: #d29922; }

  /* ── Stream result ── */
  .stream-url {
    background: #1a3a1a; border: 1px solid #3fb950; border-radius: 6px;
    padding: 10px 14px; font-family: monospace; font-size: 12px;
    color: #3fb950; word-break: break-all; margin: 6px 0;
  }

  /* ── Site badge ── */
  .site-header {
    background: linear-gradient(135deg, #1f6feb22, #6e40c922);
    border: 1px solid #30363d; border-radius: 10px;
    padding: 12px 16px; margin-bottom: 16px;
  }
  .site-header h3 { margin: 0; color: #58a6ff; font-size: 18px; }
  .site-header p  { margin: 4px 0 0; color: #8b949e; font-size: 13px; }

  /* ── Buttons ── */
  .stButton > button {
    background: linear-gradient(135deg, #1f6feb, #388bfd) !important;
    color: #fff !important; border: none !important;
    border-radius: 8px !important; font-weight: 600 !important;
    transition: opacity .2s !important;
  }
  .stButton > button:hover { opacity: .85 !important; }

  /* ── Input fields ── */
  .stTextInput input, .stSelectbox select, .stNumberInput input {
    background: #161b22 !important; color: #e6edf3 !important;
    border-color: #30363d !important;
  }

  /* ── Divider ── */
  hr { border-color: #30363d !important; }

  /* ── Metric ── */
  [data-testid="metric-container"] {
    background: #161b22; border: 1px solid #30363d;
    border-radius: 10px; padding: 12px;
  }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Session state init
# ─────────────────────────────────────────────────────────────────────────────
for k, v in {
    "search_results": [],
    "selected_media": None,
    "extraction_log": [],
    "extracted_streams": [],
    "seasons_data": {},
    "last_search_query": "",
    "running": False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────────────────────
# TMDB helpers
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def tmdb_search(query: str, media_type: str = "multi") -> list:
    url  = f"{TMDB_BASE}/search/{media_type}"
    resp = requests.get(url, params={"api_key": TMDB_API_KEY, "query": query,
                                     "page": 1, "include_adult": False}, timeout=10)
    if resp.status_code != 200:
        return []
    return resp.json().get("results", [])


@st.cache_data(ttl=300, show_spinner=False)
def tmdb_get_details(tmdb_id: int, media_type: str) -> dict:
    url  = f"{TMDB_BASE}/{media_type}/{tmdb_id}"
    resp = requests.get(url, params={"api_key": TMDB_API_KEY,
                                     "append_to_response": "external_ids"}, timeout=10)
    return resp.json() if resp.status_code == 200 else {}


@st.cache_data(ttl=300, show_spinner=False)
def tmdb_get_seasons(tmdb_id: int) -> list:
    details = tmdb_get_details(tmdb_id, "tv")
    return details.get("seasons", [])


@st.cache_data(ttl=300, show_spinner=False)
def tmdb_get_episodes(tmdb_id: int, season_num: int) -> list:
    url  = f"{TMDB_BASE}/tv/{tmdb_id}/season/{season_num}"
    resp = requests.get(url, params={"api_key": TMDB_API_KEY}, timeout=10)
    return resp.json().get("episodes", []) if resp.status_code == 200 else []


def get_imdb_id(details: dict) -> str:
    return (details.get("external_ids") or {}).get("imdb_id", "") or details.get("imdb_id", "")


def poster_url(path: str) -> str:
    if not path:
        return "https://via.placeholder.com/70x105/161b22/8b949e?text=No+Img"
    return f"{TMDB_IMG_BASE}{path}"

# ─────────────────────────────────────────────────────────────────────────────
# Log helpers
# ─────────────────────────────────────────────────────────────────────────────
def log(msg: str, level: str = "info"):
    ts  = time.strftime("%H:%M:%S")
    tag = {"ok": "✅", "err": "❌", "info": "ℹ️", "warn": "⚠️"}.get(level, "•")
    st.session_state.extraction_log.append((ts, tag, msg, level))


def render_logs():
    if not st.session_state.extraction_log:
        return
    lines = []
    for ts, tag, msg, level in st.session_state.extraction_log[-80:]:
        cls = {"ok": "log-ok", "err": "log-err", "info": "log-info", "warn": "log-warn"}.get(level, "")
        lines.append(f'<span class="log-info">[{ts}]</span> {tag} <span class="{cls}">{msg}</span>')
    html = "<br>".join(lines)
    st.markdown(f'<div class="log-container">{html}</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Validate helper
# ─────────────────────────────────────────────────────────────────────────────
def validate(data: dict, path: str):
    if data.get("status") != 200:
        raise Exception(f"API error at {path}: {data.get('error', 'unknown')}")
    return data["result"]

# ─────────────────────────────────────────────────────────────────────────────
# Site extraction functions (streamlit-aware, logging to session state)
# ─────────────────────────────────────────────────────────────────────────────

def extract_videasy(tmdb_id, media_type="movie", season="1", episode="1"):
    streams = []
    mt = "movie" if media_type == "movie" else "tv"
    headers = {
        "Accept": "*/*", "Origin": "https://cineby.sc",
        "Referer": "https://cineby.sc/", "User-Agent": BASE_UA,
    }
    def find_streams(obj):
        found, seen = [], set()
        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if isinstance(v, str) and v.startswith("http") and v not in seen:
                        if ".m3u8" in v or "/master" in v:
                            found.append(v); seen.add(v)
                    walk(v)
            elif isinstance(node, list):
                [walk(i) for i in node]
        walk(obj); return found

    for server, api_sub in VIDEASY_SERVERS:
        if mt == "movie":
            api_url = f"https://{api_sub}.videasy.net/{server}/sources-with-title?mediaType=movie&tmdbId={tmdb_id}"
        else:
            api_url = f"https://{api_sub}.videasy.net/{server}/sources-with-title?mediaType=tv&tmdbId={tmdb_id}&season={season}&episode={episode}"
        try:
            log(f"Trying Videasy server: {server}")
            enc = requests.get(api_url, headers=headers, timeout=20).text
            if not enc or len(enc.strip()) < 10:
                log(f"{server}: empty response", "warn"); continue
            resp = requests.post(f"{API}/dec-videasy", json={"text": enc, "id": str(tmdb_id)},
                                 headers={"User-Agent": BASE_UA, "Content-Type": "application/json"},
                                 timeout=20).json()
            if resp.get("status") != 200:
                log(f"{server}: {resp.get('error')}", "warn"); continue
            found = find_streams(resp["result"])
            if found:
                log(f"{server}: {len(found)} stream(s) found", "ok")
                for s in found:
                    streams.append({"server": server, "url": s, "type": "m3u8"})
                break
        except Exception as e:
            log(f"{server}: {e}", "err")
    return streams


def extract_vidsync(tmdb_id, imdb_id, title, media_type, year, season, episode, server):
    headers = {
        "Accept": "*/*", "Origin": "https://vidsync.xyz",
        "Referer": "https://vidsync.xyz/", "User-Agent": BASE_UA,
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        enc_path = f"{API}/enc-vidsync"
        log("Fetching VidSync token...")
        enc_data = validate(requests.get(enc_path, timeout=15).json(), enc_path)
        headers["X-Cf-Turnstile"] = enc_data["token"]
        mt = "movie" if media_type == "movie" else "tv"
        url = (f"https://vidsync.xyz/api/stream/fetch?title={quote_plus(title)}&type={mt}"
               f"&releaseYear={year}&mediaId={tmdb_id}&serverName={server}"
               f"&season={season}&episode={episode}")
        text = requests.get(url, headers=headers, timeout=20).text
        dec  = validate(requests.post(f"{API}/dec-vidsync",
                                      json={"text": text, "id": tmdb_id}, timeout=20).json(),
                        f"{API}/dec-vidsync")
        log("VidSync decrypted successfully", "ok")
        return [{"server": server, "url": str(dec), "type": "raw"}]
    except Exception as e:
        log(f"VidSync error: {e}", "err"); return []


def extract_vidlink(tmdb_id, media_type, season, episode):
    try:
        log("Encrypting VidLink ID...")
        enc = validate(requests.get(f"{API}/enc-vidlink?text={tmdb_id}", timeout=15).json(),
                       f"{API}/enc-vidlink")
        mt  = "movie" if media_type == "movie" else "tv"
        url = f"https://vidlink.pro/api/b/{mt}/{enc}/{season}/{episode}"
        data = requests.get(url, headers={"User-Agent": BASE_UA, "Referer": "https://vidlink.pro/"}, timeout=20).json()
        log("VidLink resolved", "ok")
        streams = []
        def find_m3u8(obj, depth=0):
            if depth > 10: return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, str) and (".m3u8" in v or "master" in v):
                        streams.append({"server": "vidlink", "url": v, "type": "m3u8"})
                    find_m3u8(v, depth+1)
            elif isinstance(obj, list):
                [find_m3u8(i, depth+1) for i in obj]
        find_m3u8(data)
        if not streams:
            streams.append({"server": "vidlink", "url": json.dumps(data, indent=2), "type": "json"})
        return streams
    except Exception as e:
        log(f"VidLink error: {e}", "err"); return []


def extract_hexa(tmdb_id, media_type, season, episode):
    try:
        from Crypto.Random import get_random_bytes
    except ImportError:
        log("pycryptodome not installed", "err"); return []
    try:
        key = get_random_bytes(32).hex()
        headers = {
            "User-Agent": BASE_UA, "Referer": "https://hexa.su/",
            "Accept": "text/plain", "X-Fingerprint-Lite": "e9136c41504646444", "X-Api-Key": key,
        }
        token = validate(requests.get(f"{API}/enc-hexa", timeout=15).json(), f"{API}/enc-hexa")["token"]
        headers["X-Cap-Token"] = token
        mt = "movie" if media_type == "movie" else "tv"
        if mt == "movie":
            url = f"https://theemoviedb.hexa.su/api/tmdb/movie/{tmdb_id}/images"
        else:
            url = f"https://theemoviedb.hexa.su/api/tmdb/tv/{tmdb_id}/season/{season}/episode/{episode}/images"
        enc = requests.get(url, headers=headers, timeout=20).text
        dec = validate(requests.post(f"{API}/dec-hexa", json={"text": enc, "key": key}, timeout=20).json(), f"{API}/dec-hexa")
        log("Hexa decrypted", "ok")
        return [{"server": "hexa", "url": str(dec), "type": "raw"}]
    except Exception as e:
        log(f"Hexa error: {e}", "err"); return []


def extract_lordflix(tmdb_id, imdb_id, title, media_type, year, season, episode, server):
    try:
        mt = "movie" if media_type == "movie" else "series"
        url = (f"https://network.hasta-la-vista.site/?title={quote(title)}&type={mt}"
               f"&year={year}&imdb={imdb_id}&tmdb={tmdb_id}&server={server}"
               f"&season={season}&episode={episode}")
        data = validate(requests.get(f"{API}/enc-lordflix?url={quote(url)}", timeout=15).json(), "enc-lordflix")
        enc  = requests.get(data["url"], headers={"Referer": "https://lordflix.org/", "User-Agent": BASE_UA}, timeout=20).text
        dec  = validate(requests.post(f"{API}/dec-lordflix", json={"text": enc, "sign": data["sign"]}, timeout=20).json(), "dec-lordflix")
        log("LordFlix decrypted", "ok")
        return [{"server": server, "url": str(dec), "type": "raw"}]
    except Exception as e:
        log(f"LordFlix error: {e}", "err"); return []


def extract_primesrc(tmdb_id, imdb_id, media_type, season, episode):
    results = []
    def resolve_key(key):
        embed_api = f"https://primesrc.me/api/v1/l?key={key}"
        data = requests.get(f"{API}/solve-primesrc?url={quote(embed_api)}", timeout=15).json()
        if data.get("status") != 200: return None
        return data["result"]

    def quality_score(q):
        m = re.search(r'(\d{3,4})p?', (q or "").lower())
        return int(m.group(1)) if m else 0

    def voe_clean(s):
        for p in ["@$","^^","~@","%?","*~","!!","#&"]:
            s = re.sub(re.escape(p), "_", s)
        return s

    def decrypt_voe(voe_url):
        try:
            domain  = '{uri.scheme}://{uri.netloc}/'.format(uri=urlparse(voe_url))
            html    = requests.get(voe_url, headers={"Referer": domain, "User-Agent": BASE_UA}, timeout=20).text
            if 'Redirecting...' in html:
                redirect_url = re.search(r"href\s*=\s*'(.*?)';", html).group(1)
                html = requests.get(redirect_url, headers={"Referer": domain, "User-Agent": BASE_UA}, timeout=20).text
            soup    = BeautifulSoup(html, 'html.parser')
            script  = soup.find('script', attrs={'type': 'application/json'})
            if not script: return None
            encoded = re.search(r'\["(.*?)"\]', script.string).group(1)
            decoded = codecs.decode(encoded, 'rot_13')
            decoded = voe_clean(decoded).replace("_","")
            decoded = b64decode(decoded).decode()
            decoded = ''.join(chr(ord(c)-3) for c in decoded)[::-1]
            decoded = b64decode(decoded).decode()
            return json.loads(decoded).get('source')
        except Exception as e:
            log(f"Voe decrypt error: {e}", "err"); return None

    try:
        mt = "movie" if media_type == "movie" else "tv"
        id_param = f"imdb={imdb_id}" if imdb_id else f"tmdb={tmdb_id}"
        if mt == "movie":
            api_url = f"https://primesrc.me/api/v1/s?{id_param}&type=movie"
        else:
            api_url = f"https://primesrc.me/api/v1/s?{id_param}&season={season}&episode={episode}&type=tv"
        log(f"Fetching PrimeSrc servers...")
        servers = requests.get(api_url, headers={"User-Agent": BASE_UA}, timeout=20).json().get("servers", [])
        log(f"PrimeSrc: {len(servers)} server(s) found")

        voe_entries = []
        for srv in servers:
            link = resolve_key(srv.get("key",""))
            if link:
                log(f"  {srv.get('name','?')}: resolved", "ok")
                results.append({"server": srv.get("name","?"), "url": link, "quality": srv.get("quality",""), "type": "embed"})
                if "voe.sx" in link:
                    voe_entries.append({"link": link, "quality": srv.get("quality","")})
            else:
                log(f"  {srv.get('name','?')}: failed", "warn")

        voe_entries.sort(key=lambda r: quality_score(r["quality"]), reverse=True)
        for ve in voe_entries:
            log(f"Decrypting Voe [{ve['quality']}]...")
            m3u8 = decrypt_voe(ve["link"])
            if m3u8:
                results.append({"server": f"voe-{ve['quality']}", "url": m3u8, "type": "m3u8"})
                log(f"Voe M3U8 extracted: {m3u8[:60]}…", "ok")
    except Exception as e:
        log(f"PrimeSrc error: {e}", "err")
    return results


def extract_animekai(anime_url, season, episode):
    KAI_HEADERS = {"User-Agent": BASE_UA, "Referer": "https://animekai.to/", "Accept": "application/json"}
    def kai_enc(t): return requests.get(f"{API}/enc-kai?text={t}").json()["result"]
    def kai_dec(t): return requests.post(f"{API}/dec-kai", json={"text": t}).json()["result"]
    def kai_parse(h): return requests.post(f"{API}/parse-html", json={"text": h}).json()["result"]
    def kai_dec_mega(t): return requests.post(f"{API}/dec-mega", json={"text": t, "agent": BASE_UA}).json()

    results = []
    try:
        html  = requests.get(anime_url, headers={**KAI_HEADERS, "Accept": "text/html"}, timeout=20).text
        match = re.search(r'<div[^>]*id="anime-rating"[^>]*data-id="([^"]+)"', html)
        if not match: log("AnimeKai: content ID not found", "err"); return []
        cid   = match.group(1)
        log(f"AnimeKai content ID: {cid}")

        enc_id   = kai_enc(cid)
        eps_resp = requests.get(f"https://animekai.to/ajax/episodes/list?ani_id={cid}&_={enc_id}", headers=KAI_HEADERS).json()
        episodes = kai_parse(eps_resp["result"])

        if season not in episodes or episode not in episodes[season]:
            log(f"AnimeKai: S{season}E{episode} not found", "err"); return []

        token  = episodes[season][episode]["token"]
        enc_tk = kai_enc(token)
        svr_resp = requests.get(f"https://animekai.to/ajax/links/list?token={token}&_={enc_tk}", headers=KAI_HEADERS).json()
        servers  = kai_parse(svr_resp["result"])

        for type_key, smap in servers.items():
            for sidx, sinfo in smap.items():
                lid = sinfo.get("lid")
                if not lid: continue
                try:
                    enc_lid  = kai_enc(lid)
                    er       = requests.get(f"https://animekai.to/ajax/links/view?id={lid}&_={enc_lid}", headers=KAI_HEADERS).json()
                    dec      = kai_dec(er["result"])
                    embed    = dec["url"]
                    referer  = embed.split("/e/")[0] + "/"
                    h        = {**KAI_HEADERS, "Referer": referer}
                    media    = embed.replace("/e/", "/media/")
                    enc_med  = requests.get(media, headers=h).json()["result"]
                    dr       = kai_dec_mega(enc_med)
                    if dr.get("status") == 200:
                        m3u8 = dr["result"].get("url") or (dr["result"].get("sources",[{}])[0].get("file"))
                        if m3u8:
                            results.append({"server": f"{type_key}/srv{sidx}", "url": m3u8, "type": "m3u8", "referer": referer})
                            log(f"AnimeKai [{type_key}/srv{sidx}]: OK", "ok")
                except Exception as e:
                    log(f"AnimeKai [{type_key}/srv{sidx}]: {e}", "err")
    except Exception as e:
        log(f"AnimeKai error: {e}", "err")
    return results


def extract_yflix(watch_url, season, episode):
    def flix_enc(t): return requests.get(f"{API}/enc-movies-flix?text={t}", headers={"User-Agent": BASE_UA}).json()["result"]
    def flix_dec(t): return requests.post(f"{API}/dec-movies-flix", json={"text": t}).json()["result"]
    def flix_parse(h): return requests.post(f"{API}/parse-html", json={"text": h}).json()["result"]
    def fh(ref, ajax=True):
        h = {"User-Agent": BASE_UA, "Referer": ref,
             "Accept": "application/json, text/plain, */*" if ajax else "text/html,*/*"}
        if ajax: h["X-Requested-With"] = "XMLHttpRequest"
        return h

    results = []
    try:
        host = urlparse(watch_url).netloc.lower()
        if host not in YFLIX_SUPPORTED_HOSTS: log(f"Unsupported host: {host}", "err"); return []
        base = YFLIX_SUPPORTED_HOSTS[host]

        html = requests.get(watch_url, headers=fh(base+"/", ajax=False), timeout=30).text
        patterns = [
            r'itemprop="aggregateRating"[^>]*data-id="([^"]+)"',
            r'data-id="([^"]+)"[^>]*itemprop="aggregateRating"',
            r'id="movie-rating"[^>]*data-id="([^"]+)"',
        ]
        cid = None
        for p in patterns:
            m = re.search(p, html)
            if m: cid = m.group(1); break
        if not cid: log("YFlix: content ID not found", "err"); return []
        log(f"YFlix content ID: {cid}")

        enc_id   = flix_enc(cid)
        eps_raw  = requests.get(f"{base}/ajax/episodes/list?id={cid}&_={enc_id}", headers=fh(base+"/")).json()
        episodes = flix_parse(eps_raw["result"])

        if season not in episodes or episode not in episodes[season]:
            log(f"YFlix: S{season}E{episode} not found", "err"); return []

        eid     = episodes[season][episode]["eid"]
        enc_eid = flix_enc(eid)
        srv_raw = requests.get(f"{base}/ajax/links/list?eid={eid}&_={enc_eid}", headers=fh(base+"/")).json()
        servers = flix_parse(srv_raw["result"])
        log(f"YFlix: {sum(len(v) for v in servers.values())} server(s)")

        for stype, smap in servers.items():
            for sidx, sinfo in smap.items():
                lid = sinfo["lid"]
                try:
                    enc_lid  = flix_enc(lid)
                    er       = requests.get(f"{base}/ajax/links/view?id={lid}&_={enc_lid}", headers=fh(base+"/")).json()
                    dec      = flix_dec(er["result"])
                    embed    = dec.get("url") if isinstance(dec, dict) else dec
                    if embed and "/iframe/" in embed:
                        r2 = requests.get(embed, headers=fh(base+"/", ajax=False), timeout=20)
                        m  = re.search(r'<iframe[^>]+src="([^"]+)"', r2.text, re.I)
                        if m: embed = m.group(1)

                    referer  = embed.split("/e/")[0] + "/"
                    media    = embed.replace("/e/", "/media/")
                    h2       = {"User-Agent": BASE_UA, "Referer": referer, "Accept": "application/json"}
                    enc_med  = requests.get(media, headers=h2, timeout=25).json().get("result","")

                    for dec_ep in ["dec-rapid", "dec-mega"]:
                        dr = requests.post(f"{API}/{dec_ep}", json={"text": enc_med, "agent": BASE_UA}, timeout=20).json()
                        if dr.get("status") == 200:
                            def find_m3u8(obj, found=[]):
                                if isinstance(obj, dict):
                                    for k, v in obj.items():
                                        if isinstance(v, str) and (".m3u8" in v or "/master" in v):
                                            found.append(v)
                                        find_m3u8(v, found)
                                elif isinstance(obj, list):
                                    [find_m3u8(i, found) for i in obj]
                                return found
                            urls = find_m3u8(dr["result"])
                            for u in urls:
                                results.append({"server": f"{stype}/{sidx}", "url": u, "type": "m3u8"})
                                log(f"YFlix [{stype}/{sidx}]: {u[:60]}…", "ok")
                            break
                except Exception as e:
                    log(f"YFlix [{stype}/{sidx}]: {e}", "err")
    except Exception as e:
        log(f"YFlix error: {e}", "err")
    return results

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar – Site selector
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔓 enc-dec.app")
    st.markdown("**Multi-site Stream Extractor**")
    st.markdown("---")

    site = st.selectbox(
        "🌐 Select Site",
        list(SITE_DESCRIPTIONS.keys()),
        format_func=lambda x: f"{'📺' if 'anime' in x.lower() or 'kai' in x.lower() or 'nime' in x.lower() else '🎬'} {x}",
    )
    st.caption(SITE_DESCRIPTIONS.get(site,""))
    st.markdown("---")

    media_filter = st.radio("🎭 Search For", ["Movie", "TV Show", "Both"], horizontal=True)
    st.markdown("---")
    st.markdown("**Quick Stats**")
    col1, col2 = st.columns(2)
    col1.metric("Sites", "14")
    col2.metric("Streams", len(st.session_state.extracted_streams))

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; padding: 20px 0 10px;">
  <h1 style="font-size:2.2rem; margin:0;">🔓 Stream Extractor</h1>
  <p style="color:#8b949e; margin:6px 0 0;">Powered by enc-dec.app · TMDB · 14 Supported Sites</p>
</div>
""", unsafe_allow_html=True)
st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# Step 1 – Search
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 🔍 Step 1 — Search for Media")

search_col, btn_col = st.columns([5, 1])
with search_col:
    query = st.text_input("", placeholder="Search movies or TV shows… e.g. 'Breaking Bad', 'Inception'",
                           label_visibility="collapsed")
with btn_col:
    search_btn = st.button("Search", use_container_width=True)

if search_btn and query.strip():
    st.session_state.selected_media = None
    st.session_state.extracted_streams = []
    st.session_state.extraction_log = []
    with st.spinner("Searching TMDB…"):
        mt_map = {"Movie": "movie", "TV Show": "tv", "Both": "multi"}
        mt     = mt_map.get(media_filter, "multi")
        results = tmdb_search(query.strip(), mt)
        # Filter by type if needed
        if media_filter == "Movie":
            results = [r for r in results if r.get("media_type","movie") == "movie"]
        elif media_filter == "TV Show":
            results = [r for r in results if r.get("media_type","tv") == "tv"]
        st.session_state.search_results = results[:12]

# ─────────────────────────────────────────────────────────────────────────────
# Step 2 – Results grid
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.search_results:
    st.markdown(f"**{len(st.session_state.search_results)} results** — click to select:")
    cols = st.columns(3)

    for idx, item in enumerate(st.session_state.search_results):
        mt      = item.get("media_type") or ("movie" if item.get("release_date") else "tv")
        name    = item.get("title") or item.get("name") or "Unknown"
        year    = (item.get("release_date") or item.get("first_air_date") or "")[:4]
        rating  = round(item.get("vote_average", 0), 1)
        overview = (item.get("overview") or "")[:120]
        poster  = poster_url(item.get("poster_path"))
        is_sel  = (st.session_state.selected_media or {}).get("id") == item["id"]

        with cols[idx % 3]:
            card_class = "media-card selected" if is_sel else "media-card"
            badge_type = "badge-movie" if mt == "movie" else "badge-tv"
            st.markdown(f"""
            <div class="{card_class}">
              <img src="{poster}" alt="poster">
              <div class="card-body">
                <div class="card-title">{name}</div>
                <div class="card-meta">
                  <span class="badge {badge_type}">{mt.upper()}</span>
                  {'<span class="badge badge-score">⭐ ' + str(rating) + '</span>' if rating else ''}
                  {year}
                </div>
                <div class="card-overview">{overview}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button(f"{'✅ Selected' if is_sel else 'Select'}", key=f"sel_{item['id']}",
                         use_container_width=True):
                with st.spinner(f"Loading {name}…"):
                    details = tmdb_get_details(item["id"], mt)
                    item["_details"] = details
                    item["_imdb_id"] = get_imdb_id(details)
                    item["_mt"] = mt
                    if mt == "tv":
                        item["_seasons"] = tmdb_get_seasons(item["id"])
                st.session_state.selected_media = item
                st.session_state.extracted_streams = []
                st.session_state.extraction_log = []
                st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Step 3 – Selected media details + config
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.selected_media:
    media    = st.session_state.selected_media
    mt       = media.get("_mt", "movie")
    details  = media.get("_details", {})
    imdb_id  = media.get("_imdb_id", "")
    tmdb_id  = str(media["id"])
    title    = media.get("title") or media.get("name") or "Unknown"
    year     = (media.get("release_date") or media.get("first_air_date") or "")[:4]
    rating   = round(media.get("vote_average", 0), 1)
    genres   = ", ".join(g["name"] for g in (details.get("genres") or [])[:4])
    poster   = poster_url(media.get("poster_path"))
    tagline  = details.get("tagline", "")
    runtime  = details.get("runtime") or details.get("episode_run_time", [None])[0] if isinstance(details.get("episode_run_time"), list) else details.get("episode_run_time")

    st.markdown("---")
    st.markdown("### 🎬 Step 2 — Selected Media")

    info_col, cfg_col = st.columns([1, 2])

    with info_col:
        st.image(poster, width=200)
        st.markdown(f"**{title}** ({year})")
        if tagline:
            st.caption(f'*"{tagline}"*')
        st.markdown(f"⭐ **{rating}** / 10")
        if genres:
            st.caption(f"🎭 {genres}")
        if runtime:
            st.caption(f"⏱ {runtime} min")
        st.markdown("**IDs:**")
        st.code(f"TMDB: {tmdb_id}\nIMDB: {imdb_id or 'N/A'}", language="text")

    with cfg_col:
        st.markdown(f"""
        <div class="site-header">
          <h3>⚙️ {site} Configuration</h3>
          <p>{SITE_DESCRIPTIONS.get(site,'')}</p>
        </div>
        """, unsafe_allow_html=True)

        season_num, episode_num = "1", "1"

        # Episode picker for TV shows
        if mt == "tv":
            seasons = media.get("_seasons", [])
            valid   = [s for s in seasons if s.get("season_number", 0) > 0]
            if valid:
                s_labels = {s["season_number"]: f"Season {s['season_number']} ({s.get('episode_count',0)} eps)"
                            for s in valid}
                sel_s = st.selectbox("📅 Season", list(s_labels.keys()),
                                     format_func=lambda x: s_labels[x])
                with st.spinner("Loading episodes…"):
                    eps = tmdb_get_episodes(int(tmdb_id), sel_s)
                if eps:
                    ep_labels = {str(e["episode_number"]): f"E{e['episode_number']}: {e.get('name','')}"
                                 for e in eps}
                    sel_e = st.selectbox("📺 Episode", list(ep_labels.keys()),
                                        format_func=lambda x: ep_labels.get(x, x))
                    season_num  = str(sel_s)
                    episode_num = str(sel_e)
                else:
                    season_num  = str(sel_s)
                    episode_num = st.text_input("Episode #", "1")

        # Site-specific options
        site_config = {}

        if site == "VidSync":
            site_config["server"] = st.selectbox("Server", ["cinevault","cinedub","cinebox","cineflix","cinevip","cinecloud","cine4k"])

        elif site == "LordFlix":
            site_config["server"] = st.selectbox("Server", ["Berlin","Tokyo","Bogota","Oslo","Luna","LordFlix","Sakura","Rio","Ativa"])

        elif site == "XPrime":
            site_config["server"] = st.selectbox("Server", ["primenet","finger","primebox","king","facile","lighter","fed","eek"])

        elif site == "Videasy":
            st.info("All servers will be tried automatically until one succeeds.")

        elif site == "AnimeKai":
            site_config["anime_url"] = st.text_input("AnimeKai Watch URL",
                value=f"https://animekai.to/watch/unknown#{media['id']}",
                help="e.g. https://animekai.to/watch/naruto-9r5k")

        elif site == "YFlix/1Movies":
            site_config["watch_url"] = st.text_input("YFlix/1Movies Watch URL",
                value=f"https://yflix.to/watch/{title.lower().replace(' ','-')}.{tmdb_id[-5:]}",
                help="e.g. https://yflix.to/watch/cyberpunk-edgerunners.b4d24")

        st.markdown("---")
        run_btn = st.button("🚀 Extract Streams", use_container_width=True)

    # ── Run extraction ──
    if run_btn:
        st.session_state.extracted_streams = []
        st.session_state.extraction_log    = []
        st.session_state.running           = True

        with st.spinner("Extracting streams…"):
            streams = []
            try:
                if site == "Videasy":
                    streams = extract_videasy(tmdb_id, mt, season_num, episode_num)

                elif site == "VidSync":
                    streams = extract_vidsync(tmdb_id, imdb_id, title, mt, year,
                                              season_num, episode_num, site_config.get("server","cinevault"))

                elif site == "VidLink":
                    streams = extract_vidlink(tmdb_id, mt, season_num, episode_num)

                elif site == "Hexa/Flixer":
                    streams = extract_hexa(tmdb_id, mt, season_num, episode_num)

                elif site == "LordFlix":
                    streams = extract_lordflix(tmdb_id, imdb_id, title, mt, year,
                                               season_num, episode_num, site_config.get("server","Berlin"))

                elif site == "PrimeSrc":
                    streams = extract_primesrc(tmdb_id, imdb_id, mt, season_num, episode_num)

                elif site == "AnimeKai":
                    streams = extract_animekai(site_config.get("anime_url",""), season_num, episode_num)

                elif site == "YFlix/1Movies":
                    streams = extract_yflix(site_config.get("watch_url",""), season_num, episode_num)

                else:
                    log(f"{site} — manual URL mode. Use Python script directly.", "warn")

            except Exception as e:
                log(f"Fatal error: {e}", "err")

            st.session_state.extracted_streams = streams
            st.session_state.running           = False

        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Step 4 – Results
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.extraction_log or st.session_state.extracted_streams:
    st.markdown("---")
    st.markdown("### 📊 Step 3 — Results")

    res_col, log_col = st.columns([1, 1])

    with res_col:
        streams = st.session_state.extracted_streams
        m3u8s   = [s for s in streams if s.get("type") == "m3u8"]
        others  = [s for s in streams if s.get("type") != "m3u8"]

        st.markdown(f"**{len(streams)} stream(s) extracted** — {len(m3u8s)} M3U8, {len(others)} other")

        if m3u8s:
            st.markdown("#### 🎯 Direct M3U8 Streams")
            for s in m3u8s:
                st.markdown(f"""
                <div style="margin-bottom:10px;">
                  <div style="color:#8b949e; font-size:12px; margin-bottom:4px;">
                    📡 {s.get('server','?')} {' · ' + s.get('quality','') if s.get('quality') else ''}
                  </div>
                  <div class="stream-url">{s['url']}</div>
                </div>
                """, unsafe_allow_html=True)
                st.code(s['url'], language="text")

        if others:
            st.markdown("#### 📦 Other Results")
            for s in others:
                with st.expander(f"🔗 {s.get('server','?')} [{s.get('type','?')}]"):
                    content = s.get("url","")
                    try:
                        parsed = json.loads(content)
                        st.json(parsed)
                    except Exception:
                        st.code(content, language="text")

        if streams:
            export = json.dumps(streams, indent=2)
            st.download_button("⬇ Download JSON", export,
                               file_name="streams.json", mime="application/json",
                               use_container_width=True)
            plain = "\n".join(s["url"] for s in m3u8s)
            if plain:
                st.download_button("⬇ Download M3U8 URLs", plain,
                                   file_name="streams.m3u8", mime="text/plain",
                                   use_container_width=True)
        elif st.session_state.extraction_log:
            st.warning("No streams extracted. Check the log for details.")

    with log_col:
        st.markdown("#### 📋 Extraction Log")
        render_logs()
        if st.button("🗑 Clear Log", use_container_width=True):
            st.session_state.extraction_log = []
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style="text-align:center; color:#8b949e; font-size:12px; padding:10px 0;">
  enc-dec.app Streamlit UI · TMDB API · For educational purposes only
</div>
""", unsafe_allow_html=True)
