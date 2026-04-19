"""
Open VSX Registry API Client for VNCode IDE.
Communicates with https://open-vsx.org to search, query, and download extensions.
Uses only stdlib (urllib) — no pip dependencies needed.
"""

import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
import os
import logging
from pathlib import Path
from typing import Optional

BASE_URL = "https://open-vsx.org/api"

# Get logger
logger = logging.getLogger('vncode')

# Reusable SSL context with certificate verification disabled
# (Windows Python often lacks proper CA certificates)
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def _get_json(url: str, timeout: int = 15) -> Optional[dict]:
    """GET a URL and parse JSON response. Returns None on error."""
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "VNCode-IDE/1.1"
        })
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
            data = resp.read()
            return json.loads(data.decode("utf-8"))
    except Exception as e:
        logger.error(f"GET {url} failed: {e}")
        return None


def search_extensions(query: str, offset: int = 0, size: int = 20,
                      sort_by: str = "relevance", sort_order: str = "desc",
                      category: str = "") -> Optional[dict]:
    """
    Search extensions on Open VSX.
    Returns {"offset", "totalSize", "extensions": [...]}.
    
    Note: OpenVSX API may not support all sort options. Use with caution.
    """
    params = {
        "query": query,
        "size": size,
        "offset": offset,
    }
    
    # Only add sort parameters if they are supported
    if sort_by in ["relevance"]:  # Add more as discovered
        params["sortBy"] = sort_by
        params["sortOrder"] = sort_order
    
    # Add category to query if specified
    if category and category != "all":
        if query.strip():
            params["query"] = f"{query} {category}"
        else:
            params["query"] = category
    
    url = f"{BASE_URL}/-/search?{urllib.parse.urlencode(params)}"
    return _get_json(url)


def get_extension_detail(namespace: str, name: str) -> Optional[dict]:
    """Get detailed info about a specific extension."""
    url = f"{BASE_URL}/{namespace}/{name}"
    return _get_json(url)


def get_extension_version(namespace: str, name: str, version: str) -> Optional[dict]:
    """Get info about a specific version of an extension."""
    url = f"{BASE_URL}/{namespace}/{name}/{version}"
    return _get_json(url)


def download_file(url: str, save_path: str, progress_callback=None) -> bool:
    """
    Download a file from URL to save_path.
    progress_callback(bytes_downloaded, total_bytes) is called periodically.
    Returns True on success.
    """
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "VNCode-IDE/1.1"
        })
        with urllib.request.urlopen(req, timeout=60, context=_ssl_ctx) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            downloaded = 0
            chunk_size = 8192

            with open(save_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)

        return True
    except Exception as e:
        logger.error(f"Download {url} failed: {e}")
        # Clean up partial file
        try:
            if os.path.exists(save_path):
                os.remove(save_path)
        except OSError:
            pass
        return False


def download_icon(icon_url: str, cache_dir: str) -> Optional[str]:
    """
    Download an extension icon to cache. Returns local path or None.
    Uses URL hash as filename to avoid re-downloading.
    """
    if not icon_url:
        return None

    import hashlib
    url_hash = hashlib.md5(icon_url.encode()).hexdigest()
    ext = ".png"
    if ".svg" in icon_url.lower():
        ext = ".svg"
    elif ".jpg" in icon_url.lower() or ".jpeg" in icon_url.lower():
        ext = ".jpg"

    cache_path = os.path.join(cache_dir, f"icon_{url_hash}{ext}")
    if os.path.exists(cache_path):
        return cache_path

    if download_file(icon_url, cache_path):
        return cache_path
    return None


def format_download_count(count: int) -> str:
    """Format download count: 38559674 → '38.6M'"""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def get_featured_extensions(size: int = 10) -> Optional[list]:
    """
    Get featured/popular extensions.
    Returns list of extension dicts.
    """
    # Search for popular extensions without query
    result = search_extensions("", size=size, sort_by="downloads", sort_order="desc")
    if result and "extensions" in result:
        return result["extensions"]
    return None


def check_extension_updates(namespace: str, name: str, current_version: str) -> Optional[dict]:
    """
    Check if there's a newer version of an extension available.
    Returns the latest extension info if update available, None otherwise.
    """
    # Get latest version info
    latest = get_extension_detail(namespace, name)
    if latest and latest.get("version") != current_version:
        return latest
    return None
