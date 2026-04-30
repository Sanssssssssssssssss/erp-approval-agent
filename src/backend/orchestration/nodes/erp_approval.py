from __future__ import annotations


def build_erp_intake_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_intake"):
            return await orchestrator.erp_intake_node(state)

    return _node


def build_erp_context_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_context"):
            return await orchestrator.erp_context_node(state)

    return _node


def build_erp_reasoning_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_reasoning"):
            return await orchestrator.erp_reasoning_node(state)

    return _node


def build_erp_guard_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_guard"):
            return await orchestrator.erp_guard_node(state)

    return _node


def build_erp_hitl_gate_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_hitl_gate"):
            return await orchestrator.erp_hitl_gate_node(state)

    return _node


def build_erp_action_proposal_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_action_proposal"):
            return await orchestrator.erp_action_proposal_node(state)

    return _node


def build_erp_finalize_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_finalize"):
            return await orchestrator.erp_finalize_node(state)

    return _node
