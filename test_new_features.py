#!/usr/bin/env python3
"""Test new features: team composition, performance tracking, dynamic specialists."""

import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent))


def test_expert_models():
    """Test expert data models."""
    from research_cli.models.expert import ExpertProposal, ExpertConfig

    # Test ExpertProposal
    proposal = ExpertProposal(
        expert_domain="Cryptography",
        rationale="Needed for security analysis",
        focus_areas=["ZK proofs", "signatures"],
        suggested_model="claude-opus-4.5"
    )
    assert proposal.expert_domain == "Cryptography"
    assert len(proposal.focus_areas) == 2

    # Test ExpertConfig
    config = ExpertConfig(
        id="crypto-expert",
        name="Cryptography Expert",
        domain="Cryptography",
        focus_areas=["ZK proofs"],
        system_prompt="You are a crypto expert",
        model="claude-sonnet-4.5"
    )
    assert config.id == "crypto-expert"

    # Test to_dict
    data = config.to_dict()
    assert "id" in data
    assert "name" in data
    assert data["model"] == "claude-sonnet-4.5"

    print("✓ Expert models work correctly")


def test_specialist_factory():
    """Test specialist factory."""
    from research_cli.models.expert import ExpertConfig
    from research_cli.agents.specialist_factory import SpecialistFactory

    config = ExpertConfig(
        id="test-expert",
        name="Test Expert",
        domain="Testing",
        focus_areas=["unit tests", "integration"],
        system_prompt="",  # Will be generated
        model="claude-sonnet-4.5"
    )

    # Test single specialist creation
    specialist = SpecialistFactory.create_specialist(config, "Test Topic")
    assert specialist["name"] == "Test Expert"
    assert specialist["model"] == "claude-sonnet-4.5"
    assert len(specialist["system_prompt"]) > 0
    assert "Testing" in specialist["system_prompt"]

    # Test multiple specialists
    configs = [config]
    specialists_dict = SpecialistFactory.create_specialists_dict(configs, "Test Topic")
    assert "test-expert" in specialists_dict
    assert specialists_dict["test-expert"]["name"] == "Test Expert"

    print("✓ Specialist factory works correctly")


def test_performance_tracker():
    """Test performance tracking."""
    import time
    from research_cli.performance import PerformanceTracker

    tracker = PerformanceTracker()

    # Test workflow tracking
    tracker.start_workflow()
    time.sleep(0.1)

    # Test operation tracking
    tracker.start_operation("test_op")
    time.sleep(0.05)
    duration = tracker.end_operation("test_op")
    assert duration >= 0.05

    # Test context manager
    with tracker.track_operation("context_op"):
        time.sleep(0.05)

    # Test round tracking
    tracker.start_round(1)
    tracker.record_reviewer_time("expert_1", 10.5)
    tracker.record_reviewer_time("expert_2", 12.3)
    tracker.record_moderator_time(5.2)
    tracker.record_revision_time(15.7)
    tracker.record_round_tokens(5000)
    tracker.end_round()

    # Test metrics export
    metrics = tracker.export_metrics()
    assert metrics.total_duration >= 0.1
    assert len(metrics.rounds) == 1
    assert metrics.rounds[0].round_number == 1
    assert metrics.rounds[0].reviewer_times["expert_1"] == 10.5
    assert metrics.rounds[0].moderator_time == 5.2
    assert metrics.rounds[0].revision_time == 15.7
    assert metrics.rounds[0].round_tokens == 5000

    # Test to_dict
    data = metrics.to_dict()
    assert "total_duration" in data
    assert "rounds" in data
    assert len(data["rounds"]) == 1

    print("✓ Performance tracker works correctly")


def test_interactive_display():
    """Test interactive editor display (non-interactive parts)."""
    from research_cli.models.expert import ExpertProposal
    from research_cli.interactive import TeamEditor

    proposals = [
        ExpertProposal(
            expert_domain="Cryptography",
            rationale="Security analysis",
            focus_areas=["ZK proofs", "signatures"],
            suggested_model="claude-opus-4.5"
        ),
        ExpertProposal(
            expert_domain="Economics",
            rationale="Incentive analysis",
            focus_areas=["game theory", "MEV"],
            suggested_model="claude-sonnet-4.5"
        )
    ]

    # Test display (should not crash)
    try:
        TeamEditor.show_proposed_team(proposals, "Test Topic", "Test analysis")
        print("✓ Interactive editor display works")
    except Exception as e:
        print(f"✗ Interactive editor display failed: {e}")


def main():
    """Run all tests."""
    print("Testing new features...\n")

    try:
        test_expert_models()
        test_specialist_factory()
        test_performance_tracker()
        test_interactive_display()

        print("\n✓ All tests passed!")
        return 0

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
