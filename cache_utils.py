import os
import json
import hashlib
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

# Cache configuration
CACHE_DIR = Path("serper_cache")
CACHE_TTL_SECONDS = 48 * 60 * 60  # 48 hours
CACHE_VERSION = "v1"  # Version to invalidate cache on schema changes


def get_cache_key(query: str) -> str:
    """Generate a unique cache key for a search query."""
    # Normalize query: lowercase, strip whitespace
    normalized = query.lower().strip()
    # Create hash for filename
    hash_obj = hashlib.md5(normalized.encode())
    return f"{CACHE_VERSION}_{hash_obj.hexdigest()}.json"


def get_cache_file_path(cache_key: str) -> Path:
    """Get the full path for a cache file."""
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / cache_key


def is_cache_valid(cache_file: Path) -> bool:
    """Check if a cache file is still valid based on TTL."""
    if not cache_file.exists():
        return False
    
    file_age = time.time() - cache_file.stat().st_mtime
    return file_age < CACHE_TTL_SECONDS


def get_cached_results(query: str) -> Optional[List[Dict]]:
    """Retrieve cached results for a query if available and valid."""
    cache_key = get_cache_key(query)
    cache_file = get_cache_file_path(cache_key)
    
    if not is_cache_valid(cache_file):
        return None
    
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        # Verify the query matches (prevent hash collisions)
        if cache_data.get("query") != query.lower().strip():
            return None
        
        print(f"DEBUG: Cache HIT for query: {query[:50]}...")
        return cache_data.get("results", [])
    except Exception as e:
        print(f"DEBUG: Cache read error: {e}")
        return None


def cache_results(query: str, results: List[Dict]) -> None:
    """Cache search results for a query."""
    cache_key = get_cache_key(query)
    cache_file = get_cache_file_path(cache_key)
    
    try:
        cache_data = {
            "query": query.lower().strip(),
            "results": results,
            "timestamp": time.time(),
            "cache_version": CACHE_VERSION
        }
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        
        print(f"DEBUG: Cached results for query: {query[:50]}...")
    except Exception as e:
        print(f"DEBUG: Cache write error: {e}")


def clear_cache() -> int:
    """Clear all cached files. Returns number of files deleted."""
    if not CACHE_DIR.exists():
        return 0
    
    deleted_count = 0
    for cache_file in CACHE_DIR.glob("*.json"):
        try:
            cache_file.unlink()
            deleted_count += 1
        except Exception as e:
            print(f"DEBUG: Error deleting cache file {cache_file}: {e}")
    
    print(f"DEBUG: Cleared {deleted_count} cache files")
    return deleted_count


def get_cache_stats() -> Dict[str, Any]:
    """Get statistics about the cache."""
    if not CACHE_DIR.exists():
        return {
            "total_files": 0,
            "total_size_bytes": 0,
            "valid_files": 0,
            "expired_files": 0
        }
    
    total_files = 0
    total_size = 0
    valid_files = 0
    expired_files = 0
    current_time = time.time()
    
    for cache_file in CACHE_DIR.glob("*.json"):
        total_files += 1
        total_size += cache_file.stat().st_size
        
        file_age = current_time - cache_file.stat().st_mtime
        if file_age < CACHE_TTL_SECONDS:
            valid_files += 1
        else:
            expired_files += 1
    
    return {
        "total_files": total_files,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "valid_files": valid_files,
        "expired_files": expired_files
    }


def cleanup_expired_cache() -> int:
    """Remove expired cache files. Returns number of files deleted."""
    if not CACHE_DIR.exists():
        return 0
    
    deleted_count = 0
    current_time = time.time()
    
    for cache_file in CACHE_DIR.glob("*.json"):
        file_age = current_time - cache_file.stat().st_mtime
        if file_age >= CACHE_TTL_SECONDS:
            try:
                cache_file.unlink()
                deleted_count += 1
            except Exception as e:
                print(f"DEBUG: Error deleting expired cache file {cache_file}: {e}")
    
    print(f"DEBUG: Cleaned up {deleted_count} expired cache files")
    return deleted_count
