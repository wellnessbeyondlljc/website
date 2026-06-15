"""Taste Engine hierarchy model and lookup helpers.

Defines the precedence order and scope resolution for taste profiles
across hub, organization, department, role, individual, and spoke levels.
"""

from typing import Dict, List, Optional, Any
import yaml
from pathlib import Path


class TasteHierarchy:
    """Manages taste profile hierarchy and precedence rules."""
    
    def __init__(self, config_path: str = "config/taste_levels.yaml"):
        """Initialize hierarchy from configuration."""
        self.config_path = Path(config_path)
        self.levels = self._load_hierarchy_config()
        
    def _load_hierarchy_config(self) -> Dict[str, Any]:
        """Load hierarchy configuration from YAML file."""
        if not self.config_path.exists():
            # Default hierarchy if config missing
            return {
                "precedence": [
                    "individual",
                    "role", 
                    "department",
                    "organization",
                    "spoke",
                    "hub"
                ],
                "decay_factor": 0.8,
                "conflict_resolution": "highest_precedence_wins"
            }
        
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def get_precedence_order(self) -> List[str]:
        """Get the ordered list of precedence levels (highest first)."""
        return self.levels.get("precedence", [])
    
    def get_decay_factor(self) -> float:
        """Get the decay factor for inherited taste."""
        return self.levels.get("decay_factor", 0.8)
    
    def resolve_conflict_strategy(self) -> str:
        """Get the conflict resolution strategy."""
        return self.levels.get("conflict_resolution", "highest_precedence_wins")
    
    def scope_precedes(self, scope1: str, scope2: str) -> bool:
        """Check if scope1 has higher precedence than scope2."""
        precedence = self.get_precedence_order()
        try:
            return precedence.index(scope1) < precedence.index(scope2)
        except ValueError:
            return False
    
    def get_effective_scope(self, *scopes: str) -> str:
        """Get the highest precedence scope from the given scopes."""
        precedence = self.get_precedence_order()
        for scope in precedence:
            if scope in scopes:
                return scope
        return "hub"  # default fallback
    
    def validate_scope(self, scope: str) -> bool:
        """Check if a scope name is valid."""
        return scope in self.get_precedence_order()
    
    def get_inheritance_path(self, from_scope: str, to_scope: str) -> List[str]:
        """Get the inheritance path between two scopes."""
        precedence = self.get_precedence_order()
        try:
            from_idx = precedence.index(from_scope)
            to_idx = precedence.index(to_scope)

            if from_idx <= to_idx:
                return []  # No inheritance from higher to lower precedence

            return precedence[from_idx:to_idx+1]
        except ValueError:
            return []


def load_default_hierarchy() -> TasteHierarchy:
    """Return a TasteHierarchy with default configuration."""
    return TasteHierarchy()