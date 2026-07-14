import pytest
from src.agents.viral_graph import viral_graph


def test_viral_graph_structure():
    nodes = list(viral_graph.nodes.keys())
    assert "analyze_source" in nodes
    assert "wait_viral_confirm" in nodes
    assert "generate_rewritten_script" in nodes
    assert "wait_script_review" in nodes
    assert "generate_images" in nodes
    assert "wait_image_review" in nodes
    assert "generate_clips_and_voiceover" in nodes
    assert "composite" in nodes


def test_viral_graph_has_no_checkpointer_at_module_level():
    assert viral_graph.checkpointer is None or viral_graph.checkpointer is False


def test_viral_graph_interrupt_count():
    assert len(viral_graph.interrupt_before_nodes) == 3
