"""Hub update writer for session-derived cross-project summaries.

Writes session point data to date-partitioned hub updates for
organization-wide taste accumulation and distribution.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class SessionPoint:
    """Represents a single session data point."""
    timestamp: str
    session_id: str
    spoke_id: str
    project_name: str
    taste_constraints: Dict[str, Any]
    metadata: Dict[str, Any]


@dataclass
class HubUpdate:
    """Represents a hub update record."""
    update_id: str
    timestamp: str
    source_spoke: str
    source_session: str
    data_type: str
    payload: Dict[str, Any]
    confidence: float


class HubUpdateWriter:
    """Writes session data to hub update store."""
    
    def __init__(self, hub_updates_path: str = "data/profiles/hub/hub-updates"):
        """Initialize writer with hub updates path."""
        self.hub_updates_path = Path(hub_updates_path)
        self.hub_updates_path.mkdir(parents=True, exist_ok=True)
    
    def write_session_update(self, session_point: SessionPoint) -> str:
        """Write session point as hub update.
        
        Returns:
            Update ID of written record
        """
        # Create update record
        update = HubUpdate(
            update_id=self._generate_update_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_spoke=session_point.spoke_id,
            source_session=session_point.session_id,
            data_type="session_taste_point",
            payload=asdict(session_point),
            confidence=self._calculate_confidence(session_point)
        )
        
        # Write to date-partitioned path
        date_path = self._get_date_path(session_point.timestamp)
        update_file = date_path / f"{update.update_id}.json"
        
        update_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(update_file, 'w') as f:
            json.dump(asdict(update), f, indent=2)
        
        return update.update_id
    
    def write_taste_promotion(self, spoke_id: str, spoke_taste: Dict[str, Any], 
                            metadata: Dict[str, Any]) -> str:
        """Write taste promotion proposal to hub."""
        update = HubUpdate(
            update_id=self._generate_update_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_spoke=spoke_id,
            source_session="promotion_proposal",
            data_type="taste_promotion",
            payload={
                "spoke_taste": spoke_taste,
                "metadata": metadata,
                "status": "pending_review"
            },
            confidence=self._calculate_promotion_confidence(spoke_taste)
        )
        
        date_path = self._get_date_path(update.timestamp)
        update_file = date_path / f"{update.update_id}.json"
        
        update_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(update_file, 'w') as f:
            json.dump(asdict(update), f, indent=2)
        
        return update.update_id
    
    def write_conflict_record(self, conflict: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        """Write hub/spoke conflict record."""
        update = HubUpdate(
            update_id=self._generate_update_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_spoke=metadata.get("spoke_id", "unknown"),
            source_session="conflict_detection",
            data_type="taste_conflict",
            payload={
                "conflict": conflict,
                "metadata": metadata,
                "resolution_status": "detected"
            },
            confidence=1.0  # Conflicts are high confidence
        )
        
        date_path = self._get_date_path(update.timestamp)
        update_file = date_path / f"{update.update_id}.json"
        
        update_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(update_file, 'w') as f:
            json.dump(asdict(update), f, indent=2)
        
        return update.update_id
    
    def _generate_update_id(self) -> str:
        """Generate unique update ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        return f"hub_update_{timestamp}"
    
    def _get_date_path(self, timestamp: str) -> Path:
        """Get date-partitioned path for timestamp."""
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            date_str = dt.strftime("%Y/%m/%d")
        except (ValueError, AttributeError):
            # Fallback to current date
            date_str = datetime.now().strftime("%Y/%m/%d")
        
        return self.hub_updates_path / date_str
    
    def _calculate_confidence(self, session_point: SessionPoint) -> float:
        """Calculate confidence score for session point."""
        confidence = 0.5  # Base confidence
        
        # Boost based on metadata quality
        if session_point.metadata.get("session_duration"):
            confidence += 0.1
        
        if session_point.metadata.get("taste_reviewed"):
            confidence += 0.2
        
        if session_point.metadata.get("conflicts_checked"):
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _calculate_promotion_confidence(self, spoke_taste: Dict[str, Any]) -> float:
        """Calculate confidence score for taste promotion."""
        confidence = 0.3  # Base promotion confidence (lower than session data)
        
        # Boost based on spoke taste completeness
        if spoke_taste.get("constraints_complete"):
            confidence += 0.2
        
        if spoke_taste.get("peer_approved"):
            confidence += 0.3
        
        if spoke_taste.get("quality_score", 0) >= 7:
            confidence += 0.2
        
        return min(confidence, 1.0)
    
    def load_recent_updates(self, days: int = 7) -> List[HubUpdate]:
        """Load recent hub updates for analysis."""
        from datetime import timedelta
        
        updates = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Scan date-partitioned directories
        date_dirs = [d for d in self.hub_updates_path.iterdir() if d.is_dir()]
        
        for date_dir in date_dirs:
            try:
                dir_date = datetime.strptime(date_dir.name, "%Y/%m/%d")
                if dir_date >= cutoff_date:
                    updates.extend(self._load_updates_from_dir(date_dir))
            except ValueError:
                continue  # Skip invalid date directories
        
        # Sort by timestamp
        updates.sort(key=lambda u: u.timestamp)
        return updates
    
    def _load_updates_from_dir(self, date_dir: Path) -> List[HubUpdate]:
        """Load all updates from a date directory."""
        updates = []
        
        for update_file in date_dir.glob("*.json"):
            try:
                with open(update_file, 'r') as f:
                    update_data = json.load(f)
                    update = HubUpdate(**update_data)
                    updates.append(update)
            except (json.JSONDecodeError, IOError, TypeError):
                continue  # Skip corrupt files
        
        return updates
    
    def get_update_statistics(self, days: int = 30) -> Dict[str, Any]:
        """Get statistics about hub updates."""
        updates = self.load_recent_updates(days)
        
        if not updates:
            return {"total_updates": 0}
        
        stats = {
            "total_updates": len(updates),
            "data_types": {},
            "source_spokes": set(),
            "date_range": {
                "earliest": updates[0].timestamp if updates else None,
                "latest": updates[-1].timestamp if updates else None
            }
        }
        
        for update in updates:
            # Count by data type
            data_type = update.data_type
            stats["data_types"][data_type] = stats["data_types"].get(data_type, 0) + 1
            
            # Collect source spokes
            stats["source_spokes"].add(update.source_spoke)
        
        stats["source_spokes"] = len(stats["source_spokes"])
        
        return stats