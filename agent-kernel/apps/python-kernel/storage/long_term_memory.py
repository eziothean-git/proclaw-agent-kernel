"""
Long-term memory storage manager using filesystem.

Provides persistent storage for long-term memory candidates,
with support for querying by session, category, and importance.

Storage Structure:
    data/long_term_memory/
        ├── index.json                    # Global index for fast lookups
        ├── by_session/
        │   └── {session_id}.jsonl       # Memory entries per session
        └── by_category/
            └── {category}.jsonl         # Memory entries per category
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from schemas.models import LongTermMemoryCandidate

logger = structlog.get_logger()


class LongTermMemoryStore:
    """
    Filesystem-based long-term memory storage.
    
    Design principles:
    - Append-only writes for durability
    - Index file for fast lookups
    - Separate files by session and category for efficient querying
    - JSONL format for easy appending and streaming reads
    """
    
    def __init__(self, base_path: str = "./data"):
        self.base_path = Path(base_path) / "long_term_memory"
        self._ensure_directories()
        self.logger = logger.bind(component="LongTermMemoryStore")
        
    def _ensure_directories(self) -> None:
        """Create necessary directory structure."""
        for subdir in ["by_session", "by_category"]:
            (self.base_path / subdir).mkdir(parents=True, exist_ok=True)
    
    def _get_index_path(self) -> Path:
        """Get path to index file."""
        return self.base_path / "index.json"
    
    def _get_session_path(self, session_id: str) -> Path:
        """Get path to session memory file."""
        return self.base_path / "by_session" / f"{session_id}.jsonl"
    
    def _get_category_path(self, category: str) -> Path:
        """Get path to category memory file."""
        # Sanitize category name for filesystem
        safe_category = "".join(c if c.isalnum() or c in "-_" else "_" for c in category)
        return self.base_path / "by_category" / f"{safe_category}.jsonl"
    
    def _load_index(self) -> dict[str, Any]:
        """Load index file or create empty index."""
        index_path = self._get_index_path()
        if index_path.exists():
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.logger.error("Failed to load index, creating new", error=str(e))
        
        return {
            "version": "1.0",
            "created_at": datetime.utcnow().isoformat(),
            "total_entries": 0,
            "sessions": {},
            "categories": {},
        }
    
    def _save_index(self, index: dict[str, Any]) -> None:
        """Save index to file."""
        index_path = self._get_index_path()
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False, default=str)
    
    def _append_to_jsonl(self, path: Path, data: dict[str, Any]) -> None:
        """Append a record to JSONL file."""
        with open(path, 'a', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, default=str)
            f.write('\n')
    
    def _read_jsonl(self, path: Path, limit: Optional[int] = None) -> list[dict[str, Any]]:
        """Read records from JSONL file."""
        if not path.exists():
            return []
        
        records = []
        with open(path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if limit is not None and i >= limit:
                    break
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        # Convert string datetime back to datetime object
                        if 'created_at' in record and isinstance(record['created_at'], str):
                            try:
                                record['created_at'] = datetime.fromisoformat(record['created_at'])
                            except ValueError:
                                # Keep as string if parsing fails
                                pass
                        records.append(record)
                    except json.JSONDecodeError:
                        self.logger.warning("Skipping malformed JSONL line", line=line[:100])
        
        return records
    
    def save_candidate(self, candidate: LongTermMemoryCandidate) -> bool:
        """
        Save a long-term memory candidate.
        
        Args:
            candidate: Memory candidate to save
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Convert candidate to dict
            data = candidate.model_dump(mode='json')
            
            # Append to session file
            session_path = self._get_session_path(candidate.session_id)
            self._append_to_jsonl(session_path, data)
            
            # Append to category file
            category_path = self._get_category_path(candidate.category)
            self._append_to_jsonl(category_path, data)
            
            # Update index
            index = self._load_index()
            index["total_entries"] = index.get("total_entries", 0) + 1
            index["updated_at"] = datetime.utcnow().isoformat()
            
            # Update session index
            if candidate.session_id not in index["sessions"]:
                index["sessions"][candidate.session_id] = {
                    "count": 0,
                    "categories": [],
                    "last_entry": None,
                }
            index["sessions"][candidate.session_id]["count"] += 1
            index["sessions"][candidate.session_id]["last_entry"] = candidate.created_at.isoformat()
            if candidate.category not in index["sessions"][candidate.session_id]["categories"]:
                index["sessions"][candidate.session_id]["categories"].append(candidate.category)
            
            # Update category index
            if candidate.category not in index["categories"]:
                index["categories"][candidate.category] = {
                    "count": 0,
                    "sessions": [],
                    "last_entry": None,
                }
            index["categories"][candidate.category]["count"] += 1
            index["categories"][candidate.category]["last_entry"] = candidate.created_at.isoformat()
            if candidate.session_id not in index["categories"][candidate.category]["sessions"]:
                index["categories"][candidate.category]["sessions"].append(candidate.session_id)
            
            self._save_index(index)
            
            self.logger.info(
                "Saved long-term memory candidate",
                candidate_id=candidate.id,
                session_id=candidate.session_id,
                category=candidate.category,
                importance=candidate.importance_score,
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to save long-term memory candidate",
                candidate_id=candidate.id,
                error=str(e),
            )
            return False
    
    def query_by_session(
        self, 
        session_id: str, 
        limit: Optional[int] = None,
        min_importance: Optional[float] = None,
    ) -> list[LongTermMemoryCandidate]:
        """
        Query memory entries by session.
        
        Args:
            session_id: Session ID to query
            limit: Maximum number of entries to return
            min_importance: Minimum importance score filter
            
        Returns:
            List of memory candidates (newest first)
        """
        session_path = self._get_session_path(session_id)
        records = self._read_jsonl(session_path)
        
        # Filter by importance if specified
        if min_importance is not None:
            records = [r for r in records if r.get("importance_score", 0) >= min_importance]
        
        # Sort by created_at (newest first)
        records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        
        # Apply limit
        if limit is not None:
            records = records[:limit]
        
        return [LongTermMemoryCandidate(**r) for r in records]
    
    def query_by_category(
        self, 
        category: str, 
        limit: Optional[int] = None,
        min_importance: Optional[float] = None,
    ) -> list[LongTermMemoryCandidate]:
        """
        Query memory entries by category.
        
        Args:
            category: Category to query
            limit: Maximum number of entries to return
            min_importance: Minimum importance score filter
            
        Returns:
            List of memory candidates (newest first)
        """
        category_path = self._get_category_path(category)
        records = self._read_jsonl(category_path)
        
        # Filter by importance if specified
        if min_importance is not None:
            records = [r for r in records if r.get("importance_score", 0) >= min_importance]
        
        # Sort by created_at (newest first)
        records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        
        # Apply limit
        if limit is not None:
            records = records[:limit]
        
        return [LongTermMemoryCandidate(**r) for r in records]
    
    def search_by_importance(
        self, 
        min_score: float,
        session_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[LongTermMemoryCandidate]:
        """
        Search memory entries by importance score.
        
        Args:
            min_score: Minimum importance score
            session_id: Optional session filter
            limit: Maximum number of entries to return
            
        Returns:
            List of memory candidates (sorted by importance, highest first)
        """
        if session_id:
            # Query specific session
            candidates = self.query_by_session(session_id, min_importance=min_score)
        else:
            # Query all sessions (inefficient for large datasets)
            candidates = []
            index = self._load_index()
            for session_id in index.get("sessions", {}).keys():
                candidates.extend(self.query_by_session(session_id, min_importance=min_score))
        
        # Sort by importance (highest first)
        candidates.sort(key=lambda c: c.importance_score, reverse=True)
        
        # Apply limit
        if limit is not None:
            candidates = candidates[:limit]
        
        return candidates
    
    def get_statistics(self) -> dict[str, Any]:
        """Get storage statistics."""
        index = self._load_index()
        return {
            "total_entries": index.get("total_entries", 0),
            "session_count": len(index.get("sessions", {})),
            "category_count": len(index.get("categories", {})),
            "sessions": {
                sid: {
                    "count": info.get("count", 0),
                    "categories": info.get("categories", []),
                }
                for sid, info in index.get("sessions", {}).items()
            },
            "categories": {
                cat: {
                    "count": info.get("count", 0),
                    "sessions": len(info.get("sessions", [])),
                }
                for cat, info in index.get("categories", {}).items()
            },
        }
    
    def delete_session_memories(self, session_id: str) -> bool:
        """
        Delete all memories for a session.
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            True if deleted successfully
        """
        try:
            session_path = self._get_session_path(session_id)
            if session_path.exists():
                session_path.unlink()
            
            # Update index
            index = self._load_index()
            if session_id in index.get("sessions", {}):
                count = index["sessions"][session_id].get("count", 0)
                index["total_entries"] = max(0, index.get("total_entries", 0) - count)
                del index["sessions"][session_id]
                
                # Remove from category indexes
                for cat_info in index.get("categories", {}).values():
                    if session_id in cat_info.get("sessions", []):
                        cat_info["sessions"].remove(session_id)
                
                self._save_index(index)
            
            self.logger.info("Deleted session memories", session_id=session_id)
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to delete session memories",
                session_id=session_id,
                error=str(e),
            )
            return False


# Singleton instance
_ltm_store: LongTermMemoryStore | None = None


def get_long_term_memory_store(base_path: str = "./data") -> LongTermMemoryStore:
    """Get or create singleton instance."""
    global _ltm_store
    if _ltm_store is None:
        _ltm_store = LongTermMemoryStore(base_path)
    return _ltm_store


def reset_long_term_memory_store() -> None:
    """Reset singleton instance (useful for testing)."""
    global _ltm_store
    _ltm_store = None
