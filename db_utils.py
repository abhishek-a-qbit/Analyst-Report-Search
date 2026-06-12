"""
SQLite database module for storing search history permanently.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Database file path
DB_PATH = Path("search_history.db")


def get_db_connection():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database with required tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create search_history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            search_type TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            results_json TEXT,
            metadata_json TEXT
        )
    """)
    
    # Create index on timestamp for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp 
        ON search_history(timestamp DESC)
    """)
    
    # Create index on search_type
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_search_type 
        ON search_history(search_type)
    """)
    
    conn.commit()
    conn.close()
    print(f"DEBUG: Database initialized at {DB_PATH}")


def save_search(query: str, search_type: str, results: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> int:
    """Save a search to the database.
    
    Args:
        query: The search query
        search_type: Type of search (search, deep, category, wide_net)
        results: The search results dictionary
        metadata: Additional metadata (optional)
    
    Returns:
        The ID of the inserted record
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    results_json = json.dumps(results)
    metadata_json = json.dumps(metadata) if metadata else None
    
    cursor.execute("""
        INSERT INTO search_history (query, search_type, results_json, metadata_json)
        VALUES (?, ?, ?, ?)
    """, (query, search_type, results_json, metadata_json))
    
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    print(f"DEBUG: Saved search to database (ID: {record_id}, Type: {search_type})")
    return record_id


def get_all_searches(limit: int = 100) -> List[Dict[str, Any]]:
    """Get all searches from the database, most recent first.
    
    Args:
        limit: Maximum number of records to return
    
    Returns:
        List of search history records
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, query, search_type, timestamp, results_json, metadata_json
        FROM search_history
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    searches = []
    for row in rows:
        search = {
            "id": row["id"],
            "query": row["query"],
            "search_type": row["search_type"],
            "timestamp": row["timestamp"],
            "results": json.loads(row["results_json"]),
            "metadata": json.loads(row["metadata_json"]) if row["metadata_json"] else None
        }
        searches.append(search)
    
    print(f"DEBUG: Retrieved {len(searches)} searches from database")
    return searches


def get_search_by_id(search_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific search by ID.
    
    Args:
        search_id: The ID of the search
    
    Returns:
        The search record or None if not found
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, query, search_type, timestamp, results_json, metadata_json
        FROM search_history
        WHERE id = ?
    """, (search_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row["id"],
            "query": row["query"],
            "search_type": row["search_type"],
            "timestamp": row["timestamp"],
            "results": json.loads(row["results_json"]),
            "metadata": json.loads(row["metadata_json"]) if row["metadata_json"] else None
        }
    return None


def get_searches_by_type(search_type: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get searches by type.
    
    Args:
        search_type: The type of search (search, deep, category, wide_net)
        limit: Maximum number of records to return
    
    Returns:
        List of search history records
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, query, search_type, timestamp, results_json, metadata_json
        FROM search_history
        WHERE search_type = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (search_type, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    searches = []
    for row in rows:
        search = {
            "id": row["id"],
            "query": row["query"],
            "search_type": row["search_type"],
            "timestamp": row["timestamp"],
            "results": json.loads(row["results_json"]),
            "metadata": json.loads(row["metadata_json"]) if row["metadata_json"] else None
        }
        searches.append(search)
    
    return searches


def delete_search(search_id: int) -> bool:
    """Delete a search by ID.
    
    Args:
        search_id: The ID of the search to delete
    
    Returns:
        True if deleted, False otherwise
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM search_history WHERE id = ?", (search_id,))
    deleted = cursor.rowcount > 0
    
    conn.commit()
    conn.close()
    
    if deleted:
        print(f"DEBUG: Deleted search ID {search_id}")
    return deleted


def clear_all_history() -> int:
    """Clear all search history.
    
    Returns:
        Number of records deleted
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM search_history")
    count = cursor.fetchone()[0]
    
    cursor.execute("DELETE FROM search_history")
    conn.commit()
    conn.close()
    
    print(f"DEBUG: Cleared all search history ({count} records)")
    return count


def get_search_stats() -> Dict[str, Any]:
    """Get statistics about the search history.
    
    Returns:
        Dictionary with statistics
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total searches
    cursor.execute("SELECT COUNT(*) FROM search_history")
    total_searches = cursor.fetchone()[0]
    
    # Searches by type
    cursor.execute("""
        SELECT search_type, COUNT(*) as count
        FROM search_history
        GROUP BY search_type
    """)
    searches_by_type = {row["search_type"]: row["count"] for row in cursor.fetchall()}
    
    # Most recent search
    cursor.execute("""
        SELECT timestamp FROM search_history
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    last_search = cursor.fetchone()
    last_search_timestamp = last_search["timestamp"] if last_search else None
    
    conn.close()
    
    return {
        "total_searches": total_searches,
        "searches_by_type": searches_by_type,
        "last_search_timestamp": last_search_timestamp
    }


# Initialize database on module import
init_db()
