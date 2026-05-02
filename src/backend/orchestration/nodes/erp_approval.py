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


def build_erp_case_file_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_case_file"):
            return await orchestrator.erp_case_file_node(state)

    return _node


def build_erp_evidence_requirements_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_evidence_requirements"):
            return await orchestrator.erp_evidence_requirements_node(state)

    return _node


def build_erp_evidence_claims_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_evidence_claims"):
            return await orchestrator.erp_evidence_claims_node(state)

    return _node


def build_erp_evidence_sufficiency_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_evidence_sufficiency"):
            return await orchestrator.erp_evidence_sufficiency_node(state)

    return _node


def build_erp_control_matrix_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_control_matrix"):
            return await orchestrator.erp_control_matrix_node(state)

    return _node


def build_erp_case_recommendation_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_case_recommendation"):
            return await orchestrator.erp_case_recommendation_node(state)

    return _node


def build_erp_adversarial_review_node(orchestrator):
    async def _node(state, config=None):
        orchestrator.ensure_graph_bindings(state, config=config)
        with orchestrator.observe_graph_node(state, node_name="erp_adversarial_review"):
            return await orchestrator.erp_adversarial_review_node(state)

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
