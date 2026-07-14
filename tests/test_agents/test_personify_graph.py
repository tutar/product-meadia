import pytest
from src.agents.personify_graph import personify_graph


def test_personify_graph_structure():
    nodes = list(personify_graph.nodes.keys())
    assert "generate_character" in nodes
    assert "wait_character_review" in nodes
    assert "generate_script" in nodes
    assert "wait_script_review" in nodes
    assert "generate_tts_and_lipsync" in nodes
    assert "composite" in nodes


def test_personify_graph_has_no_checkpointer_at_module_level():
    assert personify_graph.checkpointer is None or personify_graph.checkpointer is False


def test_personify_graph_interrupt_count():
    assert len(personify_graph.interrupt_before_nodes) == 2
