"""
Tests for Point Generator functionality
"""

import pytest
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.live.session_hook import SessionHook, SessionTurn
from src.points.point_generator import PointGenerator, WAIPoint


class TestPointGenerator:
    """Test cases for PointGenerator class"""
    
    def test_point_generator_initialization(self):
        """Test that PointGenerator initializes correctly"""
        session_id = "test_session_001"
        generator = PointGenerator(session_id)
        
        assert generator.session_id == session_id
        assert generator.points == []
        assert generator.point_counter == 0
    
    def test_generate_single_point(self):
        """Test generating a single point from a session turn"""
        session_id = "test_session_001"
        hook = SessionHook(session_id)
        generator = PointGenerator(session_id)
        
        # Create a test turn
        turn = hook.capture_turn(
            user_input="Hello, can you help me implement this feature?",
            assistant_response="I'd be happy to help you implement that feature. Let me start by understanding the requirements."
        )
        
        # Generate point
        point = generator.generate_point(turn)
        
        # Verify point structure
        assert isinstance(point, WAIPoint)
        assert point.session_id == session_id
        assert point.turn_id == turn.turn_id
        assert point.point_id == "point_1"
        assert point.engagement_score > 0
        assert point.engagement_score <= 1.0
        assert "session" in point.routing_tags
        assert "turn" in point.routing_tags
        assert isinstance(point.bolo_assessment, dict)
        assert isinstance(point.self_assessment, dict)
    
    def test_multiple_points_generation(self):
        """Test generating multiple points from multiple turns"""
        session_id = "test_session_002"
        hook = SessionHook(session_id)
        generator = PointGenerator(session_id)
        
        # Generate multiple turns
        turn1 = hook.capture_turn(
            user_input="What's the status of the project?",
            assistant_response="The project is currently in the implementation phase."
        )
        
        turn2 = hook.capture_turn(
            user_input="Can you teach me about WAI sessions?",
            assistant_response="WAI sessions provide persistent context across AI interactions."
        )
        
        # Generate points
        point1 = generator.generate_point(turn1)
        point2 = generator.generate_point(turn2)
        
        # Verify both points were created
        assert len(generator.points) == 2
        assert point1.point_id == "point_1"
        assert point2.point_id == "point_2"
        assert point1.turn_id == turn1.turn_id
        assert point2.turn_id == turn2.turn_id
    
    def test_routing_tag_extraction(self):
        """Test that routing tags are correctly extracted"""
        session_id = "test_session_003"
        hook = SessionHook(session_id)
        generator = PointGenerator(session_id)
        
        # Test teaching-related content
        turn = hook.capture_turn(
            user_input="I want to learn about teaching adoption protocols",
            assistant_response="Teaching adoption involves verifying and applying new knowledge."
        )
        
        point = generator.generate_point(turn)
        
        # Should have teaching tag
        assert "teaching" in point.routing_tags
        
        # Should still have base tags
        assert "session" in point.routing_tags
        assert "turn" in point.routing_tags
    
    def test_engagement_scoring(self):
        """Test that engagement scoring works"""
        session_id = "test_session_004"
        hook = SessionHook(session_id)
        generator = PointGenerator(session_id)
        
        # Test with short interaction
        short_turn = hook.capture_turn(
            user_input="Hi",
            assistant_response="Hello"
        )
        
        short_point = generator.generate_point(short_turn)
        
        # Test with long interaction
        long_turn = hook.capture_turn(
            user_input="Can you please help me understand the complex requirements for implementing the taste engine phase 3, including all the various components and their interactions?",
            assistant_response="I'll help you understand the taste engine phase 3 requirements in detail. This involves several key components including session hooks, point generation, BOLO evaluation, engagement tracking, and wakeup brief generation. Each component plays a crucial role in creating a comprehensive real-time learning system that can capture and process session interactions effectively."
        )
        
        long_point = generator.generate_point(long_turn)
        
        # Long interaction should have higher engagement score
        assert long_point.engagement_score > short_point.engagement_score
    
    def test_points_summary(self):
        """Test that points summary is generated correctly"""
        session_id = "test_session_005"
        hook = SessionHook(session_id)
        generator = PointGenerator(session_id)
        
        # Generate a few points
        for i in range(3):
            turn = hook.capture_turn(
                user_input=f"Test input {i}",
                assistant_response=f"Test response {i}"
            )
            generator.generate_point(turn)
        
        summary = generator.get_points_summary()
        
        assert summary["total_points"] == 3
        assert summary["session_id"] == session_id
        assert "avg_engagement" in summary
        assert "routing_tag_counts" in summary
        assert "first_point_time" in summary
        assert "last_point_time" in summary
    
    def test_export_points(self, tmp_path):
        """Test that points can be exported to JSON file"""
        session_id = "test_session_006"
        hook = SessionHook(session_id)
        generator = PointGenerator(session_id)
        
        # Generate a point
        turn = hook.capture_turn(
            user_input="Test export functionality",
            assistant_response="Exporting to JSON file"
        )
        generator.generate_point(turn)
        
        # Export to file
        export_file = tmp_path / "points.json"
        generator.export_points(str(export_file))
        
        # Verify file was created and contains valid JSON
        assert export_file.exists()
        import json
        with open(export_file, 'r') as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["session_id"] == session_id


if __name__ == "__main__":
    pytest.main([__file__])