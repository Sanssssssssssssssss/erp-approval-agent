from __future__ import annotations

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from langgraph.types import Command, interrupt

from src.backend.capabilities.invocation import (
    CapabilityRuntimeContext,
    GovernedCapabilityTool,
    activate_capability_runtime_context,
    invoke_capability,
    reset_capability_runtime_context,
)
from src.backend.capabilities.types import CapabilityResult
from src.backend.context import ContextAssembler, ContextWriter
from src.backend.context.models import ContextAssembly, ContextModelCallSnapshot, ContextTurnSnapshot
from src.backend.context.store import context_store
from src.backend.decision.skill_gate import SkillDecision, skill_instruction
from src.backend.domains.erp_approval import (
    ApprovalActionProposalBundle,
    ApprovalActionValidationResult,
    ApprovalActionProposalRepository,
    ApprovalContextBundle,
    ApprovalGuardResult,
    ApprovalRecommendation,
    ApprovalRequest,
    ApprovalTraceRepository,
    ERP_CONNECTOR_NON_ACTION_STATEMENT,
    ErpContextQuery,
    ErpReadResult,
    build_action_proposals,
    build_connector_registry_from_env,
    build_context_bundle_from_records,
    build_proposal_records_from_state,
    build_trace_record_from_state,
    default_proposal_ledger_path,
    default_trace_path,
    guard_recommendation,
    parse_approval_request,
    parse_recommendation,
    render_action_proposals,
    render_recommendation,
    read_request_from_context_query,
    validate_action_proposals,
    trace_id_from_state,
)
from src.backend.domains.erp_approval.prompts import ERP_INTAKE_SYSTEM_PROMPT, ERP_REASONING_SYSTEM_PROMPT
from src.backend.observability.otel_spans import set_span_attributes, with_observation
from src.backend.observability.types import AnswerRecord, RetrievalRecord, RouteDecisionRecord, SkillDecisionRecord, ToolCallRecord
from src.backend.orchestration.checkpointing import PendingHitlRequest, checkpoint_store
from src.backend.orchestration.compiler import compile_harness_orchestration_graph
from src.backend.orchestration.recovery import build_recovery_fallback_answer, build_recovery_hitl_request, extract_latest_failed_capability
from src.backend.orchestration.recovery_policies import select_recovery_action
from src.backend.orchestration.state import GraphState, create_initial_graph_state
from src.backend.runtime.graders import KnowledgeAnswerGrader

if TYPE_CHECKING:  # pragma: no cover
    from src.backend.decision.execution_strategy import ExecutionStrategy
    from src.backend.decision.lightweight_router import RoutingDecision
    from src.backend.runtime.agent_manager import AgentManager
    from src.backend.runtime.runtime import HarnessRuntime, RuntimeRunHandle


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(block.get("text", "")) for block in content if isinstance(block, dict) and block.get("type") == "text")
    return str(content or "")


_EXPLICIT_MCP_PATTERNS = (
    re.compile(r"\bfilesystem mcp\b", re.IGNORECASE),
    re.compile(r"\bmcp filesystem\b", re.IGNORECASE),
)
_EXPLICIT_WEB_MCP_PATTERNS = (
    re.compile(r"\bweb mcp\b", re.IGNORECASE),
    re.compile(r"\bdocument fetch mcp\b", re.IGNORECASE),
)
_REPEATED_MCP_PATTERNS = (
    re.compile(r"\b(?:twice|three times|repeat(?:ed)?|again|\d+\s+times)\b", re.IGNORECASE),
    re.compile(r"(?:两次|三次|重复|再来一次)"),
)
_READ_PATH_PATTERNS = (
    re.compile(r"\bread\s+([A-Za-z0-9_./\\-]+\.[A-Za-z0-9_]+)", re.IGNORECASE),
    re.compile(r"\bopen\s+([A-Za-z0-9_./\\-]+\.[A-Za-z0-9_]+)", re.IGNORECASE),
)
_LIST_PATH_PATTERNS = (
    re.compile(r"\blist\s+([A-Za-z0-9_./\\-]+)", re.IGNORECASE),
    re.compile(r"\bshow\s+([A-Za-z0-9_./\\-]+)", re.IGNORECASE),
)
_FETCH_URL_PATTERNS = (
    re.compile(r"\bfetch\s+(https?://[^\s]+)", re.IGNORECASE),
    re.compile(r"\bread\s+(https?://[^\s]+)", re.IGNORECASE),
    re.compile(r"\bvisit\s+(https?://[^\s]+)", re.IGNORECASE),
)
_EXPLICIT_CAPABILITY_IDS = {"mcp_filesystem_read_file", "mcp_filesystem_list_directory", "mcp_web_fetch_url"}
ERP_RECOMMENDATION_REVIEW_CAPABILITY_ID = "erp_approval_recommendation_review"
ERP_RECOMMENDATION_REVIEW_DISPLAY_NAME = "ERP approval recommendation review"
ERP_RECOMMENDATION_REVIEW_NON_ACTION = (
    "This HITL review does not approve, reject, pay, onboard, sign, or update any ERP object."
)
ERP_NO_ACTION_EXECUTED_STATEMENT = "No ERP approval, rejection, payment, supplier, contract, or budget action was executed."


@dataclass
class _ExecutionBindings:
    runtime: "HarnessRuntime"
    handle: "RuntimeRunHandle"
    context: CapabilityRuntimeContext


_CURRENT_EXECUTION_BINDINGS: ContextVar[_ExecutionBindings | None] = ContextVar("ragclaw_execution_bindings", default=None)


class HarnessLangGraphOrchestrator:
    def __init__(
        self,
        agent_manager: "AgentManager",
        *,
        execution_support,
        knowledge_grader: KnowledgeAnswerGrader | None = None,
        resume_checkpoint_id: str = "",
        resume_thread_id: str = "",
        resume_source: str = "",
        resume_payload: dict[str, Any] | None = None,
        include_checkpointer: bool = True,
    ) -> None:
        self._agent = agent_manager
        self._execution = execution_support
        self._knowledge_grader = knowledge_grader or KnowledgeAnswerGrader(agent_manager)
        self._graph = compile_harness_orchestration_graph(self, include_checkpointer=include_checkpointer)
        self._context_assembler = ContextAssembler(base_dir=self._agent.base_dir)
        self._context_writer = ContextWriter(base_dir=self._agent.base_dir)
        self._erp_connector_registry = build_connector_registry_from_env(self._agent.base_dir)
        self._erp_trace_repository = ApprovalTraceRepository(default_trace_path(self._agent.base_dir))
        self._erp_proposal_repository = ApprovalActionProposalRepository(default_proposal_ledger_path(self._agent.base_dir))
        self._resume_checkpoint_id = str(resume_checkpoint_id or "")
        self._resume_thread_id = str(resume_thread_id or "")
        self._resume_source = str(resume_source or "")
        self._resume_payload = dict(resume_payload or {})

    @property
    def graph(self):
        return self._graph

    async def run(self, runtime: "HarnessRuntime", handle: "RuntimeRunHandle", *, message: str, history: list[dict[str, Any]]) -> GraphState:
        context = CapabilityRuntimeContext(
            runtime=runtime,
            handle=handle,
            registry=self._agent.get_capability_registry(),
            governor=runtime.governor_for(handle.run_id),
            approval_overrides=set(),
        )
        token = _CURRENT_EXECUTION_BINDINGS.set(_ExecutionBindings(runtime=runtime, handle=handle, context=context))
        capability_token = activate_capability_runtime_context(context)
        try:
            thread_id = self._thread_id_for(handle)
            if self._resume_checkpoint_id:
                await self._emit_resume_events(runtime, handle, thread_id)
                resume_input: Any = None
                if self._resume_payload:
                    resume_input = Command(resume=dict(self._resume_payload))
                result = await self._graph.ainvoke(
                    resume_input,
                    config={
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_id": self._resume_checkpoint_id,
                        }
                    },
                )
            else:
                result = await self._graph.ainvoke(
                    create_initial_graph_state(
                        run_id=handle.run_id,
                        session_id=getattr(handle.metadata, "session_id", None),
                        thread_id=thread_id,
                        user_message=message,
                        history=history,
                    ),
                    config={"configurable": {"thread_id": thread_id}},
                )
            await self._emit_hitl_interrupt_if_needed(runtime, handle, thread_id, result)
            await self._emit_checkpoint_created(runtime, handle, thread_id)
            return result
        finally:
            reset_capability_runtime_context(capability_token)
            _CURRENT_EXECUTION_BINDINGS.reset(token)

    def _bindings_or_raise(self) -> _ExecutionBindings:
        bindings = _CURRENT_EXECUTION_BINDINGS.get()
        if bindings is None:
            bindings = getattr(self, "_bindings", None)
        if bindings is None:
            raise RuntimeError("orchestration bindings are not active")
        return bindings

    def _studio_configurable(self, config: Any | None) -> dict[str, Any]:
        if isinstance(config, dict):
            return dict(config.get("configurable", {}) or {})
        if config is None:
            return {}
        getter = getattr(config, "get", None)
        if callable(getter):
            return dict(getter("configurable", {}) or {})
        return {}

    def _ensure_studio_bindings(self, state: GraphState, *, config: Any | None = None) -> dict[str, Any]:
        if _CURRENT_EXECUTION_BINDINGS.get() is not None or getattr(self, "_bindings", None) is not None:
            return {}

        runtime = self._agent.get_harness_runtime()
        configurable = self._studio_configurable(config)
        normalized_inputs = self._normalized_input_fields(state)
        checkpoint_meta = dict(state.get("checkpoint_meta", {}) or {})
        session_id = state.get("session_id") or configurable.get("session_id")
        checkpoint_id = str(configurable.get("checkpoint_id", "") or checkpoint_meta.get("checkpoint_id", "") or "")
        resume_source = str(configurable.get("resume_source", "") or checkpoint_meta.get("resume_source", "") or "")
        run_status = str(checkpoint_meta.get("run_status", "") or ("resumed" if checkpoint_id else "fresh"))
        user_message = str(
            normalized_inputs.get("user_message", "")
            or state.get("user_message", "")
            or configurable.get("user_message", "")
            or ""
        )
        thread_id = str(
            state.get("thread_id", "")
            or configurable.get("thread_id", "")
            or checkpoint_store.thread_id_for(session_id=session_id, run_id=str(state.get("run_id", "") or "studio"))
        )
        handle = runtime.begin_run(
            user_message=user_message,
            session_id=str(session_id) if session_id is not None else None,
            source="langsmith_studio",
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            resume_source=resume_source,
            run_status=run_status,
            orchestration_engine="langgraph",
        )
        context = CapabilityRuntimeContext(
            runtime=runtime,
            handle=handle,
            registry=self._agent.get_capability_registry(),
            governor=runtime.governor_for(handle.run_id),
            approval_overrides=set(),
        )
        _CURRENT_EXECUTION_BINDINGS.set(_ExecutionBindings(runtime=runtime, handle=handle, context=context))
        activate_capability_runtime_context(context)
        return {
            "run_id": handle.run_id,
            "session_id": getattr(handle.metadata, "session_id", None),
            "thread_id": thread_id,
            "studio_managed_run": True,
            "checkpoint_meta": {
                **checkpoint_meta,
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "resume_source": resume_source,
                "run_status": run_status,
                "orchestration_engine": "langgraph",
                "updated_at": runtime.now(),
            },
        }

    def ensure_graph_bindings(self, state: GraphState, *, config: Any | None = None) -> dict[str, Any]:
        return self._ensure_studio_bindings(state, config=config)

    def _otel_state_attributes(self, state: GraphState, *, path_type: str = "", **extra: Any) -> dict[str, Any]:
        meta = self._run_context_meta(state)
        resolved_path_type = path_type or str(state.get("path_kind", "") or "")
        return {
            "run_id": meta["run_id"],
            "thread_id": meta["thread_id"],
            "session_id": meta["session_id"],
            "path_type": resolved_path_type,
            "context_path_type": resolved_path_type,
            "checkpoint_id": meta["checkpoint_id"] or None,
            "resume_source": meta["resume_source"] or None,
            "orchestration_engine": meta["orchestration_engine"],
            **extra,
        }

    @contextmanager
    def observe_graph_node(self, state: GraphState, *, node_name: str) -> Any:
        with with_observation(
            "graph.node",
            tracer_name="ragclaw.orchestration",
            attributes=self._otel_state_attributes(
                state,
                node_name=node_name,
                run_status=str(dict(state.get("checkpoint_meta", {}) or {}).get("run_status", "") or ""),
            ),
        ) as span:
            yield span

    def _normalized_history_message(self, item: Any) -> dict[str, str] | None:
        payload: dict[str, Any] | None = None
        if isinstance(item, dict):
            payload = dict(item)
        else:
            model_dump = getattr(item, "model_dump", None)
            if callable(model_dump):
                dumped = model_dump()
                if isinstance(dumped, dict):
                    payload = dict(dumped)
            if payload is None:
                raw_content = getattr(item, "content", None)
                raw_type = getattr(item, "type", None)
                raw_role = getattr(item, "role", None)
                if raw_content is not None or raw_type is not None or raw_role is not None:
                    payload = {
                        "content": raw_content,
                        "type": raw_type,
                        "role": raw_role,
                    }
        if payload is None:
            return None

        nested_payload = payload.get("kwargs") or payload.get("data") or payload.get("message")
        if isinstance(nested_payload, dict):
            merged_payload = dict(nested_payload)
            merged_payload.update({key: value for key, value in payload.items() if value is not None})
            payload = merged_payload

        role = str(payload.get("role", "") or payload.get("type", "") or "").strip().lower()
        if role in {"human"}:
            role = "user"
        if role in {"ai"}:
            role = "assistant"
        if not role:
            return None
        content = _stringify_content(payload.get("content", payload.get("text", ""))).strip()
        if not content:
            return None
        return {"role": role, "content": content}

    def _append_user_message(self, messages: list[dict[str, str]], user_message: str) -> list[dict[str, str]]:
        normalized = str(user_message or "").strip()
        if normalized:
            messages.append({"role": "user", "content": normalized})
        return messages

    def _studio_input_messages(self, state: GraphState) -> list[dict[str, str]]:
        normalized = self._normalized_input_fields(state)
        messages = list(normalized["history"])
        return self._append_user_message(messages, normalized["user_message"])

    def _studio_output_messages(self, state: GraphState) -> list[dict[str, str]]:
        final_answer = str(state.get("final_answer", "") or "").strip()
        if final_answer:
            return [{"role": "assistant", "content": final_answer}]
        recovery_action = str(state.get("recovery_action", "") or "").strip()
        if recovery_action:
            return [{"role": "assistant", "content": f"[{recovery_action}]"}]
        approval_decision = str(state.get("approval_decision", "") or "").strip()
        if approval_decision:
            return [{"role": "assistant", "content": f"[HITL {approval_decision}]"}]
        return self._studio_input_messages(state)

    def _studio_summary_fields(self, state: GraphState) -> dict[str, Any]:
        user_message = self._user_message(state)
        final_answer = str(state.get("final_answer", "") or "").strip()
        output_preview = final_answer or str(state.get("recovery_action", "") or state.get("approval_decision", "") or "").strip()
        return {
            "messages": self._studio_output_messages(state),
            "input_preview": user_message,
            "output_preview": output_preview,
        }

    def _normalized_input_fields(self, state: GraphState) -> dict[str, Any]:
        explicit_user_message = str(state.get("user_message", "") or state.get("message", "") or "").strip()
        raw_history = state.get("history")
        if isinstance(raw_history, list):
            history = [item for item in (self._normalized_history_message(entry) for entry in raw_history) if item is not None]
        else:
            history = []

        if not history:
            raw_messages = state.get("messages")
            if isinstance(raw_messages, list):
                normalized_messages = [
                    item
                    for item in (self._normalized_history_message(entry) for entry in raw_messages)
                    if item is not None
                ]
                if normalized_messages:
                    if not explicit_user_message:
                        for index in range(len(normalized_messages) - 1, -1, -1):
                            candidate = normalized_messages[index]
                            if candidate["role"] == "user":
                                explicit_user_message = candidate["content"].strip()
                                history = normalized_messages[:index]
                                break
                    if not history:
                        history = normalized_messages

        if explicit_user_message:
            if history and history[-1]["role"] == "user" and history[-1]["content"].strip() == explicit_user_message:
                history = history[:-1]
        elif history:
            last_item = history[-1]
            if last_item["role"] == "user":
                explicit_user_message = last_item["content"].strip()
                history = history[:-1]

        return {
            "user_message": explicit_user_message,
            "history": history,
            "augmented_history": list(history),
        }

    def _user_message(self, state: GraphState) -> str:
        return str(state.get("user_message", "") or state.get("message", "") or "").strip()

    async def bootstrap_node(self, state: GraphState, *, config: Any | None = None) -> dict[str, Any]:
        studio_updates = self._ensure_studio_bindings(state, config=config)
        bindings = self._bindings_or_raise()
        normalized_inputs = self._normalized_input_fields(state)
        resolved_run_id = str(studio_updates.get("run_id", state.get("run_id", "") or bindings.handle.run_id) or bindings.handle.run_id)
        resolved_session_id = studio_updates.get("session_id", state.get("session_id", getattr(bindings.handle.metadata, "session_id", None)))
        resolved_thread_id = str(
            studio_updates.get("thread_id", state.get("thread_id", "") or getattr(bindings.handle.metadata, "thread_id", "") or self._thread_id_for(bindings.handle))
        )
        resolved_studio_managed_run = bool(
            studio_updates.get("studio_managed_run", state.get("studio_managed_run", False) or getattr(bindings.handle.metadata, "source", "") == "langsmith_studio")
        )
        checkpoint_meta = {
            **dict(state.get("checkpoint_meta", {}) or {}),
            **dict(studio_updates.get("checkpoint_meta", {}) or {}),
            "thread_id": resolved_thread_id,
            "checkpoint_id": self._resume_checkpoint_id or str(state.get("checkpoint_meta", {}).get("checkpoint_id", "") or ""),
            "resume_source": self._resume_source or str(state.get("checkpoint_meta", {}).get("resume_source", "") or ""),
            "run_status": "resumed" if self._resume_checkpoint_id else str(state.get("checkpoint_meta", {}).get("run_status", "") or "fresh"),
            "updated_at": bindings.runtime.now(),
        }
        base_state = {
            **dict(state),
            **dict(studio_updates),
            **normalized_inputs,
            "checkpoint_meta": checkpoint_meta,
            "rag_mode": self._agent._runtime_rag_mode(),
            "governor_snapshot": bindings.runtime.governor_for(bindings.handle.run_id).snapshot(),
            "turn_id": self._current_turn_id(state),
        }
        _payload, context_updates = self._write_context_snapshot(
            state=state,
            result=base_state,
            turn_id=base_state["turn_id"],
        )
        return {
            "run_id": resolved_run_id,
            "session_id": resolved_session_id,
            "thread_id": resolved_thread_id,
            "studio_managed_run": resolved_studio_managed_run,
            "messages": self._studio_input_messages({**dict(state), **normalized_inputs}),
            "input_preview": normalized_inputs["user_message"],
            "user_message": normalized_inputs["user_message"],
            "history": list(normalized_inputs["history"]),
            "augmented_history": list(normalized_inputs["augmented_history"]),
            "rag_mode": self._agent._runtime_rag_mode(),
            "governor_snapshot": bindings.runtime.governor_for(bindings.handle.run_id).snapshot(),
            "checkpoint_meta": checkpoint_meta,
            **context_updates,
        }

    async def route_node(self, state: GraphState) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        route_context = self._context_assembler.assemble(path_kind="direct_answer", state=state, call_site="route")
        turn_id = self._current_turn_id(state)
        route_call_id = self._record_model_call_snapshot(
            state=state,
            assembly=route_context,
            call_site="route",
            call_type="router_call",
            turn_id=turn_id,
        )
        strategy, decision = await self._agent.resolve_routing(self._user_message(state), list(route_context.history_messages))
        await bindings.runtime.emit(
            bindings.handle,
            "route.decided",
            RouteDecisionRecord(
                intent=decision.intent,
                needs_tools=decision.needs_tools,
                needs_retrieval=decision.needs_retrieval,
                allowed_tools=tuple(decision.allowed_tools),
                confidence=decision.confidence,
                reason_short=decision.reason_short,
                source=decision.source,
                subtype=decision.subtype,
                ambiguity_flags=tuple(decision.ambiguity_flags),
                escalated=decision.escalated,
                model_name=decision.model_name,
            ).to_dict(),
        )
        return {
            "execution_strategy": strategy,
            "route_decision": decision,
            "path_kind": self._path_kind_from_decision(decision),
            "turn_id": turn_id,
            "context_call_ids": self._context_call_ids(state, route_call_id),
            "selected_memory_ids": list(route_context.decision.selected_memory_ids),
            "selected_artifact_ids": list(route_context.decision.selected_artifact_ids),
            "selected_evidence_ids": list(route_context.decision.selected_evidence_ids),
            "selected_conversation_ids": list(route_context.decision.selected_conversation_ids),
        }

    async def skill_node(self, state: GraphState) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        strategy = state.get("execution_strategy")
        decision = state.get("route_decision")
        if strategy is None or decision is None:
            return {}
        skill_context = self._context_assembler.assemble(
            path_kind=self._path_kind_from_decision(decision),
            state=state,
            call_site="skill",
        )
        turn_id = self._current_turn_id(state)
        skill_call_id = self._record_model_call_snapshot(
            state=state,
            assembly=skill_context,
            call_site="skill",
            call_type="capability_selection_call",
            turn_id=turn_id,
        )
        user_message = self._user_message(state)
        skill = self._agent.decide_skill(user_message, list(skill_context.history_messages), strategy, decision)
        if skill.use_skill:
            await self._activate_skill_capability(message=user_message, routing_decision=decision, skill_decision=skill)
        await bindings.runtime.emit(
            bindings.handle,
            "skill.decided",
            SkillDecisionRecord(
                use_skill=skill.use_skill,
                skill_name=skill.skill_name,
                confidence=skill.confidence,
                reason_short=skill.reason_short,
            ).to_dict(),
        )
        result = {
            "skill_decision": skill,
            "turn_id": turn_id,
            "context_call_ids": self._context_call_ids(state, skill_call_id),
            "selected_memory_ids": list(skill_context.decision.selected_memory_ids),
            "selected_artifact_ids": list(skill_context.decision.selected_artifact_ids),
            "selected_evidence_ids": list(skill_context.decision.selected_evidence_ids),
            "selected_conversation_ids": list(skill_context.decision.selected_conversation_ids),
        }
        _payload, updates = self._write_context_snapshot(state=state, result=result, assembly=skill_context, turn_id=turn_id, call_ids=result["context_call_ids"])
        return {**result, **updates}

    async def memory_retrieval_node(self, state: GraphState) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        with with_observation(
            "retrieval",
            tracer_name="ragclaw.orchestration",
            attributes=self._otel_state_attributes(state, path_type="direct_answer", retrieval_kind="memory"),
        ) as span:
            strategy = state.get("execution_strategy")
            if not state.get("rag_mode") or strategy is None or not strategy.allow_retrieval:
                result = {"memory_retrieval": [], "turn_id": self._current_turn_id(state)}
                _payload, updates = self._write_context_snapshot(state=state, result=result, turn_id=result["turn_id"])
                return {"memory_retrieval": [], **updates}
            await bindings.runtime.emit(bindings.handle, "retrieval.started", {"kind": "memory", "stage": "memory", "title": "Memory retrieval", "message": ""})
            retrievals = self._memory_retrieve(self._user_message(state))
            set_span_attributes(span, {"retrieval_count": len(retrievals)})
            if not retrievals:
                result = {"memory_retrieval": [], "turn_id": self._current_turn_id(state)}
                _payload, updates = self._write_context_snapshot(state=state, result=result, turn_id=result["turn_id"])
                return {"memory_retrieval": [], **updates}
            step = self._agent._format_memory_retrieval_step(retrievals)
            await bindings.runtime.emit(
                bindings.handle,
                "retrieval.completed",
                RetrievalRecord(
                    kind=step["kind"],
                    stage=step["stage"],
                    title=step["title"],
                    message=step["message"],
                    results=tuple(self._agent._harness_retrieval_evidence_records(step["results"])),
                ).to_dict(),
            )
            result = {
                "memory_retrieval": retrievals,
                "turn_id": self._current_turn_id(state),
            }
            _payload, updates = self._write_context_snapshot(
                state=state,
                result=result,
                turn_id=result["turn_id"],
            )
            return {"memory_retrieval": retrievals, **updates}

    async def direct_answer_node(self, state: GraphState) -> dict[str, Any]:
        strategy = state.get("execution_strategy")
        assembly = self._context_assembler.assemble(path_kind="direct_answer", state=state, call_site="direct_answer")
        turn_id = self._current_turn_id(state)
        call_type = "resume_after_hitl_call" if assembly.path_kind == "resumed_hitl" else "final_answer_call"
        answer_call_id = self._record_model_call_snapshot(
            state=state,
            assembly=assembly,
            call_site="direct_answer",
            call_type=call_type,
            turn_id=turn_id,
        )
        call_ids = self._context_call_ids(state, answer_call_id)
        messages = list(assembly.history_messages)
        messages = self._append_user_message(messages, self._user_message(state))
        extra_instructions = list(assembly.extra_instructions)
        if strategy is not None:
            extra_instructions.extend(strategy.to_instructions())
        answer, usage = await self._stream_model_answer(
            messages,
            extra_instructions=extra_instructions or None,
            path_type=assembly.path_kind,
        )
        result = {
            "final_answer": answer,
            "answer_usage": usage,
            "answer_finalized": True,
            "answer_segments": [answer] if answer else [],
            "turn_id": turn_id,
            "context_call_ids": call_ids,
        }
        final_state, updates = self._write_context_snapshot(
            state=state,
            result=result,
            assembly=assembly,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        self._record_post_turn_snapshot(
            state=final_state,
            assembly=assembly,
            call_site="direct_answer",
            model_invoked=True,
            updates=updates,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        return {**result, **updates}

    async def knowledge_retrieval_node(self, state: GraphState) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        with with_observation(
            "retrieval",
            tracer_name="ragclaw.orchestration",
            attributes=self._otel_state_attributes(state, path_type="knowledge_qa", retrieval_kind="knowledge"),
        ) as span:
            await bindings.runtime.emit(bindings.handle, "retrieval.started", {"kind": "knowledge", "stage": "knowledge", "title": "Knowledge retrieval", "message": ""})
            result = None
            async for event in self._knowledge_astream(self._user_message(state)):
                if event.get("type") == "orchestrated_result":
                    result = event["result"]
            if result is not None:
                set_span_attributes(span, {"retrieval_status": getattr(result, "status", ""), "retrieval_reason": getattr(result, "reason", "")})
                for step in result.steps:
                    await bindings.runtime.emit(
                        bindings.handle,
                        "retrieval.completed",
                        RetrievalRecord(
                            kind=step.kind,
                            stage=step.stage,
                            title=step.title,
                            message=step.message,
                            results=tuple(self._agent._harness_retrieval_evidence_records([item.to_dict() for item in step.results])),
                            status=getattr(result, "status", ""),
                            reason=getattr(result, "reason", ""),
                            strategy=str(getattr(result, "strategy", "") or ""),
                            diagnostics=dict(getattr(result, "diagnostics", {}) or {}),
                        ).to_dict(),
                    )
            result_payload = {
                "knowledge_retrieval": result,
                "turn_id": self._current_turn_id(state),
            }
            _payload, updates = self._write_context_snapshot(
                state=state,
                result=result_payload,
                turn_id=result_payload["turn_id"],
            )
            return {"knowledge_retrieval": result, **updates}

    async def knowledge_synthesis_node(self, state: GraphState) -> dict[str, Any]:
        result = state.get("knowledge_retrieval")
        assembly = self._context_assembler.assemble(path_kind="knowledge_qa", state=state, call_site="knowledge_synthesis")
        turn_id = self._current_turn_id(state)
        call_id = self._record_model_call_snapshot(
            state=state,
            assembly=assembly,
            call_site="knowledge_synthesis",
            call_type="knowledge_synthesis_call",
            turn_id=turn_id,
        )
        call_ids = self._context_call_ids(state, call_id)
        messages = list(assembly.history_messages)
        messages = self._append_user_message(messages, self._user_message(state))
        extra_instructions = list(assembly.extra_instructions)
        if result:
            extra_instructions.extend(self._agent._knowledge_answer_instructions(result))
        answer, usage = await self._stream_model_answer(
            messages,
            extra_instructions=extra_instructions or None,
            system_prompt_override=self._agent._knowledge_system_prompt(),
            stream_deltas=False,
            path_type=assembly.path_kind,
        )
        result_payload = {
            "final_answer": answer,
            "answer_usage": usage,
            "turn_id": turn_id,
            "context_call_ids": call_ids,
            "selected_memory_ids": list(assembly.decision.selected_memory_ids),
            "selected_artifact_ids": list(assembly.decision.selected_artifact_ids),
            "selected_evidence_ids": list(assembly.decision.selected_evidence_ids),
            "selected_conversation_ids": list(assembly.decision.selected_conversation_ids),
        }
        _payload, updates = self._write_context_snapshot(
            state=state,
            result=result_payload,
            assembly=assembly,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        return {**result_payload, **updates}

    async def knowledge_guard_node(self, state: GraphState) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        result = state.get("knowledge_retrieval")
        answer = str(state.get("final_answer", "") or "")
        guard_result = None
        if result is not None:
            graded = self._knowledge_grader.grade(answer, result)
            answer = graded.final_answer
            guard_result = graded.guard_result
            if guard_result is not None:
                await bindings.runtime.emit(bindings.handle, "guard.failed", guard_result.to_dict())
        await self._emit_final_answer(answer, usage=state.get("answer_usage"))
        assembly = self._context_assembler.assemble(path_kind="knowledge_qa", state=state, call_site="knowledge_synthesis")
        turn_id = self._current_turn_id(state)
        call_ids = self._context_call_ids(state)
        result_payload = {
            "final_answer": answer,
            "guard_result": guard_result,
            "answer_finalized": True,
            "answer_segments": [answer] if answer else [],
            "turn_id": turn_id,
            "context_call_ids": call_ids,
        }
        final_state, updates = self._write_context_snapshot(
            state=state,
            result=result_payload,
            assembly=assembly,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        self._record_post_turn_snapshot(
            state=final_state,
            assembly=assembly,
            call_site="knowledge_synthesis",
            model_invoked=True,
            updates=updates,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        return {**result_payload, **updates}

    async def erp_intake_node(self, state: GraphState) -> dict[str, Any]:
        assembly = self._context_assembler.assemble(path_kind="erp_approval", state=state, call_site="erp_intake")
        turn_id = self._current_turn_id(state)
        call_id = self._record_model_call_snapshot(
            state=state,
            assembly=assembly,
            call_site="erp_intake",
            call_type="erp_intake_call",
            turn_id=turn_id,
        )
        call_ids = self._context_call_ids(state, call_id)
        messages = list(assembly.history_messages)
        messages = self._append_user_message(messages, self._user_message(state))
        try:
            raw_request, _usage = await self._stream_model_answer(
                messages,
                extra_instructions=list(assembly.extra_instructions) or None,
                system_prompt_override=ERP_INTAKE_SYSTEM_PROMPT,
                stream_deltas=False,
                path_type=assembly.path_kind,
            )
        except Exception:
            raw_request = ""
        request = parse_approval_request(raw_request, self._user_message(state))
        result = {
            "erp_request": self._model_dump(request),
            "path_kind": "erp_approval",
            "turn_id": turn_id,
            "context_call_ids": call_ids,
        }
        _payload, updates = self._write_context_snapshot(
            state=state,
            result=result,
            assembly=assembly,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        return {**result, **updates}

    async def erp_context_node(self, state: GraphState) -> dict[str, Any]:
        assembly = self._context_assembler.assemble(path_kind="erp_approval", state=state, call_site="erp_context")
        request = self._erp_request_from_state(state)
        context, connector_result = self._fetch_erp_context(request)
        result = {
            "erp_request": self._model_dump(request),
            "erp_context": self._model_dump(context),
            "erp_connector_result": self._model_dump(connector_result),
            "erp_connector_warnings": list(connector_result.warnings),
            "path_kind": "erp_approval",
            "turn_id": self._current_turn_id(state),
            "context_call_ids": self._context_call_ids(state),
        }
        _payload, updates = self._write_context_snapshot(
            state=state,
            result=result,
            assembly=assembly,
            turn_id=result["turn_id"],
            call_ids=result["context_call_ids"],
        )
        return {**result, **updates}

    async def erp_reasoning_node(self, state: GraphState) -> dict[str, Any]:
        assembly = self._context_assembler.assemble(path_kind="erp_approval", state=state, call_site="erp_reasoning")
        turn_id = self._current_turn_id(state)
        call_id = self._record_model_call_snapshot(
            state=state,
            assembly=assembly,
            call_site="erp_reasoning",
            call_type="erp_reasoning_call",
            turn_id=turn_id,
        )
        call_ids = self._context_call_ids(state, call_id)
        request = self._erp_request_from_state(state)
        context = self._erp_context_from_state(state, request=request)
        messages = list(assembly.history_messages)
        messages.append(
            {
                "role": "user",
                "content": self._format_erp_reasoning_input(request, context),
            }
        )
        try:
            raw_recommendation, usage = await self._stream_model_answer(
                messages,
                extra_instructions=list(assembly.extra_instructions) or None,
                system_prompt_override=ERP_REASONING_SYSTEM_PROMPT,
                stream_deltas=False,
                path_type=assembly.path_kind,
            )
        except Exception:
            raw_recommendation = ""
            usage = None
        recommendation = parse_recommendation(raw_recommendation)
        result = {
            "erp_request": self._model_dump(request),
            "erp_context": self._model_dump(context),
            "erp_recommendation": self._model_dump(recommendation),
            "answer_usage": usage,
            "path_kind": "erp_approval",
            "turn_id": turn_id,
            "context_call_ids": call_ids,
        }
        _payload, updates = self._write_context_snapshot(
            state=state,
            result=result,
            assembly=assembly,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        return {**result, **updates}

    async def erp_guard_node(self, state: GraphState) -> dict[str, Any]:
        assembly = self._context_assembler.assemble(path_kind="erp_approval", state=state, call_site="erp_guard")
        request = self._erp_request_from_state(state)
        context = self._erp_context_from_state(state, request=request)
        recommendation = self._erp_recommendation_from_state(state)
        guarded, guard = guard_recommendation(request, context, recommendation)
        result = {
            "erp_recommendation": self._model_dump(guarded),
            "erp_guard_result": self._model_dump(guard),
            "path_kind": "erp_approval",
            "turn_id": self._current_turn_id(state),
            "context_call_ids": self._context_call_ids(state),
        }
        _payload, updates = self._write_context_snapshot(
            state=state,
            result=result,
            assembly=assembly,
            turn_id=result["turn_id"],
            call_ids=result["context_call_ids"],
        )
        return {**result, **updates}

    async def erp_hitl_gate_node(self, state: GraphState) -> dict[str, Any]:
        assembly = self._context_assembler.assemble(path_kind="erp_approval", state=state, call_site="erp_hitl_gate")
        request_model = self._erp_request_from_state(state)
        context = self._erp_context_from_state(state, request=request_model)
        recommendation = self._erp_recommendation_from_state(state)
        recommendation, guard = self._erp_guard_from_state(state, request_model, context, recommendation)
        turn_id = self._current_turn_id(state)
        call_ids = self._context_call_ids(state)

        if not recommendation.human_review_required and not guard.human_review_required:
            result = {
                "erp_recommendation": self._model_dump(recommendation),
                "erp_guard_result": self._model_dump(guard),
                "erp_hitl_request": None,
                "erp_hitl_decision": None,
                "erp_review_status": "not_required",
                "path_kind": "erp_approval",
                "turn_id": turn_id,
                "context_call_ids": call_ids,
            }
            _payload, updates = self._write_context_snapshot(
                state=state,
                result=result,
                assembly=assembly,
                turn_id=turn_id,
                call_ids=call_ids,
            )
            return {**result, **updates}

        bindings = self._bindings_or_raise()
        request = self._build_erp_hitl_request(state, request_model, context, recommendation, guard)
        with with_observation(
            "hitl.decision",
            tracer_name="ragclaw.orchestration",
            attributes=self._otel_state_attributes(
                state,
                path_type="erp_approval",
                checkpoint_id=str(request.get("checkpoint_id", "") or "") or None,
                capability_id=request["capability_id"],
                capability_type=request["capability_type"],
            ),
        ) as span:
            response = self._erp_hitl_interrupt(request)
            response_payload = dict(response) if isinstance(response, dict) else {"decision": response}
            decision = str(response_payload.get("decision", "") or "").strip().lower()
            if decision not in {"approve", "reject", "edit"}:
                decision = "reject"
            set_span_attributes(span, {"hitl_decision": decision})

        edited_input = dict(response_payload.get("edited_input", {}) or {}) if decision == "edit" else None
        hitl_payload = await self._record_erp_hitl_decision(
            state=state,
            request=request,
            response_payload=response_payload,
            decision=decision,
            edited_input=edited_input,
            bindings=bindings,
        )

        review_status = "accepted_by_human"
        if decision == "reject":
            review_status = "rejected_by_human"
        elif decision == "edit":
            review_status = "edited_by_human"
            edited_input = edited_input or dict(hitl_payload.get("edited_input_snapshot", {}) or {})
            recommendation = self._erp_recommendation_from_edit_payload(edited_input)
            recommendation, guard = guard_recommendation(request_model, context, recommendation)

        result = {
            "erp_recommendation": self._model_dump(recommendation),
            "erp_guard_result": self._model_dump(guard),
            "erp_hitl_request": dict(request),
            "erp_hitl_decision": dict(hitl_payload),
            "erp_review_status": review_status,
            "path_kind": "erp_approval",
            "turn_id": turn_id,
            "context_call_ids": call_ids,
        }
        _payload, updates = self._write_context_snapshot(
            state=state,
            result=result,
            assembly=assembly,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        return {**result, **updates}

    async def erp_action_proposal_node(self, state: GraphState) -> dict[str, Any]:
        assembly = self._context_assembler.assemble(path_kind="erp_approval", state=state, call_site="erp_action_proposal")
        request = self._erp_request_from_state(state)
        context = self._erp_context_from_state(state, request=request)
        recommendation = self._erp_recommendation_from_state(state)
        recommendation, guard = self._erp_guard_from_state(state, request, context, recommendation)
        review_status = self._erp_review_status_from_state(state, recommendation, guard)
        if review_status == "rejected_by_human":
            bundle = ApprovalActionProposalBundle(
                request_id=request.approval_id,
                review_status=review_status,
                proposals=[],
            )
            validation = ApprovalActionValidationResult(
                passed=False,
                warnings=["Human reviewer rejected the agent recommendation; no action proposals were generated."],
            )
        else:
            bundle = build_action_proposals(request, context, recommendation, guard, review_status)
            bundle, validation = validate_action_proposals(request, context, bundle)

        turn_id = self._current_turn_id(state)
        call_ids = self._context_call_ids(state)
        result = {
            "erp_action_proposals": self._model_dump(bundle),
            "erp_action_validation_result": self._model_dump(validation),
            "path_kind": "erp_approval",
            "turn_id": turn_id,
            "context_call_ids": call_ids,
        }
        _payload, updates = self._write_context_snapshot(
            state=state,
            result=result,
            assembly=assembly,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        return {**result, **updates}

    async def erp_finalize_node(self, state: GraphState) -> dict[str, Any]:
        assembly = self._context_assembler.assemble(path_kind="erp_approval", state=state, call_site="erp_finalize")
        request = self._erp_request_from_state(state)
        context = self._erp_context_from_state(state, request=request)
        recommendation = self._erp_recommendation_from_state(state)
        recommendation, guard = self._erp_guard_from_state(state, request, context, recommendation)
        review_status = self._erp_review_status_from_state(state, recommendation, guard)
        action_bundle, action_validation = self._erp_action_proposals_from_state(
            state,
            request=request,
            context=context,
            recommendation=recommendation,
            guard=guard,
            review_status=review_status,
        )
        answer = self._render_erp_final_answer(
            request,
            context,
            recommendation,
            guard,
            review_status,
            action_bundle,
            action_validation,
        )
        await self._emit_final_answer(answer, usage=state.get("answer_usage"))
        turn_id = self._current_turn_id(state)
        call_ids = self._context_call_ids(state)
        result = {
            "final_answer": answer,
            "answer_segments": [answer] if answer else [],
            "answer_finalized": True,
            "erp_request": self._model_dump(request),
            "erp_context": self._model_dump(context),
            "erp_recommendation": self._model_dump(recommendation),
            "erp_guard_result": self._model_dump(guard),
            "erp_review_status": review_status,
            "erp_action_proposals": self._model_dump(action_bundle),
            "erp_action_validation_result": self._model_dump(action_validation),
            "path_kind": "erp_approval",
            "turn_id": turn_id,
            "context_call_ids": call_ids,
        }
        trace_result = self._write_erp_trace_record({**dict(state), **result})
        if trace_result is not None:
            result["erp_trace_write_result"] = self._model_dump(trace_result)
        proposal_results = self._write_erp_proposal_records({**dict(state), **result}, trace_result=trace_result)
        if proposal_results:
            result["erp_proposal_write_results"] = [self._model_dump(item) for item in proposal_results]
        final_state, updates = self._write_context_snapshot(
            state=state,
            result=result,
            assembly=assembly,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        self._record_post_turn_snapshot(
            state=final_state,
            assembly=assembly,
            call_site="erp_finalize",
            model_invoked=True,
            updates=updates,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        return {**result, **updates}

    async def capability_selection_node(self, state: GraphState) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        strategy = state.get("execution_strategy")
        if strategy is None:
            result = {"selected_capabilities": [], "turn_id": self._current_turn_id(state)}
            _payload, updates = self._write_context_snapshot(state=state, result=result, turn_id=result["turn_id"])
            return {**result, **updates}
        decision = state.get("route_decision")
        tools = self._agent._resolve_tools_for_strategy(strategy)
        if decision is not None and decision.allowed_tools:
            allowed_names = set(decision.allowed_tools)
            tools = [tool for tool in tools if getattr(tool, "name", "") in allowed_names]
        explicit_id, explicit_payload = self._explicit_capability_selection(self._user_message(state), tools) if tools else ("", None)
        result = {
            "selected_capabilities": [str(getattr(tool, "name", "") or "") for tool in tools],
            "explicit_capability_id": explicit_id,
            "explicit_capability_payload": explicit_payload,
            "path_kind": "capability_path",
        }
        _payload, updates = self._write_context_snapshot(state=state, result=result, turn_id=self._current_turn_id(state))
        return {**result, **updates}

    async def capability_approval_node(self, state: GraphState) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        request = self._build_hitl_request(state)
        if request is None:
            return {"interrupt_request": None, "approval_decision": ""}

        with with_observation(
            "hitl.decision",
            tracer_name="ragclaw.orchestration",
            attributes=self._otel_state_attributes(
                state,
                path_type="capability_path",
                checkpoint_id=str(request.get("checkpoint_id", "") or "") or None,
                capability_id=request["capability_id"],
                capability_type=request["capability_type"],
            ),
        ) as span:
            response = interrupt(request)
            response_payload = dict(response) if isinstance(response, dict) else {"decision": response}
            decision = str(response_payload.get("decision", "") or "").strip().lower()
            if decision not in {"approve", "reject", "edit"}:
                decision = "reject"
            set_span_attributes(span, {"hitl_decision": decision})
        thread_id = str(request["thread_id"] or "")
        checkpoint_id = self._resume_checkpoint_id or str(request.get("checkpoint_id", "") or "")
        edited_input = (
            dict(response_payload.get("edited_input", {}) or {})
            if decision == "edit"
            else None
        )
        audited_request = checkpoint_store.get_hitl_request(
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
        )
        audited_decision = checkpoint_store.get_hitl_decision(
            request_id=audited_request.request_id,
        ) if audited_request is not None else None
        if audited_request is not None and audited_decision is None:
            audited_request, audited_decision, _ = checkpoint_store.record_hitl_decision(
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                decision=decision,
                actor_id=str(response_payload.get("actor_id", "") or f"session:{request.get('session_id') or thread_id}"),
                actor_type=str(response_payload.get("actor_type", "") or "session_user"),
                decided_at=str(response_payload.get("decided_at", "") or bindings.runtime.now()),
                resume_source=str(response_payload.get("resume_source", "") or self._resume_source or "langgraph_resume"),
                edited_input_snapshot=edited_input,
            )

        payload = {
            "request_id": str(getattr(audited_request, "request_id", "") or response_payload.get("request_id", "") or ""),
            "requested_at": str(getattr(audited_request, "requested_at", "") or ""),
            "decision_id": str(getattr(audited_decision, "decision_id", "") or response_payload.get("decision_id", "") or ""),
            "decision": decision,
            "actor_id": str(getattr(audited_decision, "actor_id", "") or response_payload.get("actor_id", "") or ""),
            "actor_type": str(getattr(audited_decision, "actor_type", "") or response_payload.get("actor_type", "") or ""),
            "decided_at": str(getattr(audited_decision, "decided_at", "") or response_payload.get("decided_at", "") or ""),
            "run_id": str(getattr(audited_request, "run_id", "") or request.get("run_id", "") or bindings.handle.run_id),
            "session_id": getattr(audited_request, "session_id", None) if audited_request is not None else request.get("session_id"),
            "thread_id": thread_id,
            "checkpoint_id": str(getattr(audited_request, "checkpoint_id", "") or checkpoint_id),
            "capability_id": request["capability_id"],
            "capability_type": request["capability_type"],
            "display_name": request["display_name"],
            "risk_level": request["risk_level"],
            "reason": request["reason"],
            "proposed_input": dict(request["proposed_input"]),
            "resume_source": str(
                getattr(audited_decision, "resume_source", "") or response_payload.get("resume_source", "") or self._resume_source or "hitl_api"
            ),
            "orchestration_engine": "langgraph",
        }
        if decision == "approve":
            payload["approved_input_snapshot"] = (
                dict(getattr(audited_decision, "approved_input_snapshot", {}) or {})
                if audited_decision is not None
                else dict(request["proposed_input"])
            )
        elif decision == "edit":
            payload["edited_input_snapshot"] = (
                dict(getattr(audited_decision, "edited_input_snapshot", {}) or {})
                if audited_decision is not None
                else dict(edited_input or request["proposed_input"])
            )
        else:
            payload["rejected_input_snapshot"] = (
                dict(getattr(audited_decision, "rejected_input_snapshot", {}) or {})
                if audited_decision is not None
                else dict(request["proposed_input"])
            )
        await bindings.runtime.emit(
            bindings.handle,
            "hitl.approved" if decision == "approve" else "hitl.edited" if decision == "edit" else "hitl.rejected",
            dict(payload),
        )
        if decision == "approve":
            bindings.context.approval_overrides.add(str(request["capability_id"]))
            result = {
                "interrupt_request": request,
                "approval_decision": "approve",
                "recovery_action": "",
                "turn_id": self._current_turn_id(state),
            }
            _payload, updates = self._write_context_snapshot(state=state, result=result, turn_id=result["turn_id"])
            return {**result, **updates}
        if decision == "edit":
            bindings.context.approval_overrides.add(str(request["capability_id"]))
            result = {
                "interrupt_request": request,
                "approval_decision": "edit",
                "explicit_capability_id": str(request["capability_id"]),
                "explicit_capability_payload": dict(payload.get("edited_input_snapshot", {}) or request["proposed_input"]),
                "recovery_action": "",
                "turn_id": self._current_turn_id(state),
            }
            _payload, updates = self._write_context_snapshot(state=state, result=result, turn_id=result["turn_id"])
            return {**result, **updates}

        blocked_result = CapabilityResult(
            status="blocked",
            payload={},
            partial=False,
            error_type="rejected_by_user",
            error_message=f"{request['display_name']} was rejected by the user before execution.",
            retryable=False,
            call_id=f"hitl-{request['capability_id']}",
            retry_count=0,
        )
        bindings.context.governor.record_result(
            self._agent.get_capability_registry().get(str(request["capability_id"])),
            blocked_result,
        )
        await bindings.runtime.emit(
            bindings.handle,
            "capability.blocked",
            {
                "run_id": bindings.handle.run_id,
                "session_id": getattr(bindings.handle.metadata, "session_id", None),
                "capability_id": request["capability_id"],
                "capability_type": request["capability_type"],
                "display_name": request["display_name"],
                "call_id": blocked_result.call_id,
                "status": blocked_result.status,
                "retry_count": 0,
                "partial": False,
                "latency_ms": 0,
                "error_type": blocked_result.error_type,
                "error_message": blocked_result.error_message,
                "input": dict(request["proposed_input"]),
                "payload": {},
                "risk_level": request["risk_level"],
                "approval_required": True,
                "budget_cost": 0,
                "request_id": payload["request_id"],
                "decision_id": payload["decision_id"],
            },
        )
        rejection_answer = (
            f"I did not run {request['display_name']} because you rejected this approval request."
        )
        rejection_context = self._context_assembler.assemble(
            path_kind="capability_path",
            state=state,
            call_site="hitl_rejection",
        )
        turn_id = self._current_turn_id(state)
        await self._emit_final_answer(rejection_answer)
        result = {
            "interrupt_request": request,
            "approval_decision": "reject",
            "capability_results": [
                {
                    "capability_id": request["capability_id"],
                    "call_id": blocked_result.call_id,
                    "status": blocked_result.status,
                    "payload": {},
                    "error_type": blocked_result.error_type,
                    "error_message": blocked_result.error_message,
                }
            ],
            "final_answer": rejection_answer,
            "answer_segments": [rejection_answer],
            "answer_finalized": True,
            "needs_answer_synthesis": False,
            "recovery_action": "",
            "turn_id": turn_id,
            "context_call_ids": self._context_call_ids(state),
        }
        final_state, updates = self._write_context_snapshot(
            state=state,
            result=result,
            assembly=rejection_context,
            turn_id=turn_id,
            call_ids=result["context_call_ids"],
        )
        self._record_post_turn_snapshot(
            state=final_state,
            assembly=rejection_context,
            call_site="hitl_rejection",
            model_invoked=False,
            updates=updates,
            turn_id=turn_id,
            call_ids=result["context_call_ids"],
        )
        return {**result, **updates}

    async def capability_invoke_node(self, state: GraphState) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        if str(state.get("approval_decision", "") or "").strip().lower() == "reject":
            return {}
        strategy = state.get("execution_strategy")
        selected_capabilities = set(str(item or "") for item in state.get("selected_capabilities", []) or [])
        tools = []
        if strategy is not None:
            tools = [
                tool
                for tool in self._agent._resolve_tools_for_strategy(strategy)
                if str(getattr(tool, "name", "") or "") in selected_capabilities
            ]
        if not tools:
            result = {"selected_capabilities": [], "turn_id": self._current_turn_id(state)}
            _payload, updates = self._write_context_snapshot(state=state, result=result, turn_id=result["turn_id"])
            return {**result, **updates}
        explicit_id = str(state.get("explicit_capability_id", "") or "")
        explicit_payload = state.get("explicit_capability_payload")
        if explicit_id and explicit_payload is not None:
            tool = next((item for item in tools if str(getattr(item, "name", "") or "") == explicit_id), tools[0])
            call_id = f"explicit-{explicit_id}"
            tool_input = json.dumps(explicit_payload, ensure_ascii=False)
            await bindings.runtime.emit(bindings.handle, "tool.started", ToolCallRecord(tool=explicit_id, input=tool_input, call_id=call_id).to_dict())
            result = await tool.aexecute_capability(explicit_payload)
            rendered = tool.render_capability_result(result)
            await bindings.runtime.emit(bindings.handle, "tool.completed", ToolCallRecord(tool=explicit_id, input=tool_input, output=rendered, call_id=call_id).to_dict())
            result_entry = {
                "capability_id": explicit_id,
                "capability_type": str(getattr(tool.capability_spec, "capability_type", "") or ""),
                "display_name": str(getattr(tool.capability_spec, "display_name", "") or explicit_id),
                "risk_level": str(getattr(tool.capability_spec, "risk_level", "") or ""),
                "approval_required": bool(getattr(tool.capability_spec, "approval_required", False)),
                "call_id": result.call_id,
                "status": result.status,
                "payload": dict(result.payload),
                "error_type": result.error_type,
                "error_message": result.error_message,
                "retry_count": result.retry_count,
                "input": dict(explicit_payload),
            }
            if result.status in {"success", "partial"}:
                direct_output_context = self._context_assembler.assemble(
                    path_kind="capability_path",
                    state=state,
                    call_site="capability_direct_output",
                )
                turn_id = self._current_turn_id(state)
                await self._emit_final_answer(rendered)
                result_payload = {
                    "recorded_tools": [{"tool": explicit_id, "input": tool_input, "output": rendered, "call_id": call_id}],
                    "capability_results": [result_entry],
                    "final_answer": rendered,
                    "answer_segments": [rendered] if rendered else [],
                    "answer_finalized": True,
                    "needs_answer_synthesis": False,
                    "last_failure": None,
                    "recovery_action": "",
                    "recovered_from_failure": bool(state.get("last_failure")),
                    "turn_id": turn_id,
                    "context_call_ids": self._context_call_ids(state),
                }
                final_state, updates = self._write_context_snapshot(
                    state=state,
                    result=result_payload,
                    assembly=direct_output_context,
                    turn_id=turn_id,
                    call_ids=result_payload["context_call_ids"],
                )
                self._record_post_turn_snapshot(
                    state=final_state,
                    assembly=direct_output_context,
                    call_site="capability_direct_output",
                    model_invoked=False,
                    updates=updates,
                    turn_id=turn_id,
                    call_ids=result_payload["context_call_ids"],
                )
                return {**result_payload, **updates}
            result_payload = {
                "recorded_tools": [{"tool": explicit_id, "input": tool_input, "output": rendered, "call_id": call_id}],
                "capability_results": [result_entry],
                "final_answer": "",
                "answer_segments": [],
                "answer_finalized": False,
                "needs_answer_synthesis": False,
                "last_failure": result_entry,
                "recovery_action": "",
                "recovered_from_failure": False,
                "turn_id": self._current_turn_id(state),
            }
            _payload, updates = self._write_context_snapshot(state=state, result=result_payload, turn_id=result_payload["turn_id"])
            return {**result_payload, **updates}
        return await self._invoke_tool_path(
            state=state,
            message=self._user_message(state),
            strategy=state.get("execution_strategy"),
            skill_decision=state.get("skill_decision"),
            allowed_tools=tools,
        )

    async def capability_recovery_node(self, state: GraphState) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        failure = extract_latest_failed_capability(state)
        if failure is None:
            result = {
                "last_failure": None,
                "recovery_action": "",
                "recovery_metadata": dict(state.get("recovery_metadata", {}) or {}),
                "turn_id": self._current_turn_id(state),
            }
            _payload, updates = self._write_context_snapshot(state=state, result=result, turn_id=result["turn_id"])
            return {**result, **updates}

        spec = self._agent.get_capability_registry().get(failure.capability_id)
        recovery_attempts = dict(state.get("recovery_attempts", {}) or {})
        recovery_metadata = dict(state.get("recovery_metadata", {}) or {})
        retry_count = int(recovery_attempts.get(failure.failure_key, 0) or 0)
        escalated_failures = set(str(item) for item in recovery_metadata.get("escalated_failures", []) or [])
        decision = select_recovery_action(
            spec=spec,
            error_type=failure.error_type,
            retry_count=retry_count,
            already_escalated=failure.failure_key in escalated_failures,
        )
        with with_observation(
            "recovery",
            tracer_name="ragclaw.orchestration",
            attributes=self._otel_state_attributes(
                state,
                path_type="recovery_path",
                capability_id=failure.capability_id,
                capability_type=failure.capability_type,
                error_type=failure.error_type,
                recovery_action=decision.action,
            ),
        ):
            base_payload = {
                "run_id": bindings.handle.run_id,
                "session_id": state.get("session_id"),
                "thread_id": state.get("thread_id"),
                "capability_id": failure.capability_id,
                "capability_type": failure.capability_type,
                "display_name": failure.display_name,
                "error_type": failure.error_type,
                "error_message": failure.error_message,
                "recovery_action": decision.action,
                "retry_count": retry_count,
                "from_checkpoint": bool(self._resume_checkpoint_id),
                "recovered": False,
                "checkpoint_id": self._resume_checkpoint_id or str(state.get("checkpoint_meta", {}).get("checkpoint_id", "") or ""),
            }
            await bindings.runtime.emit(bindings.handle, "recovery.started", dict(base_payload))

        if decision.action == "retry_once":
            recovery_attempts[failure.failure_key] = retry_count + 1
            await bindings.runtime.emit(
                bindings.handle,
                "recovery.retrying",
                {
                    **base_payload,
                    "retry_count": retry_count + 1,
                    "recovered": True,
                },
            )
            result = {
                "recovery_attempts": recovery_attempts,
                "last_failure": failure.to_dict(),
                "recovery_action": "retry_once",
                "recovered_from_failure": False,
                "recovery_metadata": {
                    **recovery_metadata,
                    "last_decision_reason": decision.reason,
                    "last_failure_key": failure.failure_key,
                },
                "answer_finalized": False,
                "approval_decision": "",
                "turn_id": self._current_turn_id(state),
            }
            _payload, updates = self._write_context_snapshot(state=state, result=result, turn_id=result["turn_id"])
            return {**result, **updates}

        if decision.action == "escalate_to_hitl":
            escalated_failures.add(failure.failure_key)
            interrupt_request = build_recovery_hitl_request(
                state=state,
                failure=failure,
                checkpoint_id=self._resume_checkpoint_id,
                reason=f"Recovery escalation for {failure.display_name}: {decision.reason}",
            )
            await bindings.runtime.emit(
                bindings.handle,
                "recovery.escalated",
                {
                    **base_payload,
                    "recovered": False,
                },
            )
            result = {
                "interrupt_request": interrupt_request,
                "approval_decision": "",
                "recovery_action": "escalate_to_hitl",
                "last_failure": failure.to_dict(),
                "recovery_metadata": {
                    **recovery_metadata,
                    "escalated_failures": sorted(escalated_failures),
                    "last_decision_reason": decision.reason,
                    "last_failure_key": failure.failure_key,
                },
                "answer_finalized": False,
                "turn_id": self._current_turn_id(state),
            }
            _payload, updates = self._write_context_snapshot(state=state, result=result, turn_id=result["turn_id"])
            return {**result, **updates}

        fail_fast = decision.action == "fail_fast"
        answer = build_recovery_fallback_answer(
            failure=failure,
            recovered=retry_count > 0,
            fail_fast=fail_fast,
        )
        await bindings.runtime.emit(
            bindings.handle,
            "recovery.failed" if fail_fast else "recovery.fallback",
            {
                **base_payload,
                "recovered": False,
            },
        )
        recovery_context = self._context_assembler.assemble(
            path_kind="recovery_path",
            state=state,
            call_site="recovery_fallback",
        )
        turn_id = self._current_turn_id(state)
        await self._emit_final_answer(answer)
        result = {
            "final_answer": answer,
            "answer_segments": [answer] if answer else [],
            "answer_finalized": True,
            "needs_answer_synthesis": False,
            "recovery_action": decision.action,
            "last_failure": failure.to_dict(),
            "recovery_metadata": {
                **recovery_metadata,
                "last_decision_reason": decision.reason,
                "last_failure_key": failure.failure_key,
            },
            "turn_id": turn_id,
            "context_call_ids": self._context_call_ids(state),
        }
        final_state, updates = self._write_context_snapshot(
            state=state,
            result=result,
            assembly=recovery_context,
            turn_id=turn_id,
            call_ids=result["context_call_ids"],
        )
        self._record_post_turn_snapshot(
            state=final_state,
            assembly=recovery_context,
            call_site="recovery_fallback",
            model_invoked=False,
            updates=updates,
            turn_id=turn_id,
            call_ids=result["context_call_ids"],
        )
        return {**result, **updates}

    async def capability_synthesis_node(self, state: GraphState) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        if state.get("answer_finalized"):
            return {}
        final_answer = str(state.get("final_answer", "") or "")
        recorded_tools = list(state.get("recorded_tools", []))
        if state.get("needs_answer_synthesis"):
            final_answer = await self._stream_tool_result_fallback(
                state=state,
                user_message=self._user_message(state),
                recorded_tools=recorded_tools,
                strategy=state.get("execution_strategy"),
            )
        elif not final_answer and recorded_tools:
            final_answer = "\n\n".join(
                str(item.get("output", "") or "").strip()
                for item in recorded_tools
                if str(item.get("output", "") or "").strip()
            )
        if final_answer:
            if not state.get("needs_answer_synthesis"):
                synthesis_context = self._context_assembler.assemble(
                    path_kind="capability_path",
                    state=state,
                    call_site="capability_output_join",
                )
            else:
                synthesis_context = self._context_assembler.assemble(
                    path_kind="capability_path",
                    state=state,
                    call_site="tool_result_fallback",
                )
            await bindings.runtime.emit(bindings.handle, "answer.completed", AnswerRecord(content=final_answer, segment_index=bindings.runtime.current_segment_index(bindings.handle), final=True).to_dict())
        else:
            synthesis_context = self._context_assembler.assemble(
                path_kind="capability_path",
                state=state,
                call_site="capability_output_join",
            )
        turn_id = self._current_turn_id(state)
        call_ids = self._context_call_ids(state)
        result = {"final_answer": final_answer, "answer_finalized": True, "turn_id": turn_id, "context_call_ids": call_ids}
        final_state, updates = self._write_context_snapshot(
            state=state,
            result=result,
            assembly=synthesis_context,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        self._record_post_turn_snapshot(
            state=final_state,
            assembly=synthesis_context,
            call_site="tool_result_fallback" if state.get("needs_answer_synthesis") else "capability_output_join",
            model_invoked=bool(state.get("needs_answer_synthesis")),
            updates=updates,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        return {**result, **updates}

    async def capability_guard_node(self, state: GraphState) -> dict[str, Any]:
        result = {"guard_result": None}
        _payload, updates = self._write_context_snapshot(state=state, result=result, turn_id=self._current_turn_id(state))
        return {**result, **updates}

    async def finalize_node(self, state: GraphState, *, config: Any | None = None) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        result = {
            "governor_snapshot": bindings.runtime.governor_for(bindings.handle.run_id).snapshot(),
            **self._studio_summary_fields(state),
        }
        _payload, updates = self._write_context_snapshot(state=state, result=result, turn_id=self._current_turn_id(state))
        if state.get("studio_managed_run"):
            try:
                bindings.runtime.complete_run(bindings.handle)
            except KeyError:
                pass
        return {**result, **updates}

    def _thread_id_for(self, handle: "RuntimeRunHandle") -> str:
        return self._resume_thread_id or checkpoint_store.thread_id_for(
            session_id=getattr(handle.metadata, "session_id", None),
            run_id=handle.run_id,
        )

    async def _emit_resume_events(self, runtime: "HarnessRuntime", handle: "RuntimeRunHandle", thread_id: str) -> None:
        with with_observation(
            "checkpoint.resume",
            tracer_name="ragclaw.orchestration",
            attributes={
                "run_id": handle.run_id,
                "thread_id": thread_id,
                "session_id": getattr(handle.metadata, "session_id", None),
                "checkpoint_id": self._resume_checkpoint_id or None,
                "resume_source": self._resume_source or "checkpoint",
                "path_type": "resumed_hitl" if self._resume_source else "",
                "context_path_type": "resumed_hitl" if self._resume_source else "",
                "orchestration_engine": "langgraph",
            },
        ):
            summary = checkpoint_store.get_checkpoint(thread_id=thread_id, checkpoint_id=self._resume_checkpoint_id)
            if summary is None:
                raise RuntimeError(f"checkpoint not found: {self._resume_checkpoint_id}")
            await runtime.emit(
                handle,
                "checkpoint.resumed",
                {
                    "thread_id": thread_id,
                    "checkpoint_id": summary.checkpoint_id,
                    "resume_source": self._resume_source or "checkpoint",
                    "orchestration_engine": "langgraph",
                    "state_label": summary.state_label,
                    "created_at": summary.created_at,
                },
            )

    async def _emit_checkpoint_created(self, runtime: "HarnessRuntime", handle: "RuntimeRunHandle", thread_id: str) -> None:
        with with_observation(
            "checkpoint.create",
            tracer_name="ragclaw.orchestration",
            attributes={
                "run_id": handle.run_id,
                "thread_id": thread_id,
                "session_id": getattr(handle.metadata, "session_id", None),
                "path_type": "",
                "context_path_type": "",
                "orchestration_engine": "langgraph",
            },
        ) as span:
            latest = checkpoint_store.latest_checkpoint(thread_id=thread_id)
            if latest is None:
                return
            set_span_attributes(span, {"checkpoint_id": latest.checkpoint_id})
            await runtime.emit(
                handle,
                "checkpoint.created",
                {
                    "thread_id": latest.thread_id,
                    "checkpoint_id": latest.checkpoint_id,
                    "created_at": latest.created_at,
                    "state_label": latest.state_label,
                    "resume_eligible": latest.resume_eligible,
                    "orchestration_engine": "langgraph",
                },
            )

    async def _emit_hitl_interrupt_if_needed(
        self,
        runtime: "HarnessRuntime",
        handle: "RuntimeRunHandle",
        thread_id: str,
        result: GraphState,
    ) -> None:
        interrupts = list(result.get("__interrupt__", []) or []) if isinstance(result, dict) else []
        if not interrupts:
            return
        with with_observation(
            "hitl.request",
            tracer_name="ragclaw.orchestration",
            attributes={
                "run_id": handle.run_id,
                "thread_id": thread_id,
                "session_id": getattr(handle.metadata, "session_id", None),
                "resume_source": self._resume_source or "hitl_api",
                "path_type": "capability_path",
                "context_path_type": "capability_path",
                "orchestration_engine": "langgraph",
            },
        ) as span:
            latest = checkpoint_store.latest_checkpoint(thread_id=thread_id)
            if latest is None:
                return
            raw_payload = getattr(interrupts[0], "value", {}) or {}
            request, created = checkpoint_store.record_pending_hitl(
                PendingHitlRequest(
                    request_id="",
                    run_id=str(raw_payload.get("run_id", "") or handle.run_id),
                    thread_id=str(raw_payload.get("thread_id", "") or thread_id),
                    session_id=str(raw_payload.get("session_id")) if raw_payload.get("session_id") is not None else None,
                    checkpoint_id=str(latest.checkpoint_id or raw_payload.get("checkpoint_id", "") or ""),
                    capability_id=str(raw_payload.get("capability_id", "") or ""),
                    capability_type=str(raw_payload.get("capability_type", "") or ""),
                    display_name=str(raw_payload.get("display_name", "") or ""),
                    risk_level=str(raw_payload.get("risk_level", "") or ""),
                    reason=str(raw_payload.get("reason", "") or ""),
                    proposed_input=dict(raw_payload.get("proposed_input", {}) or {}),
                    requested_at=runtime.now(),
                )
            )
            if not created:
                return
            set_span_attributes(span, {"checkpoint_id": request.checkpoint_id or latest.checkpoint_id, "capability_id": request.capability_id, "capability_type": request.capability_type})
            await runtime.emit(
                handle,
                "checkpoint.interrupted",
                {
                    "thread_id": request.thread_id,
                    "checkpoint_id": request.checkpoint_id,
                    "resume_source": self._resume_source or "hitl_api",
                    "orchestration_engine": "langgraph",
                    "state_label": "interrupted",
                    "created_at": latest.created_at,
                },
            )
            await runtime.emit(
                handle,
                "hitl.requested",
                {
                    **request.to_dict(),
                    "orchestration_engine": "langgraph",
                    "resume_source": self._resume_source or "hitl_api",
                },
            )

    def _path_kind_from_decision(self, decision: "RoutingDecision") -> str:
        if decision.intent == "erp_approval":
            return "erp_approval"
        if decision.intent == "knowledge_qa":
            return "knowledge_qa"
        if decision.intent == "direct_answer" or (not decision.needs_tools and not decision.needs_retrieval):
            return "direct_answer"
        return "capability_path"

    def _model_dump(self, model: Any) -> dict[str, Any]:
        dump = getattr(model, "model_dump", None)
        if callable(dump):
            return dict(dump())
        return dict(model or {})

    def _erp_request_from_state(self, state: GraphState) -> ApprovalRequest:
        payload = state.get("erp_request")
        if not payload:
            return parse_approval_request("", self._user_message(state))
        try:
            return ApprovalRequest.model_validate(payload or {})
        except Exception:
            return parse_approval_request("", self._user_message(state))

    def _fetch_erp_context(self, request: ApprovalRequest):
        query = ErpContextQuery.from_request(request)
        registry = getattr(self, "_erp_connector_registry", None)
        if registry is None and hasattr(self, "_erp_context_adapter"):
            context = self._erp_context_adapter.fetch_context(query)
            connector_result = ErpReadResult(
                provider="mock",
                status="success" if context.records else "unavailable",
                records=list(context.records),
                warnings=[] if context.records else ["Mock ERP context adapter returned no records."],
                diagnostics={"legacy_adapter_fallback": True},
                non_action_statement=ERP_CONNECTOR_NON_ACTION_STATEMENT,
            )
            return context, connector_result
        if registry is None:
            base_dir = getattr(getattr(self, "_agent", None), "base_dir", None)
            registry = build_connector_registry_from_env(base_dir)
            self._erp_connector_registry = registry
        connector_result = registry.default().fetch_context(read_request_from_context_query(query))
        context = build_context_bundle_from_records(
            connector_result.records,
            request_id=request.approval_id or "unidentified",
        )
        return context, connector_result

    def _erp_context_from_state(self, state: GraphState, *, request: ApprovalRequest) -> ApprovalContextBundle:
        payload = state.get("erp_context")
        if not payload:
            return self._fetch_erp_context(request)[0]
        try:
            context = ApprovalContextBundle.model_validate(payload or {})
            return context if context.records else self._fetch_erp_context(request)[0]
        except Exception:
            return self._fetch_erp_context(request)[0]

    def _erp_recommendation_from_state(self, state: GraphState) -> ApprovalRecommendation:
        payload = state.get("erp_recommendation")
        if not payload:
            return parse_recommendation("")
        try:
            return ApprovalRecommendation.model_validate(payload or {})
        except Exception:
            return parse_recommendation("")

    def _erp_action_proposals_from_state(
        self,
        state: GraphState,
        *,
        request: ApprovalRequest,
        context: ApprovalContextBundle,
        recommendation: ApprovalRecommendation,
        guard: ApprovalGuardResult,
        review_status: str,
    ) -> tuple[ApprovalActionProposalBundle, ApprovalActionValidationResult]:
        bundle_payload = state.get("erp_action_proposals")
        validation_payload = state.get("erp_action_validation_result")
        try:
            if bundle_payload and validation_payload:
                return (
                    ApprovalActionProposalBundle.model_validate(bundle_payload),
                    ApprovalActionValidationResult.model_validate(validation_payload),
                )
        except Exception:
            pass
        if review_status == "rejected_by_human":
            return (
                ApprovalActionProposalBundle(request_id=request.approval_id, review_status=review_status, proposals=[]),
                ApprovalActionValidationResult(
                    passed=False,
                    warnings=["Human reviewer rejected the agent recommendation; no action proposals were generated."],
                ),
            )
        bundle = build_action_proposals(request, context, recommendation, guard, review_status)
        return validate_action_proposals(request, context, bundle)

    def _write_erp_trace_record(self, state: GraphState | dict[str, Any]):
        repository = getattr(self, "_erp_trace_repository", None)
        if repository is None:
            agent = getattr(self, "_agent", None)
            base_dir = getattr(agent, "base_dir", None)
            if base_dir is None:
                return None
            repository = ApprovalTraceRepository(default_trace_path(base_dir))
            self._erp_trace_repository = repository
        try:
            record = build_trace_record_from_state(dict(state), self._trace_now())
            return repository.upsert(record)
        except Exception:
            return None

    def _write_erp_proposal_records(self, state: GraphState | dict[str, Any], *, trace_result: Any = None) -> list[Any]:
        repository = getattr(self, "_erp_proposal_repository", None)
        if repository is None:
            agent = getattr(self, "_agent", None)
            base_dir = getattr(agent, "base_dir", None)
            if base_dir is None:
                return []
            repository = ApprovalActionProposalRepository(default_proposal_ledger_path(base_dir))
            self._erp_proposal_repository = repository
        try:
            trace_id = str(getattr(trace_result, "trace_id", "") or "")
            if not trace_id:
                trace_id = trace_id_from_state(dict(state))
            records = build_proposal_records_from_state(dict(state), trace_id, self._trace_now())
            if not records:
                return []
            return repository.upsert_many(records)
        except Exception:
            return []

    def _trace_now(self) -> str:
        try:
            return str(self._bindings_or_raise().runtime.now())
        except Exception:
            return datetime.now(timezone.utc).isoformat()

    def _erp_guard_from_state(
        self,
        state: GraphState,
        request: ApprovalRequest,
        context: ApprovalContextBundle,
        recommendation: ApprovalRecommendation,
    ) -> tuple[ApprovalRecommendation, ApprovalGuardResult]:
        payload = state.get("erp_guard_result")
        try:
            if payload:
                return recommendation, ApprovalGuardResult.model_validate(payload)
        except Exception:
            pass
        return guard_recommendation(request, context, recommendation)

    def _build_erp_hitl_request(
        self,
        state: GraphState,
        request: ApprovalRequest,
        context: ApprovalContextBundle,
        recommendation: ApprovalRecommendation,
        guard: ApprovalGuardResult,
    ) -> dict[str, Any]:
        context_source_ids = [record.source_id for record in context.records]
        return {
            "run_id": state["run_id"],
            "thread_id": state.get("thread_id", ""),
            "session_id": state.get("session_id"),
            "capability_id": ERP_RECOMMENDATION_REVIEW_CAPABILITY_ID,
            "capability_type": "function",
            "display_name": ERP_RECOMMENDATION_REVIEW_DISPLAY_NAME,
            "risk_level": self._erp_review_risk_level(recommendation, guard),
            "reason": (
                "Review the agent's ERP approval recommendation. Accepting this HITL request accepts "
                "or edits the recommendation only; it does not execute an ERP action."
            ),
            "proposed_input": {
                "review_type": "erp_recommendation_review",
                "approval_request": self._model_dump(request),
                "context_source_ids": context_source_ids,
                "recommendation": self._model_dump(recommendation),
                "guard_result": self._model_dump(guard),
                "explicit_non_action_statement": ERP_RECOMMENDATION_REVIEW_NON_ACTION,
            },
            "checkpoint_id": self._resume_checkpoint_id or str(state.get("checkpoint_meta", {}).get("checkpoint_id", "") or ""),
        }

    def _erp_review_risk_level(self, recommendation: ApprovalRecommendation, guard: ApprovalGuardResult) -> str:
        if recommendation.status in {"blocked", "recommend_reject", "escalate"}:
            return "high"
        if guard.warnings:
            return "high"
        if recommendation.status == "request_more_info":
            return "medium"
        if recommendation.status == "recommend_approve" and recommendation.human_review_required:
            return "medium"
        return "low"

    def _erp_hitl_interrupt(self, request: dict[str, Any]) -> Any:
        return interrupt(request)

    async def _record_erp_hitl_decision(
        self,
        *,
        state: GraphState,
        request: dict[str, Any],
        response_payload: dict[str, Any],
        decision: str,
        edited_input: dict[str, Any] | None,
        bindings: _ExecutionBindings,
    ) -> dict[str, Any]:
        thread_id = str(request.get("thread_id", "") or "")
        checkpoint_id = self._resume_checkpoint_id or str(request.get("checkpoint_id", "") or "")
        audited_request = None
        audited_decision = None
        if thread_id and checkpoint_id:
            try:
                audited_request = checkpoint_store.get_hitl_request(thread_id=thread_id, checkpoint_id=checkpoint_id)
                audited_decision = (
                    checkpoint_store.get_hitl_decision(request_id=audited_request.request_id)
                    if audited_request is not None
                    else None
                )
                if audited_request is not None and audited_decision is None:
                    audited_request, audited_decision, _ = checkpoint_store.record_hitl_decision(
                        thread_id=thread_id,
                        checkpoint_id=checkpoint_id,
                        decision=decision,
                        actor_id=str(response_payload.get("actor_id", "") or f"session:{request.get('session_id') or thread_id}"),
                        actor_type=str(response_payload.get("actor_type", "") or "session_user"),
                        decided_at=str(response_payload.get("decided_at", "") or bindings.runtime.now()),
                        resume_source=str(response_payload.get("resume_source", "") or self._resume_source or "langgraph_resume"),
                        edited_input_snapshot=edited_input,
                    )
            except Exception:
                audited_request = None
                audited_decision = None

        payload = {
            "request_id": str(getattr(audited_request, "request_id", "") or response_payload.get("request_id", "") or ""),
            "requested_at": str(getattr(audited_request, "requested_at", "") or ""),
            "decision_id": str(getattr(audited_decision, "decision_id", "") or response_payload.get("decision_id", "") or ""),
            "decision": decision,
            "actor_id": str(getattr(audited_decision, "actor_id", "") or response_payload.get("actor_id", "") or ""),
            "actor_type": str(getattr(audited_decision, "actor_type", "") or response_payload.get("actor_type", "") or ""),
            "decided_at": str(getattr(audited_decision, "decided_at", "") or response_payload.get("decided_at", "") or ""),
            "run_id": str(getattr(audited_request, "run_id", "") or request.get("run_id", "") or bindings.handle.run_id),
            "session_id": getattr(audited_request, "session_id", None) if audited_request is not None else request.get("session_id"),
            "thread_id": thread_id or str(state.get("thread_id", "") or ""),
            "checkpoint_id": str(getattr(audited_request, "checkpoint_id", "") or checkpoint_id),
            "capability_id": request["capability_id"],
            "capability_type": request["capability_type"],
            "display_name": request["display_name"],
            "risk_level": request["risk_level"],
            "reason": request["reason"],
            "proposed_input": dict(request["proposed_input"]),
            "resume_source": str(
                getattr(audited_decision, "resume_source", "") or response_payload.get("resume_source", "") or self._resume_source or "hitl_api"
            ),
            "orchestration_engine": "langgraph",
        }
        if decision == "approve":
            payload["approved_input_snapshot"] = (
                dict(getattr(audited_decision, "approved_input_snapshot", {}) or {})
                if audited_decision is not None
                else dict(request["proposed_input"])
            )
        elif decision == "edit":
            payload["edited_input_snapshot"] = (
                dict(getattr(audited_decision, "edited_input_snapshot", {}) or {})
                if audited_decision is not None
                else dict(edited_input or request["proposed_input"])
            )
        else:
            payload["rejected_input_snapshot"] = (
                dict(getattr(audited_decision, "rejected_input_snapshot", {}) or {})
                if audited_decision is not None
                else dict(request["proposed_input"])
            )
        await bindings.runtime.emit(
            bindings.handle,
            "hitl.approved" if decision == "approve" else "hitl.edited" if decision == "edit" else "hitl.rejected",
            dict(payload),
        )
        return payload

    def _erp_recommendation_from_edit_payload(self, edited_input: dict[str, Any] | None) -> ApprovalRecommendation:
        candidate: Any = dict(edited_input or {})
        if isinstance(candidate, dict) and isinstance(candidate.get("recommendation"), dict):
            candidate = candidate["recommendation"]
        if isinstance(candidate, dict):
            try:
                return ApprovalRecommendation.model_validate(candidate)
            except Exception:
                return parse_recommendation(json.dumps(candidate, ensure_ascii=False))
        return parse_recommendation("")

    def _erp_review_status_from_state(
        self,
        state: GraphState,
        recommendation: ApprovalRecommendation,
        guard: ApprovalGuardResult | None = None,
    ) -> str:
        status = str(state.get("erp_review_status", "") or "").strip()
        if status:
            return status
        if recommendation.human_review_required or (guard is not None and guard.human_review_required):
            return "requested"
        return "not_required"

    def _render_erp_final_answer(
        self,
        request: ApprovalRequest,
        context: ApprovalContextBundle,
        recommendation: ApprovalRecommendation,
        guard: ApprovalGuardResult,
        review_status: str,
        action_bundle: ApprovalActionProposalBundle,
        action_validation: ApprovalActionValidationResult,
    ) -> str:
        rendered_actions = render_action_proposals(action_bundle, action_validation)
        if review_status == "rejected_by_human":
            return "\n".join(
                [
                    "ERP approval recommendation review",
                    "",
                    "Human review status: rejected_by_human",
                    "Human reviewer rejected the agent recommendation.",
                    "",
                    f"Approval request: {request.approval_type} / {request.approval_id or 'unidentified'}",
                    ERP_NO_ACTION_EXECUTED_STATEMENT,
                    "",
                    rendered_actions,
                ]
            ).strip()
        answer = render_recommendation(request, context, recommendation, guard)
        return f"{answer}\n\nHuman review status: {review_status}\n\n{rendered_actions}".strip()

    def _format_erp_reasoning_input(self, request: ApprovalRequest, context: ApprovalContextBundle) -> str:
        erp_records = [record.model_dump() for record in context.records if record.record_type != "policy"]
        policy_records = [record.model_dump() for record in context.records if record.record_type == "policy"]
        schema = {
            "status": "recommend_approve | recommend_reject | request_more_info | escalate | blocked",
            "confidence": 0.0,
            "summary": "string",
            "rationale": ["string"],
            "missing_information": ["string"],
            "risk_flags": ["string"],
            "citations": ["source_id"],
            "proposed_next_action": "none | request_more_info | route_to_manager | route_to_finance | route_to_procurement | route_to_legal | manual_review",
            "human_review_required": True,
        }
        return (
            "[Approval request]\n"
            + json.dumps(self._model_dump(request), ensure_ascii=False, indent=2)
            + "\n\n[ERP records]\n"
            + json.dumps(erp_records, ensure_ascii=False, indent=2)
            + "\n\n[Policy records]\n"
            + json.dumps(policy_records, ensure_ascii=False, indent=2)
            + "\n\n[Missing context hints]\n"
            + json.dumps(self._erp_missing_context_hints(request, context), ensure_ascii=False, indent=2)
            + "\n\n[Output JSON schema]\n"
            + json.dumps(schema, ensure_ascii=False, indent=2)
            + "\n\nReturn JSON only. Citations must be source_id values from ERP records or Policy records."
        )

    def _erp_missing_context_hints(self, request: ApprovalRequest, context: ApprovalContextBundle) -> list[str]:
        record_types = {record.record_type for record in context.records}
        hints: list[str] = []
        if "approval_request" not in record_types:
            hints.append("approval_request record is missing")
        if "policy" not in record_types:
            hints.append("policy records are missing")
        if request.approval_type == "purchase_requisition":
            if "vendor" not in record_types:
                hints.append("vendor record is missing for purchase requisition")
            if "budget" not in record_types:
                hints.append("budget record is missing for purchase requisition")
        if request.approval_type == "invoice_payment":
            for record_type in ("purchase_order", "goods_receipt", "invoice"):
                if record_type not in record_types:
                    hints.append(f"{record_type} record is missing for invoice/payment review")
        if request.approval_type == "supplier_onboarding" and "vendor" not in record_types:
            hints.append("vendor onboarding record is missing")
        if request.approval_type == "contract_exception" and "contract" not in record_types:
            hints.append("contract record is missing")
        if request.approval_type == "budget_exception" and "budget" not in record_types:
            hints.append("budget record is missing")
        return hints

    async def _activate_skill_capability(self, *, message: str, routing_decision: "RoutingDecision", skill_decision: SkillDecision) -> None:
        skill_key = skill_decision.skill_name.replace("-", "_")
        spec = self._agent.get_capability_registry().get(f"skill.{skill_key}")
        await invoke_capability(
            spec=spec,
            payload={"message": message, "allowed_capabilities": list(getattr(routing_decision, "allowed_tools", ()) or ())},
            execute_async=self._build_skill_runner(spec, skill_decision),
        )

    def _build_skill_runner(self, spec, skill_decision: SkillDecision):
        async def _runner(_payload: dict[str, Any]) -> CapabilityResult:
            return CapabilityResult(status="success", payload={"capability_id": spec.capability_id, "guidance": skill_instruction(skill_decision.skill_name), "reason_short": skill_decision.reason_short, "confidence": skill_decision.confidence}, partial=False)
        return _runner

    def _build_hitl_request(self, state: GraphState) -> dict[str, Any] | None:
        existing_request = state.get("interrupt_request")
        if isinstance(existing_request, dict) and existing_request:
            return dict(existing_request)
        selected_capabilities = [str(item or "") for item in state.get("selected_capabilities", []) or []]
        if not selected_capabilities:
            return None
        registry = self._agent.get_capability_registry()
        selected_specs = []
        for capability_id in selected_capabilities:
            try:
                spec = registry.get(capability_id)
            except KeyError:
                continue
            if spec.approval_required:
                selected_specs.append(spec)
        if not selected_specs:
            return None
        spec = selected_specs[0]
        proposed_input = state.get("explicit_capability_payload")
        if not isinstance(proposed_input, dict) or not proposed_input:
            proposed_input = self._approval_proposed_input(spec.capability_id, self._user_message(state))
        return {
            "run_id": state["run_id"],
            "thread_id": state.get("thread_id", ""),
            "session_id": state.get("session_id"),
            "capability_id": spec.capability_id,
            "capability_type": spec.capability_type,
            "display_name": spec.display_name,
            "risk_level": spec.risk_level,
            "reason": f"{spec.display_name} requires explicit approval before execution.",
            "proposed_input": dict(proposed_input),
            "checkpoint_id": str(state.get("checkpoint_meta", {}).get("checkpoint_id", "") or ""),
        }

    def _approval_proposed_input(self, capability_id: str, user_message: str) -> dict[str, Any]:
        normalized = str(user_message or "").strip()
        if capability_id == "python_repl":
            print_match = re.search(r"(print\s*\([^)]+\))", normalized, re.IGNORECASE)
            if print_match:
                return {"code": print_match.group(1)}
            calc_match = re.search(r"\bcalculate\s+(.+?)(?:,|and tell|then tell|$)", normalized, re.IGNORECASE)
            if calc_match:
                expression = calc_match.group(1).strip().rstrip(".")
                return {"code": f"print({expression})"}
            return {"code": normalized}
        return {"message": normalized}

    async def _stream_model_answer(
        self,
        messages: list[dict[str, str]],
        *,
        extra_instructions: list[str] | None = None,
        system_prompt_override: str | None = None,
        stream_deltas: bool = True,
        path_type: str = "",
    ) -> tuple[str, dict[str, int] | None]:
        bindings = self._bindings_or_raise()
        with with_observation(
            "answer.synthesis",
            tracer_name="ragclaw.orchestration",
            attributes=self._otel_state_attributes(
                {
                    "run_id": bindings.handle.run_id,
                    "session_id": getattr(bindings.handle.metadata, "session_id", None),
                    "thread_id": getattr(bindings.handle.metadata, "thread_id", None),
                    "checkpoint_meta": {
                        "checkpoint_id": getattr(bindings.handle.metadata, "checkpoint_id", ""),
                        "resume_source": getattr(bindings.handle.metadata, "resume_source", ""),
                        "orchestration_engine": getattr(bindings.handle.metadata, "orchestration_engine", "langgraph"),
                    },
                    "path_kind": path_type,
                },
                path_type=path_type,
                message_count=len(messages),
                stream_deltas=stream_deltas,
                system_override=bool(system_prompt_override),
            ),
        ) as span:
            started = False
            final_answer = ""
            usage = None
            async for event in self._execution.astream_model_answer(messages, extra_instructions=extra_instructions, system_prompt_override=system_prompt_override):
                event_type = str(event.get("type", "") or "")
                if event_type == "token":
                    if not started and stream_deltas:
                        await bindings.runtime.emit(bindings.handle, "answer.started", AnswerRecord(content="", segment_index=bindings.runtime.current_segment_index(bindings.handle), final=False).to_dict())
                        started = True
                    content = str(event.get("content", "") or "")
                    if content:
                        final_answer += content
                        if stream_deltas:
                            await bindings.runtime.emit(bindings.handle, "answer.delta", AnswerRecord(content=content, segment_index=bindings.runtime.current_segment_index(bindings.handle), final=False).to_dict())
                elif event_type == "done":
                    final_answer = str(event.get("content", "") or "").strip() or final_answer.strip()
                    usage = event.get("usage")
                    if not started and stream_deltas:
                        await bindings.runtime.emit(bindings.handle, "answer.started", AnswerRecord(content="", segment_index=bindings.runtime.current_segment_index(bindings.handle), final=False).to_dict())
                    if stream_deltas:
                        await bindings.runtime.emit(bindings.handle, "answer.completed", AnswerRecord(content=final_answer, segment_index=bindings.runtime.current_segment_index(bindings.handle), final=True, input_tokens=int(usage.get("input_tokens", 0) or 0) if isinstance(usage, dict) and usage.get("input_tokens") is not None else None, output_tokens=int(usage.get("output_tokens", 0) or 0) if isinstance(usage, dict) and usage.get("output_tokens") is not None else None).to_dict())
            set_span_attributes(
                span,
                {
                    "output_tokens": int(usage.get("output_tokens", 0) or 0) if isinstance(usage, dict) and usage.get("output_tokens") is not None else None,
                    "input_tokens": int(usage.get("input_tokens", 0) or 0) if isinstance(usage, dict) and usage.get("input_tokens") is not None else None,
                    "answer_length": len(final_answer),
                },
            )
            return final_answer, usage

    async def _emit_final_answer(self, content: str, *, usage: dict[str, int] | None = None) -> None:
        bindings = self._bindings_or_raise()
        await bindings.runtime.emit(bindings.handle, "answer.started", AnswerRecord(content="", segment_index=bindings.runtime.current_segment_index(bindings.handle), final=False).to_dict())
        if content:
            await bindings.runtime.emit(bindings.handle, "answer.delta", AnswerRecord(content=content, segment_index=bindings.runtime.current_segment_index(bindings.handle), final=False).to_dict())
        await bindings.runtime.emit(bindings.handle, "answer.completed", AnswerRecord(content=content, segment_index=bindings.runtime.current_segment_index(bindings.handle), final=True, input_tokens=int(usage.get("input_tokens", 0) or 0) if isinstance(usage, dict) and usage.get("input_tokens") is not None else None, output_tokens=int(usage.get("output_tokens", 0) or 0) if isinstance(usage, dict) and usage.get("output_tokens") is not None else None).to_dict())

    def _explicit_capability_selection(self, message: str, allowed_tools: list[Any]) -> tuple[str, dict[str, str] | None]:
        normalized = str(message or "")
        if not any(pattern.search(normalized) for pattern in (*_EXPLICIT_MCP_PATTERNS, *_EXPLICIT_WEB_MCP_PATTERNS)):
            return "", None
        if any(pattern.search(normalized) for pattern in _REPEATED_MCP_PATTERNS):
            return "", None
        if len(allowed_tools) != 1 or not isinstance(allowed_tools[0], GovernedCapabilityTool):
            return "", None
        tool_name = str(getattr(allowed_tools[0], "name", "") or "")
        if tool_name not in _EXPLICIT_CAPABILITY_IDS:
            return "", None
        patterns = _FETCH_URL_PATTERNS
        key = "url"
        if tool_name == "mcp_filesystem_read_file":
            patterns, key = _READ_PATH_PATTERNS, "path"
        elif tool_name == "mcp_filesystem_list_directory":
            patterns, key = _LIST_PATH_PATTERNS, "path"
        for pattern in patterns:
            match = pattern.search(normalized)
            if match:
                return tool_name, {key: str(match.group(1)).strip().rstrip(".,;:")}
        return "", None

    async def _invoke_tool_path(self, *, state: GraphState, message: str, strategy: "ExecutionStrategy | None", skill_decision: SkillDecision | None, allowed_tools: list[Any]) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        if strategy is None:
            raise RuntimeError("capability path requires execution strategy")
        assembly = self._context_assembler.assemble(
            path_kind="capability_path",
            state=state,
            call_site="tool_agent",
        )
        turn_id = self._current_turn_id(state)
        tool_agent_call_id = self._record_model_call_snapshot(
            state=state,
            assembly=assembly,
            call_site="tool_agent",
            call_type="final_answer_call",
            turn_id=turn_id,
        )
        call_ids = self._context_call_ids(state, tool_agent_call_id)
        extra_instructions = list(assembly.extra_instructions)
        extra_instructions.extend(self._execution.tool_agent_instructions(strategy, skill_decision or SkillDecision(False, "", 0.0, "")))
        agent = self._execution.build_tool_agent(
            extra_instructions=extra_instructions,
            tools_override=allowed_tools,
        )
        messages = list(assembly.history_messages)
        messages.append({"role": "user", "content": message})
        final_parts: list[str] = []
        answer_segments: list[str] = []
        last_ai_message = ""
        last_streamed = ""
        pending_tools: dict[str, dict[str, str]] = {}
        recorded_tools: list[dict[str, str]] = []
        capability_results: list[dict[str, Any]] = []
        answer_started = False

        async for mode, payload in agent.astream({"messages": messages}, stream_mode=["messages", "updates"]):
            if mode == "messages":
                chunk, metadata = payload
                if metadata.get("langgraph_node") != "model":
                    continue
                text = _stringify_content(getattr(chunk, "content", ""))
                next_chunk = self._execution.incremental_stream_text(last_streamed, text)
                if text:
                    last_streamed = text
                if next_chunk:
                    if not answer_started:
                        await bindings.runtime.emit(bindings.handle, "answer.started", AnswerRecord(content="", segment_index=bindings.runtime.current_segment_index(bindings.handle), final=False).to_dict())
                        answer_started = True
                    final_parts.append(next_chunk)
                    answer_segments.append(next_chunk)
                    await bindings.runtime.emit(bindings.handle, "answer.delta", AnswerRecord(content=next_chunk, segment_index=bindings.runtime.current_segment_index(bindings.handle), final=False).to_dict())
                continue
            if mode != "updates":
                continue
            for update in payload.values():
                for agent_message in update.get("messages", []):
                    message_type = getattr(agent_message, "type", "")
                    tool_calls = getattr(agent_message, "tool_calls", []) or []
                    if message_type == "ai" and not tool_calls:
                        candidate = _stringify_content(getattr(agent_message, "content", ""))
                        if candidate:
                            last_ai_message = candidate
                    if tool_calls:
                        for tool_call in tool_calls:
                            call_id = str(tool_call.get("id") or tool_call.get("name"))
                            tool_name = str(tool_call.get("name", "tool"))
                            tool_input = tool_call.get("args", "")
                            if not isinstance(tool_input, str):
                                tool_input = json.dumps(tool_input, ensure_ascii=False)
                            pending_tools[call_id] = {"tool": tool_name, "input": str(tool_input)}
                            await bindings.runtime.emit(bindings.handle, "tool.started", ToolCallRecord(tool=tool_name, input=str(tool_input), call_id=call_id).to_dict())
                    if message_type == "tool":
                        tool_call_id = str(getattr(agent_message, "tool_call_id", ""))
                        pending = pending_tools.pop(tool_call_id, {"tool": getattr(agent_message, "name", "tool"), "input": ""})
                        output = _stringify_content(getattr(agent_message, "content", ""))
                        recorded_tools.append({"tool": pending["tool"], "input": pending["input"], "output": output, "call_id": tool_call_id})
                        structured_result = self._consume_captured_result(bindings.context, pending["tool"])
                        if structured_result is None:
                            structured_result = {"capability_id": pending["tool"], "call_id": tool_call_id, "status": "success", "payload": {"text": output}}
                        capability_results.append(structured_result)
                        await bindings.runtime.emit(bindings.handle, "tool.completed", ToolCallRecord(tool=pending["tool"], input=pending["input"], output=output, call_id=tool_call_id).to_dict())
                        bindings.runtime.advance_answer_segment(bindings.handle)
                        answer_started = False

        final_answer = "".join(final_parts).strip() or last_ai_message.strip()
        last_failure = extract_latest_failed_capability({"capability_results": capability_results})
        result = {
            "recorded_tools": recorded_tools,
            "capability_results": capability_results,
            "final_answer": final_answer,
            "answer_segments": answer_segments,
            "needs_answer_synthesis": self._execution.needs_tool_result_fallback(final_answer, recorded_tools),
            "answer_finalized": False,
            "error_state": None,
            "last_failure": last_failure.to_dict() if last_failure is not None else None,
            "recovery_action": "",
            "recovered_from_failure": False,
            "turn_id": turn_id,
            "context_call_ids": call_ids,
        }
        _payload, updates = self._write_context_snapshot(
            state=state,
            result=result,
            assembly=assembly,
            turn_id=turn_id,
            call_ids=call_ids,
        )
        return {**result, **updates}

    def _consume_captured_result(self, context: CapabilityRuntimeContext, capability_id: str) -> dict[str, Any] | None:
        for index, entry in enumerate(list(context.result_log)):
            if str(entry.get("capability_id", "") or "") == str(capability_id or ""):
                return context.result_log.pop(index)
        return None

    async def _stream_tool_result_fallback(self, *, state: GraphState, user_message: str, recorded_tools: list[dict[str, str]], strategy: "ExecutionStrategy | None") -> str:
        assembly = self._context_assembler.assemble(
            path_kind="capability_path",
            state=state,
            call_site="tool_result_fallback",
        )
        turn_id = self._current_turn_id(state)
        call_id = self._record_model_call_snapshot(
            state=state,
            assembly=assembly,
            call_site="tool_result_fallback",
            call_type="final_answer_call",
            turn_id=turn_id,
        )
        state["turn_id"] = turn_id
        state["context_call_ids"] = self._context_call_ids(state, call_id)
        fallback_messages = list(assembly.history_messages)
        fallback_messages.append({"role": "assistant", "content": self._execution.tool_results_context(recorded_tools)})
        fallback_messages = self._append_user_message(fallback_messages, user_message)
        instructions = [
            "The tool calls already succeeded. Do not call more tools.",
            "Answer the user's original request directly using the provided tool results.",
            "Your answer must be natural-language and user-facing, not an internal note.",
        ]
        instructions.extend(assembly.extra_instructions)
        if strategy is not None:
            instructions.extend(strategy.to_instructions())
        answer, _usage = await self._stream_model_answer(
            fallback_messages,
            extra_instructions=instructions,
            path_type="capability_path",
        )
        if answer:
            return answer
        fallback = "Based on the completed capability results, here is the consolidated answer:\n\n" + "\n\n".join(
            str(item.get("output", "")).strip()[:1200] for item in recorded_tools if str(item.get("output", "")).strip()
        )
        await self._emit_final_answer(fallback)
        return fallback

    def _current_turn_id(self, state: GraphState, *, segment_index: int | None = None) -> str:
        explicit = str(state.get("turn_id", "") or "").strip()
        if explicit:
            return explicit
        bindings = self._bindings_or_raise()
        run_id = str(state.get("run_id", "") or bindings.handle.run_id).strip()
        resolved_segment = bindings.runtime.current_segment_index(bindings.handle) if segment_index is None else int(segment_index)
        return f"{run_id}:{resolved_segment}"

    def _context_call_ids(self, state: GraphState, *extra: str) -> list[str]:
        ordered: list[str] = []
        for item in list(state.get("context_call_ids", []) or []):
            value = str(item or "").strip()
            if value and value not in ordered:
                ordered.append(value)
        for item in extra:
            value = str(item or "").strip()
            if value and value not in ordered:
                ordered.append(value)
        return ordered

    def _context_budget_report(self, assembly: ContextAssembly) -> dict[str, Any]:
        return {
            "allocated": assembly.budget.to_dict(),
            "used": dict(assembly.budget_used),
            "excluded_from_prompt": list(assembly.excluded_from_prompt),
        }

    def _run_context_meta(self, state: GraphState, *, assembly: ContextAssembly | None = None) -> dict[str, Any]:
        bindings = self._bindings_or_raise()
        checkpoint_meta = dict(state.get("checkpoint_meta", {}) or {})
        thread_id = str(state.get("thread_id", "") or state.get("session_id", "") or "").strip() or self._thread_id_for(bindings.handle)
        run_status = str(
            checkpoint_meta.get("run_status", "")
            or getattr(bindings.handle.metadata, "run_status", "")
            or ("recovery" if assembly is not None and assembly.path_kind == "recovery_path" else "fresh")
        )
        return {
            "thread_id": thread_id,
            "run_id": str(state.get("run_id", "") or bindings.handle.run_id).strip(),
            "session_id": str(state.get("session_id", "") or getattr(bindings.handle.metadata, "session_id", "") or "").strip() or None,
            "run_status": run_status,
            "resume_source": str(
                checkpoint_meta.get("resume_source", "")
                or getattr(bindings.handle.metadata, "resume_source", "")
                or self._resume_source
                or ""
            ),
            "checkpoint_id": str(
                checkpoint_meta.get("checkpoint_id", "")
                or getattr(bindings.handle.metadata, "checkpoint_id", "")
                or self._resume_checkpoint_id
                or ""
            ),
            "orchestration_engine": str(
                checkpoint_meta.get("orchestration_engine", "")
                or getattr(bindings.handle.metadata, "orchestration_engine", "")
                or "langgraph"
            ),
        }

    def _write_context_snapshot(
        self,
        *,
        state: GraphState,
        result: dict[str, Any] | None = None,
        assembly: ContextAssembly | None = None,
        turn_id: str | None = None,
        call_ids: list[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        bindings = self._bindings_or_raise()
        resolved_turn_id = str(turn_id or self._current_turn_id(state)).strip()
        payload = {
            **dict(state),
            **dict(result or {}),
            "turn_id": resolved_turn_id,
            "context_call_ids": list(call_ids if call_ids is not None else self._context_call_ids(state)),
        }
        if assembly is not None:
            payload["selected_memory_ids"] = list(assembly.decision.selected_memory_ids)
            payload["selected_artifact_ids"] = list(assembly.decision.selected_artifact_ids)
            payload["selected_evidence_ids"] = list(assembly.decision.selected_evidence_ids)
            payload["selected_conversation_ids"] = list(assembly.decision.selected_conversation_ids)
        updates = self._context_writer.snapshot(payload, updated_at=bindings.runtime.now())
        return payload, updates

    def _record_model_call_snapshot(
        self,
        *,
        state: GraphState,
        assembly: ContextAssembly,
        call_site: str,
        call_type: str,
        turn_id: str | None = None,
    ) -> str:
        bindings = self._bindings_or_raise()
        meta = self._run_context_meta(state, assembly=assembly)
        resolved_turn_id = str(turn_id or self._current_turn_id(state)).strip()
        call_id = f"{resolved_turn_id}:{call_site}"
        snapshot = ContextModelCallSnapshot(
            call_id=call_id,
            session_id=meta["session_id"],
            run_id=meta["run_id"],
            thread_id=meta["thread_id"],
            turn_id=resolved_turn_id,
            call_type=call_type,
            call_site=call_site,
            path_type=assembly.path_kind,
            user_query=str(state.get("user_message", "") or ""),
            context_envelope=assembly.envelope,
            assembly_decision=assembly.decision,
            budget_report=self._context_budget_report(assembly),
            selected_memory_ids=assembly.decision.selected_memory_ids,
            selected_artifact_ids=assembly.decision.selected_artifact_ids,
            selected_evidence_ids=assembly.decision.selected_evidence_ids,
            selected_conversation_ids=assembly.decision.selected_conversation_ids,
            dropped_items=assembly.decision.dropped_items,
            truncation_reason=assembly.decision.truncation_reason,
            run_status=meta["run_status"],
            resume_source=meta["resume_source"],
            checkpoint_id=meta["checkpoint_id"],
            orchestration_engine=meta["orchestration_engine"],
            created_at=bindings.runtime.now(),
        )
        try:
            context_store.record_context_model_call(snapshot)
        except Exception:
            return ""
        return call_id

    def _post_turn_state_snapshot(self, *, state: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        return {
            "working_memory": dict(updates.get("working_memory", {}) or {}),
            "episodic_summary": dict(updates.get("episodic_summary", {}) or {}),
            "checkpoint_meta": dict(updates.get("checkpoint_meta", {}) or state.get("checkpoint_meta", {}) or {}),
            "latest_consolidation": dict(updates.get("latest_consolidation", {}) or {}),
            "final_answer": str(state.get("final_answer", "") or ""),
            "answer_finalized": bool(state.get("answer_finalized", False)),
            "last_failure": dict(state.get("last_failure", {}) or {}),
            "recovery_action": str(state.get("recovery_action", "") or ""),
            "approval_decision": str(state.get("approval_decision", "") or ""),
        }

    def _record_post_turn_snapshot(
        self,
        *,
        state: GraphState,
        assembly: ContextAssembly,
        call_site: str,
        model_invoked: bool,
        updates: dict[str, Any],
        turn_id: str | None = None,
        call_ids: list[str] | None = None,
    ) -> None:
        bindings = self._bindings_or_raise()
        meta = self._run_context_meta(state, assembly=assembly)
        resolved_turn_id = str(turn_id or self._current_turn_id(state)).strip()
        segment_index = int(str(resolved_turn_id).rsplit(":", 1)[-1]) if ":" in resolved_turn_id else bindings.runtime.current_segment_index(bindings.handle)
        snapshot = ContextTurnSnapshot(
            turn_id=resolved_turn_id,
            session_id=meta["session_id"],
            run_id=meta["run_id"],
            thread_id=meta["thread_id"],
            assistant_message_id=None,
            segment_index=segment_index,
            call_site=call_site,
            path_type=assembly.path_kind,
            user_query=str(state.get("user_message", "") or ""),
            context_envelope=assembly.envelope,
            assembly_decision=assembly.decision,
            budget_report=self._context_budget_report(assembly),
            selected_memory_ids=assembly.decision.selected_memory_ids,
            selected_artifact_ids=assembly.decision.selected_artifact_ids,
            selected_evidence_ids=assembly.decision.selected_evidence_ids,
            selected_conversation_ids=assembly.decision.selected_conversation_ids,
            dropped_items=assembly.decision.dropped_items,
            truncation_reason=assembly.decision.truncation_reason,
            run_status=meta["run_status"],
            resume_source=meta["resume_source"],
            checkpoint_id=meta["checkpoint_id"],
            orchestration_engine=meta["orchestration_engine"],
            model_invoked=model_invoked,
            call_ids=tuple(call_ids if call_ids is not None else self._context_call_ids(state)),
            post_turn_state_snapshot=self._post_turn_state_snapshot(state=state, updates=updates),
            created_at=bindings.runtime.now(),
        )
        try:
            context_store.record_context_turn_snapshot(snapshot)
        except Exception:
            return

    def _memory_retrieve(self, message: str) -> list[dict[str, Any]]:
        from src.backend.runtime import executors as executors_module  # pylint: disable=import-outside-toplevel
        return executors_module.memory_indexer.retrieve(message, top_k=3)

    def _knowledge_astream(self, message: str):
        from src.backend.runtime import executors as executors_module  # pylint: disable=import-outside-toplevel
        return executors_module.knowledge_orchestrator.astream(message)
