"""Promotion manager for spoke-to-hub candidate constraints.

Generates promotion proposals from spoke-derived constraints
for hub review and potential adoption.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict
from enum import Enum


class PromotionStatus(Enum):
    """Status of a promotion proposal."""
    PENDING = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged_into_hub"
    EXPIRED = "expired"


@dataclass
class PromotionProposal:
    """Represents a spoke-to-hub promotion proposal."""
    proposal_id: str
    spoke_id: str
    spoke_name: str
    proposed_constraints: Dict[str, Any]
    current_hub_constraints: Dict[str, Any]
    conflict_analysis: Dict[str, Any]
    metadata: Dict[str, Any]
    status: PromotionStatus
    created_at: str
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    review_notes: Optional[str] = None


class PromotionManager:
    """Manages spoke-to-hub promotion proposals."""
    
    def __init__(self, proposals_path: str = "data/promotions"):
        """Initialize promotion manager."""
        self.proposals_path = Path(proposals_path)
        self.proposals_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (self.proposals_path / "pending").mkdir(exist_ok=True)
        (self.proposals_path / "approved").mkdir(exist_ok=True)
        (self.proposals_path / "rejected").mkdir(exist_ok=True)
    
    def generate_proposal(self, spoke_id: str, spoke_name: str, 
                         spoke_taste: Dict[str, Any], 
                         hub_taste: Dict[str, Any],
                         metadata: Dict[str, Any]) -> PromotionProposal:
        """Generate a promotion proposal from spoke constraints."""
        
        # Analyze conflicts between spoke and hub
        conflict_analysis = self._analyze_conflicts(spoke_taste, hub_taste)
        
        # Create proposal
        proposal = PromotionProposal(
            proposal_id=self._generate_proposal_id(),
            spoke_id=spoke_id,
            spoke_name=spoke_name,
            proposed_constraints=spoke_taste,
            current_hub_constraints=hub_taste,
            conflict_analysis=conflict_analysis,
            metadata=metadata,
            status=PromotionStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat()
        )
        
        return proposal
    
    def save_proposal(self, proposal: PromotionProposal):
        """Save proposal to appropriate directory based on status."""
        filename = f"{proposal.proposal_id}.json"
        
        if proposal.status == PromotionStatus.PENDING:
            filepath = self.proposals_path / "pending" / filename
        elif proposal.status == PromotionStatus.APPROVED:
            filepath = self.proposals_path / "approved" / filename
        elif proposal.status == PromotionStatus.REJECTED:
            filepath = self.proposals_path / "rejected" / filename
        else:
            filepath = self.proposals_path / filename
        
        with open(filepath, 'w') as f:
            proposal_dict = asdict(proposal)
            proposal_dict["status"] = proposal.status.value  # Convert enum to string
            json.dump(proposal_dict, f, indent=2)
    
    def load_pending_proposals(self) -> List[PromotionProposal]:
        """Load all pending promotion proposals."""
        proposals = []
        pending_dir = self.proposals_path / "pending"
        
        for proposal_file in pending_dir.glob("*.json"):
            try:
                with open(proposal_file, 'r') as f:
                    proposal_data = json.load(f)
                    proposal = PromotionProposal(**proposal_data)
                    proposal.status = PromotionStatus(proposal_data["status"])
                    proposals.append(proposal)
            except (json.JSONDecodeError, IOError, TypeError):
                continue
        
        # Sort by creation date (newest first)
        proposals.sort(key=lambda p: p.created_at, reverse=True)
        return proposals
    
    def review_proposal(self, proposal_id: str, status: PromotionStatus,
                       reviewed_by: str, review_notes: str = "") -> bool:
        """Review a promotion proposal."""
        proposals = self.load_pending_proposals()
        
        for proposal in proposals:
            if proposal.proposal_id == proposal_id:
                proposal.status = status
                proposal.reviewed_at = datetime.now(timezone.utc).isoformat()
                proposal.reviewed_by = reviewed_by
                proposal.review_notes = review_notes
                
                # Move to appropriate directory
                self.save_proposal(proposal)
                
                # Remove from pending
                pending_file = self.proposals_path / "pending" / f"{proposal_id}.json"
                if pending_file.exists():
                    pending_file.unlink()
                
                return True
        
        return False
    
    def merge_approved_proposals(self, hub_taste_path: Path) -> Dict[str, Any]:
        """Merge all approved proposals into hub taste."""
        approved_dir = self.proposals_path / "approved"
        
        if not hub_taste_path.exists():
            return {"error": "Hub taste file not found"}
        
        # Load current hub taste
        with open(hub_taste_path, 'r') as f:
            hub_taste = json.load(f)
        
        merged_count = 0
        conflicts = []
        
        # Process all approved proposals
        for proposal_file in approved_dir.glob("*.json"):
            try:
                with open(proposal_file, 'r') as f:
                    proposal_data = json.load(f)
                    proposal = PromotionProposal(**proposal_data)
                    proposal.status = PromotionStatus(proposal_data["status"])
                
                if proposal.status != PromotionStatus.APPROVED:
                    continue
                
                # Merge constraints (simple overwrite for now)
                for key, value in proposal.proposed_constraints.items():
                    if key in hub_taste and hub_taste[key] != value:
                        conflicts.append({
                            "key": key,
                            "hub_value": hub_taste[key],
                            "proposed_value": value,
                            "proposal_id": proposal.proposal_id
                        })
                    else:
                        hub_taste[key] = value
                        merged_count += 1
                
                # Mark as merged
                proposal.status = PromotionStatus.MERGED
                self.save_proposal(proposal)
                
            except (json.JSONDecodeError, IOError, TypeError):
                continue
        
        # Save updated hub taste
        with open(hub_taste_path, 'w') as f:
            json.dump(hub_taste, f, indent=2)
        
        return {
            "merged_constraints": merged_count,
            "conflicts": conflicts,
            "processed_proposals": len(list(approved_dir.glob("*.json")))
        }
    
    def _analyze_conflicts(self, spoke_taste: Dict[str, Any], 
                          hub_taste: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze conflicts between spoke and hub constraints."""
        conflicts = []
        additions = []
        compatibles = []
        
        spoke_keys = set(spoke_taste.keys())
        hub_keys = set(hub_taste.keys())
        
        # Check for conflicts (same key, different value)
        for key in spoke_keys & hub_keys:
            if spoke_taste[key] != hub_taste[key]:
                conflicts.append({
                    "key": key,
                    "spoke_value": spoke_taste[key],
                    "hub_value": hub_taste[key],
                    "severity": self._assess_conflict_severity(key, spoke_taste[key], hub_taste[key])
                })
            else:
                compatibles.append(key)
        
        # Check for additions (keys in spoke but not in hub)
        for key in spoke_keys - hub_keys:
            additions.append(key)
        
        return {
            "conflicts": conflicts,
            "additions": additions,
            "compatibles": compatibles,
            "total_conflicts": len(conflicts),
            "total_additions": len(additions),
            "total_compatibles": len(compatibles),
            "compatibility_score": len(compatibles) / max(len(spoke_keys), 1)
        }
    
    def _assess_conflict_severity(self, key: str, spoke_value: Any, hub_value: Any) -> str:
        """Assess severity of a constraint conflict."""
        # Simple severity assessment - can be enhanced
        high_severity_keys = ["version_scheme", "test_framework", "core_dependencies"]
        medium_severity_keys = ["style_guide", "lint_rules", "build_tools"]
        
        if key in high_severity_keys:
            return "high"
        elif key in medium_severity_keys:
            return "medium"
        else:
            return "low"
    
    def _generate_proposal_id(self) -> str:
        """Generate unique proposal ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"promotion_{timestamp}"
    
    def get_proposal_statistics(self) -> Dict[str, Any]:
        """Get statistics about promotion proposals."""
        stats = {
            "pending": len(list((self.proposals_path / "pending").glob("*.json"))),
            "approved": len(list((self.proposals_path / "approved").glob("*.json"))),
            "rejected": len(list((self.proposals_path / "rejected").glob("*.json")))
        }
        
        stats["total"] = sum(stats.values())
        
        # Get aging info for pending proposals
        pending_proposals = self.load_pending_proposals()
        if pending_proposals:
            oldest = pending_proposals[-1]  # Sorted newest first, so last is oldest
            stats["oldest_pending_age_days"] = self._calculate_age_days(oldest.created_at)
        
        return stats
    
    def _calculate_age_days(self, timestamp: str) -> int:
        """Calculate age in days from timestamp."""
        try:
            created = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            return (now - created).days
        except (ValueError, AttributeError):
            return 0