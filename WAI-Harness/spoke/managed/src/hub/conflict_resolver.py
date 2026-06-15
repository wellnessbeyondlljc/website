"""
Taste Engine Phase 3.5 - Conflict Resolver

Detects and records conflicts between hub and spoke taste constraints.
Provides analysis and reporting of collision patterns across the organization.

This component ensures that conflicts are surfaced rather than silently
overwritten, enabling informed decision-making about taste evolution.
"""

import json
import yaml
from typing import Dict, List, Any, Optional, Set, Tuple
from pathlib import Path
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging

from ..profiles.hierarchy import TasteHierarchy, load_default_hierarchy


class ConflictSeverity(Enum):
    """Severity levels for conflicts."""
    LOW = "low"           # Informational, can be automatically resolved
    MEDIUM = "medium"     # Requires attention, may need manual review
    HIGH = "high"         # Critical, blocks normal operation
    BLOCKING = "blocking"  # Must be resolved before continuing


class ConflictType(Enum):
    """Types of conflicts that can occur."""
    VALUE_MISMATCH = "value_mismatch"        # Different values for same constraint
    STRUCTURE_MISMATCH = "structure_mismatch" # Incompatible constraint structures
    DEPENDENCY_CONFLICT = "dependency_conflict" # Conflicting dependencies
    SCOPE_CONFLICT = "scope_conflict"        # Constraint in wrong scope


@dataclass
class ConflictAnalysis:
    """Detailed analysis of a conflict."""
    conflict_id: str
    conflict_type: ConflictType
    severity: ConflictSeverity
    constraint_path: str
    hub_value: Any
    spoke_values: Dict[str, Any]  # spoke_name -> value
    affected_spokes: List[str] = field(default_factory=list)
    detection_context: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    resolution_suggestions: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.conflict_id:
            self.conflict_id = f"conflict-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "conflict_id": self.conflict_id,
            "conflict_type": self.conflict_type.value,
            "severity": self.severity.value,
            "constraint_path": self.constraint_path,
            "hub_value": self.hub_value,
            "spoke_values": self.spoke_values,
            "affected_spokes": self.affected_spokes,
            "detection_context": self.detection_context,
            "created_at": self.created_at,
            "resolution_suggestions": self.resolution_suggestions
        }


@dataclass
class ConflictReport:
    """A report of detected conflicts."""
    report_id: str
    date: str
    total_conflicts: int
    conflicts_by_type: Dict[str, int] = field(default_factory=dict)
    conflicts_by_severity: Dict[str, int] = field(default_factory=dict)
    conflicts: List[ConflictAnalysis] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "report_id": self.report_id,
            "date": self.date,
            "total_conflicts": self.total_conflicts,
            "conflicts_by_type": self.conflicts_by_type,
            "conflicts_by_severity": self.conflicts_by_severity,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "summary": self.summary
        }


class ConflictResolver:
    """Detects and analyzes conflicts between hub and spoke taste constraints."""
    
    def __init__(self, hub_path: Path, hierarchy: Optional[TasteHierarchy] = None):
        self.hub_path = hub_path
        self.hierarchy = hierarchy or load_default_hierarchy()
        self.conflicts_dir = hub_path / "data" / "profiles" / "hub" / "conflicts"
        self.conflicts_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
    
    def detect_conflicts(self, hub_profile: Dict[str, Any],
                        spoke_profiles: Dict[str, Dict[str, Any]]) -> ConflictReport:
        """
        Detect conflicts between hub and spoke profiles.
        
        Args:
            hub_profile: Hub taste profile
            spoke_profiles: Mapping of spoke_name -> spoke taste profile
            
        Returns:
            ConflictReport with detected conflicts
        """
        conflicts = []
        
        # Analyze each spoke profile against the hub
        for spoke_name, spoke_profile in spoke_profiles.items():
            spoke_conflicts = self._analyze_hub_spoke_conflicts(
                hub_profile, spoke_profile, spoke_name
            )
            conflicts.extend(spoke_conflicts)
        
        # Analyze inter-spoke conflicts
        inter_spoke_conflicts = self._analyze_inter_spoke_conflicts(spoke_profiles)
        conflicts.extend(inter_spoke_conflicts)
        
        # Create conflict report
        report = self._create_conflict_report(conflicts)
        
        # Save the report
        self._save_conflict_report(report)
        
        return report
    
    def _analyze_hub_spoke_conflicts(self, hub_profile: Dict[str, Any],
                                   spoke_profile: Dict[str, Any],
                                   spoke_name: str) -> List[ConflictAnalysis]:
        """Analyze conflicts between hub and a specific spoke."""
        conflicts = []
        
        # Get all constraint paths from both profiles
        hub_paths = self._get_all_constraint_paths(hub_profile)
        spoke_paths = self._get_all_constraint_paths(spoke_profile)
        
        # Check for value conflicts on common constraints
        common_paths = hub_paths.intersection(spoke_paths)
        
        for constraint_path in common_paths:
            hub_value = self._get_constraint_value(hub_profile, constraint_path)
            spoke_value = self._get_constraint_value(spoke_profile, constraint_path)
            
            if hub_value != spoke_value:
                # Value mismatch conflict
                conflict = ConflictAnalysis(
                    conflict_type=ConflictType.VALUE_MISMATCH,
                    severity=self._determine_severity(hub_value, spoke_value),
                    constraint_path=constraint_path,
                    hub_value=hub_value,
                    spoke_values={spoke_name: spoke_value},
                    affected_spokes=[spoke_name],
                    resolution_suggestions=self._generate_resolution_suggestions(
                        ConflictType.VALUE_MISMATCH, hub_value, spoke_value
                    )
                )
                conflicts.append(conflict)
        
        return conflicts
    
    def _analyze_inter_spoke_conflicts(self, spoke_profiles: Dict[str, Dict[str, Any]]) -> List[ConflictAnalysis]:
        """Analyze conflicts between different spokes."""
        conflicts = []
        
        # Group constraints by path across spokes
        constraint_map = {}
        
        for spoke_name, spoke_profile in spoke_profiles.items():
            paths = self._get_all_constraint_paths(spoke_profile)
            
            for constraint_path in paths:
                if constraint_path not in constraint_map:
                    constraint_map[constraint_path] = {}
                
                value = self._get_constraint_value(spoke_profile, constraint_path)
                constraint_map[constraint_path][spoke_name] = value
        
        # Find constraints with conflicting values across spokes
        for constraint_path, spoke_values in constraint_map.items():
            unique_values = set(str(v) for v in spoke_values.values())
            
            if len(unique_values) > 1:
                # Inter-spoke conflict
                conflict = ConflictAnalysis(
                    conflict_type=ConflictType.VALUE_MISMATCH,
                    severity=ConflictSeverity.MEDIUM,  # Inter-spoke conflicts are typically medium
                    constraint_path=constraint_path,
                    hub_value=None,  # Not a hub conflict
                    spoke_values=spoke_values,
                    affected_spokes=list(spoke_values.keys()),
                    resolution_suggestions=[
                        "Establish hub-level standard for this constraint",
                        "Allow spoke-level variation if appropriate",
                        "Create spoke-specific variants with clear naming"
                    ]
                )
                conflicts.append(conflict)
        
        return conflicts
    
    def _get_all_constraint_paths(self, profile: Dict[str, Any], 
                                 prefix: str = "") -> Set[str]:
        """Get all constraint paths from a profile."""
        paths = set()
        
        def traverse(obj: Any, current_prefix: str):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_prefix = f"{current_prefix}.{key}" if current_prefix else key
                    if isinstance(value, (str, int, float, bool)):
                        paths.add(new_prefix)
                    elif isinstance(value, dict):
                        traverse(value, new_prefix)
                    elif isinstance(value, list):
                        # Skip lists in constraint paths
                        pass
        
        traverse(profile, prefix)
        return paths
    
    def _get_constraint_value(self, profile: Dict[str, Any], constraint_path: str) -> Any:
        """Get the value of a constraint from a profile."""
        path_parts = constraint_path.split('.')
        current = profile
        
        for part in path_parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        
        return current
    
    def _determine_severity(self, hub_value: Any, spoke_value: Any) -> ConflictSeverity:
        """Determine the severity of a value mismatch conflict."""
        # Simple heuristics for severity determination
        if (isinstance(hub_value, (int, float)) and 
            isinstance(spoke_value, (int, float))):
            # Numeric values - check magnitude of difference
            if hub_value == 0:
                relative_diff = abs(spoke_value)
            else:
                relative_diff = abs(spoke_value - hub_value) / abs(hub_value)
            
            if relative_diff > 0.5:  # More than 50% difference
                return ConflictSeverity.HIGH
            elif relative_diff > 0.2:  # More than 20% difference
                return ConflictSeverity.MEDIUM
            else:
                return ConflictSeverity.LOW
        elif isinstance(hub_value, bool) and isinstance(spoke_value, bool):
            # Boolean conflicts are usually high severity
            return ConflictSeverity.HIGH
        elif isinstance(hub_value, str) and isinstance(spoke_value, str):
            # String conflicts - check if they're fundamentally different
            if hub_value.lower() != spoke_value.lower():
                return ConflictSeverity.MEDIUM
            else:
                return ConflictSeverity.LOW
        else:
            # Type mismatches or complex values
            return ConflictSeverity.HIGH
    
    def _generate_resolution_suggestions(self, conflict_type: ConflictType,
                                      hub_value: Any, spoke_value: Any) -> List[str]:
        """Generate resolution suggestions for a conflict."""
        suggestions = []
        
        if conflict_type == ConflictType.VALUE_MISMATCH:
            suggestions.extend([
                "Adopt hub value for consistency",
                "Elevate spoke value to hub standard",
                "Create exception for this spoke",
                "Define context-specific rules"
            ])
            
            # Add specific suggestions based on value types
            if isinstance(hub_value, (int, float)) and isinstance(spoke_value, (int, float)):
                suggestions.append("Consider compromise value between hub and spoke")
            elif isinstance(hub_value, str) and isinstance(spoke_value, str):
                suggestions.append("Review string formatting and naming conventions")
        
        return suggestions
    
    def _create_conflict_report(self, conflicts: List[ConflictAnalysis]) -> ConflictReport:
        """Create a conflict report from a list of conflicts."""
        report_id = f"conflict-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        today = date.today().isoformat()
        
        # Group conflicts by type and severity
        conflicts_by_type = {}
        conflicts_by_severity = {}
        
        for conflict in conflicts:
            # Count by type
            conflict_type = conflict.conflict_type.value
            conflicts_by_type[conflict_type] = conflicts_by_type.get(conflict_type, 0) + 1
            
            # Count by severity
            severity = conflict.severity.value
            conflicts_by_severity[severity] = conflicts_by_severity.get(severity, 0) + 1
        
        # Generate summary
        summary = {
            "total_conflicts": len(conflicts),
            "unique_constraint_paths": len(set(c.constraint_path for c in conflicts)),
            "total_affected_spokes": len(set(
                spoke for c in conflicts for spoke in c.affected_spokes
            )),
            "high_severity_count": conflicts_by_severity.get("high", 0),
            "blocking_count": conflicts_by_severity.get("blocking", 0)
        }
        
        return ConflictReport(
            report_id=report_id,
            date=today,
            total_conflicts=len(conflicts),
            conflicts_by_type=conflicts_by_type,
            conflicts_by_severity=conflicts_by_severity,
            conflicts=conflicts,
            summary=summary
        )
    
    def _save_conflict_report(self, report: ConflictReport) -> None:
        """Save a conflict report to file."""
        output_file = self.conflicts_dir / f"{report.report_id}.json"
        
        with open(output_file, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
        
        self.logger.info(f"Saved conflict report to {output_file}")
    
    def load_conflict_history(self, days: int = 30) -> List[ConflictReport]:
        """Load conflict reports for the last N days."""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        reports = []
        
        for report_file in self.conflicts_dir.glob("conflict-report-*.json"):
            try:
                with open(report_file, 'r') as f:
                    data = json.load(f)
                
                report_date = date.fromisoformat(data["date"])
                
                if start_date <= report_date <= end_date:
                    report = ConflictReport(
                        report_id=data["report_id"],
                        date=data["date"],
                        total_conflicts=data["total_conflicts"],
                        conflicts_by_type=data["conflicts_by_type"],
                        conflicts_by_severity=data["conflicts_by_severity"],
                        conflicts=[
                            ConflictAnalysis(**c) for c in data["conflicts"]
                        ],
                        summary=data["summary"]
                    )
                    reports.append(report)
            except Exception as e:
                self.logger.error(f"Error loading conflict report from {report_file}: {e}")
        
        # Sort by date
        reports.sort(key=lambda r: r.date)
        
        return reports
    
    def get_conflict_trends(self, days: int = 30) -> Dict[str, Any]:
        """Analyze conflict trends over time."""
        reports = self.load_conflict_history(days)
        
        if not reports:
            return {"error": "No conflict reports found for the specified period"}
        
        trends = {
            "period_days": days,
            "total_reports": len(reports),
            "total_conflicts": sum(r.total_conflicts for r in reports),
            "avg_conflicts_per_report": sum(r.total_conflicts for r in reports) / len(reports),
            "conflict_type_distribution": {},
            "severity_distribution": {},
            "top_conflicting_constraints": {},
            "most_affected_spokes": {}
        }
        
        # Aggregate type distribution
        for report in reports:
            for conflict_type, count in report.conflicts_by_type.items():
                trends["conflict_type_distribution"][conflict_type] = (
                    trends["conflict_type_distribution"].get(conflict_type, 0) + count
                )
        
        # Aggregate severity distribution
        for report in reports:
            for severity, count in report.conflicts_by_severity.items():
                trends["severity_distribution"][severity] = (
                    trends["severity_distribution"].get(severity, 0) + count
                )
        
        # Find top conflicting constraints
        constraint_conflict_counts = {}
        spoke_conflict_counts = {}
        
        for report in reports:
            for conflict in report.conflicts:
                # Count constraint conflicts
                constraint = conflict.constraint_path
                constraint_conflict_counts[constraint] = (
                    constraint_conflict_counts.get(constraint, 0) + 1
                )
                
                # Count spoke conflicts
                for spoke in conflict.affected_spokes:
                    spoke_conflict_counts[spoke] = (
                        spoke_conflict_counts.get(spoke, 0) + 1
                    )
        
        # Get top 10 for each
        trends["top_conflicting_constraints"] = dict(sorted(
            constraint_conflict_counts.items(), 
            key=lambda x: x[1], reverse=True
        )[:10])
        
        trends["most_affected_spokes"] = dict(sorted(
            spoke_conflict_counts.items(), 
            key=lambda x: x[1], reverse=True
        )[:10])
        
        return trends