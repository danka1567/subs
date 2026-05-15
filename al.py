"""
advanced_streaming_app.py
=========================
Advanced Movie/TV Show Streaming Web App with TMDB Integration
Preserves all original enc-dec.app functionality
"""

import streamlit as st
import codecs
import hashlib
import json
import re
import sys
import time
import base64
from base64 import b64decode
from urllib.parse import quote, quote_plus, urlparse, parse_qs, unquote
from typing import Dict, List, Optional, Any, Tuple
import requests
from bs4 import BeautifulSoup

# ============================================================================
# ORIGINAL CODE FROM enc_dec_combined.py (PRESERVED AS IS)
# ============================================================================

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------
API      = "https://enc-dec.app/api"
DATABASE = "https://enc-dec.app/db"

BASE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36"
)

# Quality ranking for PrimeSrc/Voe picker
QUALITY_RANK = ["360p", "480p", "720p", "1080p", "2160p", "4k"]

# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def validate(data: dict, path: str):
    """Check API response status and return result, or abort with an error."""
    if data.get("status") != 200:
        print(f"\n{'-'*25} API ERROR {'-'*25}\n")
        print(f"Path:        {path}")
        print(f"Status Code: {data.get('status')}")
        print(f"Error:       {data.get('error', 'unknown')}")
        raise SystemExit(1)
    return data["result"]


def print_result(title: str, referer, data):
    """Pretty-print a decrypted result."""
    sep = "-" * 25
    print(f"\n{sep} {title} {sep}\n")
    if referer:
        print(f"Referer: {referer}\n")
    print(data)


# ---------------------------------------------------------------------------
# 1. Videasy  (player.videasy.net)  -- FULL PIPELINE
# ---------------------------------------------------------------------------

VIDEASY_SERVERS = [
    ("mb-flix",    "api"),
    ("1movies",    "api"),
    ("moviebox",   "api"),
    ("cdn",        "api"),
    ("primesrcme", "api"),
    ("primewire",  "api"),
    ("m4uhd",      "api2"),
    ("hdmovie",    "api"),
    ("lamovie",    "api"),
    ("superflix",  "api"),
    ("cuevana",    "api2"),
    ("overflix",   "api2"),
    ("visioncine", "api"),
    ("meine",      "api"),
]


def _videasy_find_streams(obj):
    """Walk a nested structure and collect all .m3u8 / /master URLs."""
    found, seen = [], set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and v.startswith("http") and v not in seen:
                    if ".m3u8" in v or "/master" in v:
                        found.append(v)
                        seen.add(v)
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(obj)
    return found


def run_videasy(
    movie_url="https://player.videasy.net/movie/280",
):
    """
    Full Videasy pipeline:
      1. Parse TMDB id from player.videasy.net URL
      2. Try each server in turn (mb-flix, 1movies, …)
      3. POST encrypted blob to /api/dec-videasy
      4. Walk result for .m3u8 / /master URLs and print them

    Servers (friendly name -> api subdomain):
        neon/mb-flix, 1movies, moviebox/cdn, primesrcme,
        primewire, m4uhd, hdmovie, lamovie, superflix,
        cuevana, overflix, visioncine, meine

    URL format: https://player.videasy.net/movie/<tmdb_id>
    """
    parsed = urlparse(movie_url)
    if parsed.netloc.lower() != "player.videasy.net":
        print("Videasy: Only player.videasy.net URLs are supported.")
        return

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2 or parts[0] != "movie":
        print("Videasy: URL format must be https://player.videasy.net/movie/<tmdb_id>")
        return

    tmdb_id = parts[1]

    headers = {
        "Accept":     "*/*",
        "Origin":     "https://cineby.sc",
        "Referer":    "https://cineby.sc/",
        "User-Agent": BASE_UA,
    }

    errors = []
    for server, api_sub in VIDEASY_SERVERS:
        api_url = (
            f"https://{api_sub}.videasy.net/{server}/sources-with-title"
            f"?mediaType=movie&tmdbId={tmdb_id}"
        )
        try:
            print(f"  [+] Trying server: {server}")
            encrypted = requests.get(api_url, headers=headers, timeout=30).text
            if not encrypted or len(encrypted.strip()) < 10:
                errors.append(f"{server}: empty response")
                continue

            response = requests.post(
                f"{API}/dec-videasy",
                json={"text": encrypted, "id": str(tmdb_id)},
                headers={"User-Agent": BASE_UA, "Accept": "application/json",
                         "Content-Type": "application/json"},
                timeout=30,
            ).json()

            if response.get("status") != 200:
                errors.append(f"{server}: {response.get('error', 'unknown')}")
                continue

            decrypted = response["result"]
            streams   = _videasy_find_streams(decrypted)

            if streams:
                print(f"\n{'='*60}")
                print("VIDEASY STREAM EXTRACTED")
                print(f"{'='*60}")
                print(f"TMDB ID : {tmdb_id}")
                print(f"Server  : {server}")
                print("\nStreams:\n")
                for s in streams:
                    print(s)
                print()
                return streams

        except Exception as exc:
            errors.append(f"{server}: {exc}")

    print("\n[Videasy] All servers failed.")
    for e in errors[-5:]:
        print(f"  {e}")
    return None


# ---------------------------------------------------------------------------
# 2. VidSync  (vidsync.xyz)
# ---------------------------------------------------------------------------
def run_vidsync(
    title="Game of Thrones",
    media_type="tv",
    year="2011",
    imdb_id="tt0944947",
    tmdb_id="1399",
    season="1",
    episode="1",
    server="cinevault",
):
    """
    Server list: https://vidsync.xyz/api/stream/serverList
    Sample: cinevault, cinedub, cinebox, cineflix, cinevip, cinecloud, cine4k

    Movie: ?type=movie&title=...&mediaId={tmdb_id}&releaseYear={year}&serverName={server}
    TV:    + &season=...&episode=...
    """
    headers = {
        "Accept": "*/*",
        "Origin": "https://vidsync.xyz",
        "Referer": "https://vidsync.xyz/",
        "User-Agent": BASE_UA,
        "X-Requested-With": "XMLHttpRequest",
    }

    enc_path = f"{API}/enc-vidsync"
    enc_data = validate(requests.get(enc_path).json(), enc_path)
    headers["X-Cf-Turnstile"] = enc_data["token"]

    enc_title = quote_plus(title)
    url = (
        f"https://vidsync.xyz/api/stream/fetch"
        f"?title={enc_title}&type={media_type}&releaseYear={year}"
        f"&mediaId={tmdb_id}&serverName={server}&season={season}&episode={episode}"
    )
    text = requests.get(url, headers=headers).text

    dec_path = f"{API}/dec-vidsync"
    decrypted = validate(
        requests.post(dec_path, json={"text": text, "id": tmdb_id}).json(), dec_path
    )
    print_result("VidSync - Decrypted Data", headers["Referer"], decrypted)
    return decrypted


# ---------------------------------------------------------------------------
# 3. VidLink  (vidlink.pro)
# ---------------------------------------------------------------------------
def run_vidlink(
    title="Cyberpunk: Edgerunners",
    media_type="tv",
    year="2022",
    imdb_id="tt12590266",
    tmdb_id="105248",
    season="1",
    episode="1",
):
    """
    Movie: https://vidlink.pro/api/b/movie/{encrypted_id}
    TV:    https://vidlink.pro/api/b/tv/{encrypted_id}/{season}/{episode}
    """
    headers = {
        "User-Agent": BASE_UA,
        "Origin":     "https://vidlink.pro",
        "Referer":    "https://vidlink.pro/",
    }

    enc_path  = f"{API}/enc-vidlink?text={tmdb_id}"
    encrypted = validate(requests.get(enc_path).json(), enc_path)

    url  = f"https://vidlink.pro/api/b/{media_type}/{encrypted}/{season}/{episode}"
    data = requests.get(url, headers=headers).json()
    print_result("VidLink - Data", headers["Referer"], json.dumps(data, indent=2))
    return data


# ---------------------------------------------------------------------------
# 4. VidFast  (vidfast.pro)
# ---------------------------------------------------------------------------
def run_vidfast(
    title="Game of Thrones",
    media_type="tv",
    year="2011",
    imdb_id="tt0944947",
    tmdb_id="1399",
    season="1",
    episode="1",
    version="1",
):
    """
    Movie: https://vidfast.pro/movie/{IMDB_or_TMDB}
    TV:    https://vidfast.pro/tv/{IMDB_or_TMDB}/{season}/{episode}/
    """
    headers = {
        "User-Agent":        BASE_UA,
        "Referer":           "https://vidfast.pro/",
        "X-Requested-With":  "XMLHttpRequest",
    }

    base_url = f"https://vidfast.pro/{media_type}/{tmdb_id}/{season}/{episode}/"
    response = requests.get(base_url).text

    match = re.search(r'\\"en\\":\\"(.*?)\\"', response)
    if not match:
        print("VidFast: Could not extract encoded text from page.")
        return None
    text = match.group(1)

    enc_path = f"{API}/enc-vidfast?text={text}&version={version}"
    parts    = validate(requests.get(enc_path).json(), enc_path)
    headers["X-CSRF-Token"] = parts["token"]

    servers_encrypted = requests.post(parts["servers"], headers=headers).text
    dec_path = f"{API}/dec-vidfast"
    servers_decrypted = validate(
        requests.post(dec_path, json={"text": servers_encrypted, "version": version}).json(),
        dec_path,
    )

    server       = servers_decrypted[0]
    stream_url   = f"{parts['stream']}/{server['data']}"
    stream_enc   = requests.post(stream_url, headers=headers).text
    stream_dec   = validate(
        requests.post(dec_path, json={"text": stream_enc, "version": version}).json(),
        dec_path,
    )
    print_result("VidFast - Decrypted Stream", headers["Referer"], stream_dec)
    return stream_dec


# ---------------------------------------------------------------------------
# 5. Hexa / Flixer  (hexa.su / flixer.su)
# ---------------------------------------------------------------------------
def run_hexa(
    title="Cyberpunk: Edgerunners",
    media_type="tv",
    year="2022",
    imdb_id="tt12590266",
    tmdb_id="105248",
    season="1",
    episode="1",
):
    """
    Also works with https://flixer.su/
    Movie: https://theemoviedb.hexa.su/api/tmdb/movie/{tmdb_id}/images
    TV:    https://theemoviedb.hexa.su/api/tmdb/tv/{tmdb_id}/season/{s}/episode/{e}/images
    """
    try:
        from Crypto.Random import get_random_bytes
    except ImportError:
        sys.exit("Missing dependency: pip install pycryptodome")

    headers = {
        "User-Agent":        BASE_UA,
        "Referer":           "https://hexa.su/",
        "Accept":            "text/plain",
        "X-Fingerprint-Lite":"e9136c41504646444",
    }

    key = get_random_bytes(32).hex()
    headers["X-Api-Key"] = key

    enc_path = f"{API}/enc-hexa"
    token    = validate(requests.get(enc_path).json(), enc_path)["token"]
    headers["X-Cap-Token"] = token

    if media_type == "movie":
        url = f"https://theemoviedb.hexa.su/api/tmdb/movie/{tmdb_id}/images"
    else:
        url = (
            f"https://theemoviedb.hexa.su/api/tmdb/tv/{tmdb_id}"
            f"/season/{season}/episode/{episode}/images"
        )

    encrypted = requests.get(url, headers=headers).text
    dec_path  = f"{API}/dec-hexa"
    decrypted = validate(
        requests.post(dec_path, json={"text": encrypted, "key": key}).json(), dec_path
    )
    print_result("Hexa - Decrypted Data", headers["Referer"], decrypted)
    return decrypted


# ---------------------------------------------------------------------------
# 6. LordFlix  (lordflix.org / network.hasta-la-vista.site)
# ---------------------------------------------------------------------------
def run_lordflix(
    title="Game of Thrones",
    media_type="series",
    year="2011",
    imdb_id="tt0944947",
    tmdb_id="1399",
    season="1",
    episode="1",
    server="Berlin",
):
    """
    Server list: https://network.hasta-la-vista.site/servers
    Sample: Berlin, Tokyo, Bogota, Oslo, Luna, LordFlix, Sakura, Rio, Ativa

    Movie:  ?title=...&type=movie&year=...&imdb=...&tmdb=...&server=...
    Series: ?title=...&type=series&...&server=...&season=...&episode=...
    """
    headers = {
        "Accept":     "*/*",
        "Origin":     "https://lordflix.org",
        "Referer":    "https://lordflix.org/",
        "User-Agent": BASE_UA,
    }

    url = (
        f"https://network.hasta-la-vista.site/"
        f"?title={quote(title)}&type={media_type}&year={year}"
        f"&imdb={imdb_id}&tmdb={tmdb_id}&server={server}"
        f"&season={season}&episode={episode}"
    )

    enc_path  = f"{API}/enc-lordflix?url={quote(url)}"
    data      = validate(requests.get(enc_path).json(), enc_path)
    encrypted = requests.get(data["url"], headers=headers).text

    dec_path  = f"{API}/dec-lordflix"
    decrypted = validate(
        requests.post(dec_path, json={"text": encrypted, "sign": data["sign"]}).json(),
        dec_path,
    )
    print_result("LordFlix - Decrypted Data", headers["Referer"], decrypted)
    return decrypted


# ---------------------------------------------------------------------------
# 7. Abyss  (playhydrax.com)
# ---------------------------------------------------------------------------
def run_abyss(content_id="K8R6OOjS7"):
    """
    content_id -- the 'v' query parameter on playhydrax.com
    """
    headers = {
        "User-Agent": BASE_UA,
        "Origin":     "https://playhydrax.com",
        "Referer":    "https://playhydrax.com/",
    }

    url      = f"https://playhydrax.com/?v={content_id}"
    response = requests.get(url, headers=headers).text
    match    = re.search(r'const\s+datas\s*=\s*"([^"]*)"', response)
    if not match:
        print("Abyss: Could not find 'datas' variable in page.")
        return None
    encrypted = match.group(1)

    dec_path  = f"{API}/dec-abyss"
    decrypted = validate(
        requests.post(dec_path, json={"text": encrypted}).json(), dec_path
    )
    print_result("Abyss - Decrypted Data", headers["Referer"], decrypted)
    return decrypted


# ---------------------------------------------------------------------------
# 8. KissKH  (kisskh.do)
# ---------------------------------------------------------------------------
def run_kisskh(content_id="192143"):
    """
    content_id -- episode ID on kisskh.do
    """
    headers = {
        "User-Agent": BASE_UA,
        "Accept":     "application/json",
    }

    enc_vid_path = f"{API}/enc-kisskh?text={content_id}&type=vid"
    vid_key      = validate(requests.get(enc_vid_path).json(), enc_vid_path)
    video_url    = (
        f"https://kisskh.do/api/DramaList/Episode/{content_id}.png"
        f"?err=false&ts=&time=&kkey={vid_key}"
    )
    video_response = requests.get(video_url, headers=headers).json()

    enc_sub_path   = f"{API}/enc-kisskh?text={content_id}&type=sub"
    sub_key        = validate(requests.get(enc_sub_path).json(), enc_sub_path)
    sub_url        = f"https://kisskh.do/api/Sub/{content_id}?kkey={sub_key}"
    subtitle_resp  = requests.get(sub_url, headers=headers).json()

    subtitle_src   = subtitle_resp[0]["src"]
    subtitle_dec   = requests.get(f"{API}/dec-kisskh?url={quote(subtitle_src)}").text

    print(f"\n{'-'*25} KissKH Sample Response {'-'*25}\n")
    print("Video:\n",     json.dumps(video_response, indent=2))
    print("\nSubtitles:\n", json.dumps(subtitle_resp, indent=2))
    print("\nDecrypted subtitle (first 200 chars):\n", subtitle_dec[:200])
    return {"video": video_response, "subtitles": subtitle_resp, "subtitle_dec": subtitle_dec}


# ---------------------------------------------------------------------------
# 9. OneTouchTV  (api3.devcorp.me)
# ---------------------------------------------------------------------------
def run_onetouchtv(
    content_url="https://api3.devcorp.me/web/vod/150294-ghost-train-2024/episode/1",
):
    """
    content_url -- full API URL for the specific episode.
    """
    headers   = {"User-Agent": BASE_UA}
    encrypted = requests.get(content_url, headers=headers).text

    dec_path  = f"{API}/dec-onetouchtv"
    decrypted = validate(
        requests.post(dec_path, json={"text": encrypted}).json(), dec_path
    )
    print_result("OneTouchTV - Decrypted Data", None, decrypted)
    return decrypted


# ---------------------------------------------------------------------------
# 10. PrimeSrc  (primesrc.me)  -- FULL PIPELINE (all servers + Voe m3u8)
# ---------------------------------------------------------------------------

def _primesrc_parse_url(url: str) -> dict:
    parsed = urlparse(url)
    qs     = parse_qs(parsed.query)
    path   = parsed.path.lower()

    def first(k):
        return qs.get(k, [None])[0]

    if "/movie" in path:
        media_type = "movie"
    elif "/tv" in path or "/series" in path or "/anime" in path:
        media_type = "tv"
    else:
        media_type = first("type") or "movie"

    return {
        "type":    media_type,
        "imdb_id": first("imdb"),
        "tmdb_id": first("tmdb"),
        "season":  first("season"),
        "episode": first("episode"),
    }


def _primesrc_fetch_servers(params: dict) -> list:
    imdb_id = params.get("imdb_id")
    tmdb_id = params.get("tmdb_id")
    media   = params["type"]
    season  = params.get("season")
    episode = params.get("episode")

    if imdb_id:
        id_param = f"imdb={imdb_id}"
    elif tmdb_id:
        id_param = f"tmdb={tmdb_id}"
    else:
        print("  [!] No IMDB or TMDB id found in URL.")
        return []

    if media == "movie":
        api_url = f"https://primesrc.me/api/v1/s?{id_param}&type=movie"
    else:
        if not season or not episode:
            print("  [!] TV URL needs &season=N&episode=N in the URL.")
            return []
        api_url = (
            f"https://primesrc.me/api/v1/s?{id_param}"
            f"&season={season}&episode={episode}&type=tv"
        )

    resp    = requests.get(api_url, headers={"User-Agent": BASE_UA}, timeout=20).json()
    servers = resp.get("servers", [])
    if not servers:
        print("  [!] No servers returned from PrimeSrc.")
    return servers


def _primesrc_resolve_key(key: str):
    embed_api = f"https://primesrc.me/api/v1/l?key={key}"
    solve_url = f"{API}/solve-primesrc?url={quote(embed_api)}"
    try:
        data = requests.get(solve_url, headers={"User-Agent": BASE_UA}, timeout=15).json()
        if data.get("status") != 200:
            return None
        return data["result"]
    except Exception:
        return None


def _primesrc_quality_score(q: str) -> int:
    q = (q or "").lower()
    m = re.search(r'(\d{3,4})p?', q)
    if m:
        return int(m.group(1))
    for i, label in enumerate(QUALITY_RANK):
        if label in q:
            return (i + 1) * 100
    return 0


def _voe_clean_symbols(s: str) -> str:
    for p in ["@$", "^^", "~@", "%?", "*~", "!!", "#&"]:
        s = re.sub(re.escape(p), "_", s)
    return s


def _voe_shift_back(s: str, n: int) -> str:
    return ''.join(chr(ord(c) - n) for c in s)


def _decrypt_voe(voe_embed_url: str):
    """Given a voe.sx embed URL, return the direct .m3u8 HLS stream URL."""
    domain  = '{uri.scheme}://{uri.netloc}/'.format(uri=urlparse(voe_embed_url))
    session = requests.Session()
    session.headers.update({
        "Referer":                   domain,
        "User-Agent":                BASE_UA,
        "Accept":                    "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language":           "en-US,en;q=0.5",
        "Accept-Encoding":           "gzip, deflate, br",
        "Connection":                "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })

    try:
        html = session.get(voe_embed_url, timeout=20).text

        if 'Redirecting...' in html:
            redirect_url = re.search(r"href\s*=\s*'(.*?)';", html).group(1)
            html = session.get(redirect_url, timeout=20).text

        soup       = BeautifulSoup(html, 'html.parser')
        script_tag = soup.find('script', attrs={'type': 'application/json'})
        if not script_tag:
            print("  [Voe] Could not find JSON script tag.")
            return None

        obfuscated = script_tag.string
        encoded    = re.search(r'\["(.*?)"\]', obfuscated).group(1)

        decoded = codecs.decode(encoded, 'rot_13')
        decoded = _voe_clean_symbols(decoded)
        decoded = decoded.replace("_", "")
        decoded = b64decode(decoded).decode()
        decoded = _voe_shift_back(decoded, 3)
        decoded = decoded[::-1]
        decoded = b64decode(decoded).decode()
        data    = json.loads(decoded)
        return data.get('source')

    except Exception as e:
        print(f"  [Voe] Decryption error: {e}")
        return None


def run_primesrc(
    embed_url="https://primesrc.me/embed/movie?tmdb=9470",
):
    """
    Full PrimeSrc pipeline:
      1. Parse media type + id from embed URL
      2. Fetch all available servers
      3. Resolve every server key -> embed link
      4. Pick best Voe link by quality
      5. Decrypt Voe embed -> .m3u8 and print it

    URL examples:
      Movie by TMDB : https://primesrc.me/embed/movie?tmdb=296
      Movie by IMDB : https://primesrc.me/embed/movie?imdb=tt0468569
      TV by TMDB    : https://primesrc.me/embed/tv?tmdb=1399&season=1&episode=1
      TV by IMDB    : https://primesrc.me/embed/tv?imdb=tt0944947&season=1&episode=1
    """
    sep = "=" * 70
    print(f"\n{sep}")
    print("  PrimeSrc + Voe Extractor")
    print(f"{sep}")
    print(f"  URL  : {embed_url}")

    params  = _primesrc_parse_url(embed_url)
    print(f"  Type : {params['type'].upper()}\n")

    servers = _primesrc_fetch_servers(params)
    if not servers:
        return None

    print(f"  Found: {len(servers)} server(s)\n")
    total   = len(servers)
    results = []

    for i, srv in enumerate(servers, 1):
        name    = str(srv.get("name")    or "unknown")
        key     = srv.get("key", "")
        quality = str(srv.get("quality") or "")
        lang    = str(srv.get("lang")    or "—")
        print(f"  [{i:>2}/{total}] {name:<18} ... ", end="", flush=True)
        link = _primesrc_resolve_key(key)
        print("OK" if link else "FAIL")
        results.append({"name": name, "quality": quality, "lang": lang, "link": link})

    # Print table
    dash = "-" * 70
    print(f"\n{dash}")
    print(f"  {'#':<4} {'Host':<20} {'Quality':<10} {'Lang':<6}  Link")
    print(dash)
    for idx, item in enumerate(results, 1):
        link = item["link"] or "FAILED"
        q    = item["quality"] or "—"
        print(f"  {idx:<4} {item['name']:<20} {q:<10} {item['lang']:<6}  {link}")
    print(dash)
    ok   = sum(1 for r in results if r["link"])
    fail = len(results) - ok
    print(f"  Total: {len(results)}   OK: {ok}   FAIL: {fail}")
    print(dash + "\n")

    # Pick best Voe link
    voe_entries = [r for r in results if r.get("link") and "voe.sx" in r["link"]]
    if not voe_entries:
        print("  [!] No Voe links found in results.")
        return None

    voe_entries.sort(key=lambda r: _primesrc_quality_score(r["quality"]), reverse=True)
    best = voe_entries[0]

    print(f"  [Voe] {len(voe_entries)} link(s) found — picked best:")
    for e in voe_entries:
        marker = "  >>>" if e is best else "     "
        q = e["quality"] or "unknown quality"
        print(f"  {marker} [{q}]  {e['link']}")

    print("\n  Decrypting Voe embed ...")
    m3u8_url = _decrypt_voe(best["link"])

    print("\n" + "#" * 50)
    if m3u8_url:
        print(f"  Captured URL:\n  \033[92m{m3u8_url}\033[0m")
    else:
        print("  [!] Failed to extract stream URL from Voe.")
    print("#" * 50 + "\n")
    
    return m3u8_url


# ---------------------------------------------------------------------------
# 11. Reanime  (reanime.to)
# ---------------------------------------------------------------------------
def run_reanime(
    title="Cyberpunk Edgerunners",
    anilist_id="120377",
    episode="1",
):
    """
    Requires json5: pip install json5
    Multiple server options may be available with different audio languages.
    """
    try:
        import json5 as j5
    except ImportError:
        sys.exit("Missing dependency: pip install json5")
    from urllib.parse import urlparse as _up

    headers = {
        "User-Agent": BASE_UA,
        "Referer":    "https://reanime.to/",
    }

    response = requests.get(
        f"https://reanime.to/api/flix/{anilist_id}/{episode}", headers=headers
    ).json()

    servers    = response["servers"]
    server_url = servers[0]["dataLink"]
    domain     = _up(server_url).netloc

    page  = requests.get(server_url, headers=headers).text
    match = re.search(r'type:\s*"data",\s*data:\s*(\{.*?\})\s*,\s*uses:', page, re.S)
    if not match:
        print("Reanime: Could not extract embedded data from page.")
        return None
    data      = j5.loads(match.group(1))
    subtitles = data.pop("subtitles", None)

    resolve_path = f"{API}/dec-reanime?type=resolve"
    resolved     = validate(
        requests.post(resolve_path, json={"data": data}).json(), resolve_path
    )

    referer        = f"https://{domain}/"
    stream_headers = {**headers, "Referer": referer}
    token_response = requests.get(
        f"https://{domain}/api/m3u8/{resolved['token']}", headers=stream_headers
    ).json()

    decrypt_path = f"{API}/dec-reanime?type=decrypt"
    decrypted    = validate(
        requests.post(
            decrypt_path,
            json={"data": {"state": resolved["state"], "token_response": token_response}},
        ).json(),
        decrypt_path,
    )
    print_result("Reanime - Decrypted Data", referer, decrypted)
    if subtitles:
        print(f"\nSubtitles available: {subtitles}")
    return decrypted


# ---------------------------------------------------------------------------
# 12. XPrime  (mznxiwqjdiq00239q.space)
# ---------------------------------------------------------------------------
def _xprime_solve_altcha():
    """Solve XPrime's Proof-of-Work Altcha challenge."""
    url       = "https://mznxiwqjdiq00239q.space/altcha/challenge"
    challenge = requests.get(url).json()

    algorithm = challenge["algorithm"]
    ch        = challenge["challenge"]
    salt      = challenge["salt"]
    maxnumber = challenge["maxnumber"]

    threshold = hex(((1 << 256) - 1) // (maxnumber + 1))[2:].rjust(64, "0")
    start     = time.time()
    number    = -1
    for n in range(maxnumber * 10 + 1):
        h = hashlib.sha256(f"{algorithm}:{ch}:{salt}:{n}".encode()).hexdigest()
        if h <= threshold:
            number = n
            break

    if number < 0:
        raise RuntimeError("XPrime: Altcha PoW solving failed.")

    took    = int((time.time() - start) * 1000)
    payload = {
        "algorithm": algorithm,
        "challenge": ch,
        "maxnumber": maxnumber,
        "number":    number,
        "salt":      salt,
        "signature": challenge["signature"],
        "took":      took,
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def run_xprime(
    title="Cyberpunk: Edgerunners",
    media_type="tv",
    year="2022",
    imdb_id="tt12590266",
    tmdb_id="105248",
    season="1",
    episode="1",
    server="primebox",
):
    """
    Server list: https://mznxiwqjdiq00239q.space/servers
    Sample: primenet, finger, primebox, king, facile, lighter, fed, eek

    Movie: ?name={title}&year={year}&id={tmdb_id}&imdb={imdb_id}
    TV:    + &season={s}&episode={e}
    """
    headers = {
        "User-Agent": BASE_UA,
        "Referer":    "https://mznxiwqjdiq00239q.space/",
    }

    print("XPrime: Solving Altcha PoW challenge (may take a moment)...")
    altcha = _xprime_solve_altcha()

    url = (
        f"https://mznxiwqjdiq00239q.space/{server}"
        f"?name={quote(title)}&year={year}&id={tmdb_id}&imdb={imdb_id}"
        f"&season={season}&episode={episode}&altcha={altcha}"
    )
    encrypted = requests.get(url, headers=headers).text

    dec_path  = f"{API}/dec-xprime"
    decrypted = validate(
        requests.post(dec_path, json={"text": encrypted}).json(), dec_path
    )
    print_result("XPrime - Decrypted Data", headers["Referer"], decrypted)
    return decrypted


# ---------------------------------------------------------------------------
# 13. MegaUp  (AnimeKai embed decryptor)
# ---------------------------------------------------------------------------
def run_megaup(
    view_url=(
        "https://animekai.to/ajax/links/view"
        "?id=dIG98qei6A"
        "&_=xQm9tJfLwGhz_0Eq8S_YAHYkwp-qSvLfm50W5X1nyd2NnAcpzTUWyAgck4I"
    ),
):
    """
    Works with any AnimeKai /ajax/links/view URL regardless of domain.
    Flow: dec-kai -> extract embed URL -> /media/ endpoint -> dec-mega -> HLS streams.
    """
    headers = {
        "User-Agent": BASE_UA,
        "Accept":     "application/json",
    }

    enc     = requests.get(view_url, headers=headers).json()["result"]
    dec     = requests.post(f"{API}/dec-kai", json={"text": enc}).json()["result"]
    embed   = dec["url"]
    referer = embed.split("/e/")[0] + "/"
    headers["Referer"] = referer

    media     = embed.replace("/e/", "/media/")
    encrypted = requests.get(media, headers=headers).json()["result"]

    dec_path  = f"{API}/dec-mega"
    decrypted = validate(
        requests.post(dec_path, json={"text": encrypted, "agent": BASE_UA}).json(),
        dec_path,
    )
    print_result("MegaUp - Decrypted Data", referer, decrypted)
    return decrypted


# ---------------------------------------------------------------------------
# 14. RapidShare  (YFlix / 1Movies embed decryptor)
# ---------------------------------------------------------------------------
def run_rapidshare(
    view_url=(
        "https://yflix.to/ajax/links/view"
        "?id=cYe--KWj5g"
        "&_=VU7EzW-r3IptzPzkwFi43K6fMXG1W-twXRnEjr7jYvY2mi6oJTqlmYTf"
    ),
):
    """
    Works with any YFlix / 1Movies /ajax/links/view URL regardless of domain.
    Flow: dec-movies-flix -> extract embed URL -> /media/ endpoint -> dec-rapid -> HLS streams.
    """
    headers = {
        "User-Agent": BASE_UA,
        "Accept":     "application/json",
    }

    enc     = requests.get(view_url, headers=headers).json()["result"]
    dec     = requests.post(f"{API}/dec-movies-flix", json={"text": enc}).json()["result"]
    embed   = dec["url"]
    referer = embed.split("/e/")[0] + "/"
    headers["Referer"] = referer

    media     = embed.replace("/e/", "/media/")
    encrypted = requests.get(media, headers=headers).json()["result"]

    dec_path  = f"{API}/dec-rapid"
    decrypted = validate(
        requests.post(dec_path, json={"text": encrypted, "agent": BASE_UA}).json(),
        dec_path,
    )
    print_result("RapidShare - Decrypted Data", referer, decrypted)
    return decrypted


# ---------------------------------------------------------------------------
# 15. AnimeKai  (animekai.to)  -- FULL PIPELINE (all sub/softsub/dub m3u8)
# ---------------------------------------------------------------------------

def _kai_enc(text: str) -> str:
    return requests.get(f"{API}/enc-kai?text={text}").json()["result"]


def _kai_dec(text: str) -> dict:
    return requests.post(f"{API}/dec-kai", json={"text": text}).json()["result"]


def _kai_dec_mega(text: str, user_agent: str) -> dict:
    resp = requests.post(f"{API}/dec-mega", json={"text": text, "agent": user_agent}).json()
    if resp.get("status") != 200:
        raise Exception(f"dec-mega error: {resp.get('error', 'unknown')}")
    return resp["result"]


def _kai_parse_html(html: str):
    return requests.post(f"{API}/parse-html", json={"text": html}).json()["result"]


def _kai_get_episodes(content_id: str, base_headers: dict) -> dict:
    enc_id = _kai_enc(content_id)
    resp   = requests.get(
        f"https://animekai.to/ajax/episodes/list?ani_id={content_id}&_={enc_id}",
        headers=base_headers,
    ).json()
    return _kai_parse_html(resp["result"])


def _kai_get_servers(token: str, base_headers: dict) -> dict:
    enc_token = _kai_enc(token)
    resp      = requests.get(
        f"https://animekai.to/ajax/links/list?token={token}&_={enc_token}",
        headers=base_headers,
    ).json()
    return _kai_parse_html(resp["result"])


def _kai_get_m3u8_from_lid(lid: str, base_headers: dict):
    enc_lid    = _kai_enc(lid)
    embed_resp = requests.get(
        f"https://animekai.to/ajax/links/view?id={lid}&_={enc_lid}",
        headers=base_headers,
    ).json()
    decrypted  = _kai_dec(embed_resp["result"])
    embed_url  = decrypted["url"]
    referer    = embed_url.split("/e/")[0] + "/"
    h          = {**base_headers, "Referer": referer}
    media_url  = embed_url.replace("/e/", "/media/")
    encrypted  = requests.get(media_url, headers=h).json()["result"]
    dec_result = _kai_dec_mega(encrypted, BASE_UA)
    m3u8       = dec_result.get("url") or dec_result.get("sources", [{}])[0].get("file")
    return m3u8, referer


def run_animekai(
    anime_url="https://animekai.to/watch/naruto-9r5k#ep=1",
    season="1",
    episode="1",
):
    """
    Full AnimeKai pipeline:
      1. Extract content_id from page HTML
      2. Fetch episode list -> pick season/episode -> token
      3. Fetch servers list (sub / softsub / dub)
      4. For every server in every type, resolve lid -> embed -> .m3u8
      5. Print all results

    URL format : https://animekai.to/watch/<anime-slug>
    sub_type   : sub | softsub | dub
    episode    : "1", "2", …
    """
    KAI_HEADERS = {
        "User-Agent": BASE_UA,
        "Referer":    "https://animekai.to/",
        "Accept":     "application/json",
    }

    print(f"\nExtracting M3U8 URLs for: {anime_url}")
    print(f"Season {season}, Episode {episode}\n" + "─" * 50)

    html  = requests.get(anime_url, headers={**KAI_HEADERS, "Accept": "text/html"}).text
    match = re.search(r'<div[^>]*id="anime-rating"[^>]*data-id="([^"]+)"', html)
    if not match:
        print("[!] Could not find content ID in page HTML.")
        return None
    content_id = match.group(1)
    print(f"[+] Content ID: {content_id}")

    episodes = _kai_get_episodes(content_id, KAI_HEADERS)
    if season not in episodes or episode not in episodes[season]:
        available = {s: list(eps.keys()) for s, eps in episodes.items()}
        print(f"[!] Season {season} / Episode {episode} not found. Available: {available}")
        return None

    token = episodes[season][episode]["token"]
    title = episodes[season][episode].get("title", f"S{season}E{episode}")
    print(f"[+] Episode: {title} | Token: {token}")

    servers = _kai_get_servers(token, KAI_HEADERS)
    print(f"[+] Available types/servers: { {k: list(v.keys()) for k, v in servers.items()} }")

    results = {}
    for type_key, server_dict in servers.items():
        results[type_key] = {}
        for server_num, server_info in server_dict.items():
            lid = server_info.get("lid")
            if not lid:
                print(f"  [-] {type_key}/server{server_num}: No lid, skipping")
                continue
            try:
                m3u8, referer = _kai_get_m3u8_from_lid(lid, KAI_HEADERS)
                results[type_key][server_num] = {"m3u8": m3u8, "referer": referer}
                print(f"  [✓] {type_key}/server{server_num}: {m3u8}")
            except Exception as exc:
                print(f"  [✗] {type_key}/server{server_num}: Error - {exc}")
                results[type_key][server_num] = {"error": str(exc)}

    print("\n" + "═" * 50)
    print("RESULTS")
    print("═" * 50)
    for type_key, srv_map in results.items():
        for server_num, data in srv_map.items():
            if "m3u8" in data:
                print(f"[{type_key.upper()}] Server {server_num}")
                print(f"  M3U8   : {data['m3u8']}")
                print(f"  Referer: {data['referer']}")
            else:
                print(f"[{type_key.upper()}] Server {server_num} — ERROR: {data.get('error')}")
    
    return results


# ---------------------------------------------------------------------------
# 16. YFlix / 1Movies  (yflix.to / 1movies.bz)  -- FULL PIPELINE
# ---------------------------------------------------------------------------

YFLIX_SUPPORTED_HOSTS = {
    "yflix.to":          "https://yflix.to",
    "www.yflix.to":      "https://yflix.to",
    "1movies.bz":        "https://1movies.bz",
    "www.1movies.bz":    "https://1movies.bz",
    "solarmovie.fi":     "https://solarmovie.fi",
    "www.solarmovie.fi": "https://solarmovie.fi",
}


def _flix_headers(referer, ajax=True):
    h = {
        "User-Agent": BASE_UA,
        "Referer":    referer,
        "Accept":     "application/json, text/plain, */*" if ajax
                      else "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    if ajax:
        h["X-Requested-With"] = "XMLHttpRequest"
    return h


def _flix_enc(text: str) -> str:
    return requests.get(f"{API}/enc-movies-flix?text={text}",
                        headers={"User-Agent": BASE_UA}).json()["result"]


def _flix_dec(text: str) -> dict:
    return requests.post(f"{API}/dec-movies-flix", json={"text": text}).json()["result"]


def _flix_parse_html(html: str):
    return requests.post(f"{API}/parse-html", json={"text": html}).json()["result"]


def _flix_get_content_id(watch_url: str):
    host = urlparse(watch_url).netloc.lower()
    if host not in YFLIX_SUPPORTED_HOSTS:
        raise ValueError(f"Unsupported host: {host}. Supported: {list(YFLIX_SUPPORTED_HOSTS)}")
    base = YFLIX_SUPPORTED_HOSTS[host]
    html = requests.get(watch_url, headers=_flix_headers(base + "/", ajax=False),
                        timeout=30).text
    patterns = [
        r'itemprop="aggregateRating"[^>]*data-id="([^"]+)"',
        r'data-id="([^"]+)"[^>]*itemprop="aggregateRating"',
        r'id="movie-rating"[^>]*data-id="([^"]+)"',
        r'data-id="([^"]+)"[^>]*id="movie-rating"',
        r'class="[^"]*user-bookmark[^"]*"[^>]*data-id="([^"]+)"[^>]*data-live="true"',
        r'data-id="([^"]+)"[^>]*data-live="true"',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return base, m.group(1)
    raise ValueError("Could not find content_id (data-id) in page HTML")


def _flix_unwrap_iframe(url: str, base: str) -> str:
    seen = set()
    cur  = url
    while cur and "/iframe/" in cur and cur not in seen:
        seen.add(cur)
        r = requests.get(cur, headers=_flix_headers(base + "/", ajax=False), timeout=30)
        m = re.search(r'<iframe[^>]+src="([^"]+)"', r.text, re.IGNORECASE)
        if not m:
            break
        cur = m.group(1)
    return cur


def _flix_resolve_embed(embed_url: str):
    """
    Fetch /media/<id>, try dec-rapid then dec-mega, return parsed sources.
    """
    if "/e/" not in embed_url:
        raise ValueError(f"Embed URL does not contain '/e/': {embed_url}")

    referer   = embed_url.split("/e/")[0] + "/"
    media_url = embed_url.replace("/e/", "/media/")
    headers   = {"User-Agent": BASE_UA, "Referer": referer,
                 "Accept": "application/json, text/plain, */*"}

    raw       = requests.get(media_url, headers=headers, timeout=30).json()
    encrypted = raw.get("result")
    if not encrypted:
        raise ValueError(f"No 'result' in media response: {raw}")

    host  = urlparse(embed_url).netloc.lower()
    order = ["dec-mega", "dec-rapid"] if "mega" in host else ["dec-rapid", "dec-mega"]

    last_err = None
    for path in order:
        try:
            data   = requests.post(f"{API}/{path}",
                                   json={"text": encrypted, "agent": BASE_UA}).json()
            if data.get("status") != 200:
                last_err = data.get("error")
                continue
            return {"decryptor": path, "referer": referer,
                    "media_url": media_url, "sources": data["result"]}
        except Exception as exc:
            last_err = exc
    raise ValueError(f"All decryptors failed for {host}: {last_err}")


def _flix_find_m3u8s(sources_blob):
    found = []
    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and (".m3u8" in v or "/master" in v):
                    found.append({"key": k, "url": v})
                walk(v)
        elif isinstance(node, list):
            for it in node:
                walk(it)
    walk(sources_blob)
    return found


def run_yflix(
    watch_url="https://yflix.to/watch/cyberpunk-edgerunners.b4d24",
    season="1",
    episode="1",
):
    """
    Full YFlix / 1Movies pipeline:
      1. Scrape content_id from watch page
      2. Fetch episode list -> pick season/episode -> eid
      3. Fetch server list -> resolve ALL servers
      4. For each server: get embed URL -> resolve to .m3u8 via dec-rapid / dec-mega
      5. Print every extracted stream URL

    Supported hosts: yflix.to, 1movies.bz, solarmovie.fi
    URL format: https://yflix.to/watch/<movie-or-show-slug>
    For TV shows: add --season / --episode (defaults: 1/1)
    """
    try:
        base, content_id = _flix_get_content_id(watch_url)
    except ValueError as exc:
        print(f"[!] {exc}")
        return None

    print(f"\n{'='*70}")
    print("  YFlix / 1Movies Extractor")
    print(f"{'='*70}")
    print(f"  URL        : {watch_url}")
    print(f"  Content ID : {content_id}")

    # Episodes
    enc_id       = _flix_enc(content_id)
    episodes_raw = requests.get(
        f"{base}/ajax/episodes/list?id={content_id}&_={enc_id}",
        headers=_flix_headers(base + "/"),
    ).json()
    episodes = _flix_parse_html(episodes_raw["result"])

    if season not in episodes:
        print(f"[!] Season {season!r} not found. Available: {list(episodes.keys())}")
        return None
    if episode not in episodes[season]:
        print(f"[!] Episode {episode!r} not in season {season!r}. "
              f"Available: {list(episodes[season].keys())}")
        return None

    eid   = episodes[season][episode]["eid"]
    title = episodes[season][episode].get("title", f"S{season}E{episode}")
    print(f"  Episode    : {title}  (eid={eid})")

    # Servers
    enc_eid      = _flix_enc(eid)
    servers_raw  = requests.get(
        f"{base}/ajax/links/list?eid={eid}&_={enc_eid}",
        headers=_flix_headers(base + "/"),
    ).json()
    servers = _flix_parse_html(servers_raw["result"])
    total   = sum(len(v) for v in servers.values())
    print(f"  Servers    : {total} found\n")

    all_results = []
    for stype, smap in servers.items():
        for sidx, sinfo in smap.items():
            lid  = sinfo["lid"]
            label = f"{stype}/{sidx}"

            print(f"  [{label}] {sinfo.get('title', '')}  lid={lid}")

            # Get embed URL
            enc_lid    = _flix_enc(lid)
            embed_resp = requests.get(
                f"{base}/ajax/links/view?id={lid}&_={enc_lid}",
                headers=_flix_headers(base + "/"),
            ).json()

            try:
                dec_result = _flix_dec(embed_resp["result"])
                embed_url  = dec_result.get("url") if isinstance(dec_result, dict) else dec_result
                if embed_url and "/iframe/" in embed_url:
                    embed_url = _flix_unwrap_iframe(embed_url, base)
                print(f"    embed: {embed_url}")

                sources = _flix_resolve_embed(embed_url)
                m3u8s   = _flix_find_m3u8s(sources["sources"])
                for m in m3u8s:
                    print(f"    m3u8:  {m['url']}")
                all_results.append({
                    "type": stype, "index": sidx, "embed": embed_url,
                    "m3u8s": m3u8s, "decryptor": sources["decryptor"],
                })

            except Exception as exc:
                print(f"    error: {exc}")
                all_results.append({"type": stype, "index": sidx, "error": str(exc)})

    # Summary
    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    ok   = sum(1 for r in all_results if "m3u8s" in r and r["m3u8s"])
    fail = len(all_results) - ok
    print(f"  Total: {len(all_results)}   OK: {ok}   FAIL: {fail}")
    for r in all_results:
        if "m3u8s" in r and r["m3u8s"]:
            for m in r["m3u8s"]:
                print(f"  [{r['type']}/{r['index']}]  {m['url']}")
    print(f"{'='*70}\n")
    
    return all_results


# ============================================================================
# STREAMLIT UI (WRAPPER AROUND ORIGINAL FUNCTIONS)
# ============================================================================

# Page configuration
st.set_page_config(
    page_title="Advanced Streaming Hub",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
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
    .main-header {
        text-align: center;
        padding: 20px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px;
        margin-bottom: 30px;
    }
</style>
""", unsafe_allow_html=True)

# TMDB Configuration (for UI only - doesn't affect original functions)
TMDB_API_KEY = "6fad3f86b8452ee232deb7977d7dcf58"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

# Session state initialization
if 'selected_movie' not in st.session_state:
    st.session_state.selected_movie = None
if 'selected_tv' not in st.session_state:
    st.session_state.selected_tv = None
if 'current_m3u8' not in st.session_state:
    st.session_state.current_m3u8 = None
if 'current_referer' not in st.session_state:
    st.session_state.current_referer = None
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = None

# TMDB Functions (for UI only)
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
        "append_to_response": "credits,images"
    }
    return requests.get(url, params=params).json()

@st.cache_data(ttl=3600)
def get_tv_details(tv_id: int) -> Dict:
    """Get detailed TV show information"""
    url = f"{TMDB_BASE_URL}/tv/{tv_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US",
        "append_to_response": "credits,images"
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

def video_player(m3u8_url: str, referer: str = None):
    """Display video player with m3u8 stream"""
    import streamlit.components.v1 as components
    
    st.markdown(f"""
    <div class="stream-info">
        <strong>🎬 Stream URL:</strong> <code>{m3u8_url[:100]}...</code><br>
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
# Main App UI
# ============================================================================

def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🎬 Advanced Streaming Hub</h1>
        <p>Stream movies and TV shows using the enc-dec.app API</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar for search
    with st.sidebar:
        st.markdown("### 🔍 Search")
        search_type = st.radio("Type", ["Movies", "TV Shows", "All"], horizontal=True)
        search_query = st.text_input("Enter title:", placeholder="e.g., Inception, Breaking Bad")
        
        if search_query:
            media_type = "movie" if search_type == "Movies" else "tv" if search_type == "TV Shows" else "all"
            with st.spinner("Searching..."):
                results = search_tmdb(search_query, media_type)
            
            if results:
                st.markdown(f"### 📋 Results ({len(results)})")
                for result in results[:15]:
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
                        st.session_state.current_m3u8 = None
                        st.session_state.extracted_data = None
                        st.rerun()
            elif search_query:
                st.info("No results found")
        
        st.markdown("---")
        st.markdown("### ⚙️ Available Functions")
        st.markdown("""
        - **Videasy** - Full pipeline
        - **VidSync** - Multiple servers
        - **VidLink** - Fast extraction
        - **VidFast** - High quality
        - **Hexa/Flixer** - TMDB integration
        - **LordFlix** - Network servers
        - **Abyss** - Hydrax streams
        - **KissKH** - Drama episodes
        - **OneTouchTV** - VOD content
        - **PrimeSrc** - Voe.sx support
        - **Reanime** - Anime streams
        - **XPrime** - Altcha protected
        - **MegaUp** - AnimeKai embed
        - **RapidShare** - YFlix embed
        - **AnimeKai** - Full pipeline
        - **YFlix/1Movies** - Full pipeline
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
        
        # Function selection for extraction
        st.markdown("---")
        st.markdown("## 🎥 Select Extraction Function")
        
        available_functions = {
            "Videasy": lambda: run_videasy(f"https://player.videasy.net/movie/{movie_id}"),
            "PrimeSrc": lambda: run_primesrc(f"https://primesrc.me/embed/movie?tmdb={movie_id}"),
            "VidFast": lambda: run_vidfast(tmdb_id=str(movie_id), media_type="movie"),
            "VidLink": lambda: run_vidlink(tmdb_id=str(movie_id), media_type="movie"),
            "YFlix/1Movies": lambda: run_yflix(f"https://yflix.to/watch/movie-{movie_id}"),
        }
        
        selected_func = st.selectbox("Choose extraction function:", list(available_functions.keys()))
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("🔍 Extract Stream", type="primary", use_container_width=True):
                with st.spinner(f"Extracting using {selected_func}..."):
                    try:
                        # Redirect stdout to capture print output
                        import io
                        from contextlib import redirect_stdout
                        
                        f = io.StringIO()
                        with redirect_stdout(f):
                            result = available_functions[selected_func]()
                        
                        output_text = f.getvalue()
                        
                        if result:
                            st.session_state.current_m3u8 = result if isinstance(result, str) else None
                            st.session_state.extracted_data = result
                            st.success(f"✅ Extraction completed successfully!")
                            
                            # Show output
                            with st.expander("View extraction log"):
                                st.code(output_text)
                        else:
                            st.warning("No stream URL extracted. Check the log for details.")
                            with st.expander("View extraction log"):
                                st.code(output_text)
                    except Exception as e:
                        st.error(f"Extraction failed: {str(e)}")
        
        with col2:
            if st.session_state.current_m3u8:
                if st.button("🔄 Clear Stream", use_container_width=True):
                    st.session_state.current_m3u8 = None
                    st.session_state.extracted_data = None
                    st.rerun()
        
        # Display extracted stream info
        if st.session_state.extracted_data:
            st.markdown("---")
            st.markdown("### 📊 Extracted Data")
            st.json(st.session_state.extracted_data if isinstance(st.session_state.extracted_data, (dict, list)) else {"url": st.session_state.extracted_data})
        
        # Video player
        if st.session_state.current_m3u8:
            st.markdown("---")
            st.markdown("## 📺 Now Playing")
            video_player(st.session_state.current_m3u8)
    
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
                season_data = get_tv_seasons(tv_id, selected_season)
                episodes = season_data.get("episodes", [])
                episode_numbers = [e["episode_number"] for e in episodes]
                selected_episode = st.selectbox("Episode:", episode_numbers, key="tv_episode")
            
            # Function selection
            st.markdown("### 🎥 Select Extraction Function")
            
            available_functions = {
                "PrimeSrc": lambda: run_primesrc(f"https://primesrc.me/embed/tv?tmdb={tv_id}&season={selected_season}&episode={selected_episode}"),
                "VidFast": lambda: run_vidfast(tmdb_id=str(tv_id), media_type="tv", season=str(selected_season), episode=str(selected_episode)),
                "VidLink": lambda: run_vidlink(tmdb_id=str(tv_id), media_type="tv", season=str(selected_season), episode=str(selected_episode)),
                "YFlix/1Movies": lambda: run_yflix(f"https://yflix.to/watch/tv-{tv_id}", season=str(selected_season), episode=str(selected_episode)),
            }
            
            selected_func = st.selectbox("Choose extraction function:", list(available_functions.keys()), key="tv_func")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("🔍 Extract Stream", type="primary", use_container_width=True, key="tv_extract"):
                    with st.spinner(f"Extracting S{selected_season}E{selected_episode} using {selected_func}..."):
                        try:
                            import io
                            from contextlib import redirect_stdout
                            
                            f = io.StringIO()
                            with redirect_stdout(f):
                                result = available_functions[selected_func]()
                            
                            output_text = f.getvalue()
                            
                            if result:
                                st.session_state.current_m3u8 = result if isinstance(result, str) else None
                                st.session_state.extracted_data = result
                                st.success(f"✅ Extraction completed successfully!")
                                
                                with st.expander("View extraction log"):
                                    st.code(output_text)
                            else:
                                st.warning("No stream URL extracted. Check the log for details.")
                                with st.expander("View extraction log"):
                                    st.code(output_text)
                        except Exception as e:
                            st.error(f"Extraction failed: {str(e)}")
            
            with col2:
                if st.session_state.current_m3u8:
                    if st.button("🔄 Clear Stream", use_container_width=True, key="tv_clear"):
                        st.session_state.current_m3u8 = None
                        st.session_state.extracted_data = None
                        st.rerun()
            
            # Display extracted data
            if st.session_state.extracted_data:
                st.markdown("---")
                st.markdown("### 📊 Extracted Data")
                st.json(st.session_state.extracted_data if isinstance(st.session_state.extracted_data, (dict, list)) else {"url": st.session_state.extracted_data})
            
            # Video player
            if st.session_state.current_m3u8:
                st.markdown("---")
                st.markdown(f"## 📺 Now Playing: S{selected_season}E{selected_episode}")
                video_player(st.session_state.current_m3u8)
    
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
                <li>🎥 16 different extraction functions preserved</li>
                <li>📺 Automatic m3u8 extraction and playback</li>
                <li>🎨 Modern, responsive interface</li>
                <li>⚡ All original enc-dec.app functionality intact</li>
            </ul>
            <br>
            <p><strong>Note:</strong> Select a movie/TV show from the sidebar to begin streaming</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Featured content
        st.markdown("### 🔥 Popular Now")
        try:
            popular_movies = search_tmdb("marvel", "movie")[:6]
            cols = st.columns(3)
            for idx, movie in enumerate(popular_movies[:3]):
                with cols[idx]:
                    poster = get_image_url(movie.get("poster_path"), "w300")
                    st.image(poster, use_container_width=True)
                    st.caption(movie.get("title", "")[:30])
        except:
            st.info("Search for content to get started")

if __name__ == "__main__":
    main()
