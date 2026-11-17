"""The agent's state graph (docs/agent-architecture.md).

    START -> agent -> (tool calls?) -> tools -> (consequential?) -> confirm [interrupt] -> agent
                 \\-> (final text) -> ground -> (ungrounded, 1 retry) -> agent
                 \\-> (step limit) -> fail_safe -> END

Invariants
- Every function_call gets exactly one function_result before the next model call.
- Consequential tools run only after interrupt() returns an approval. The confirm node has
  NO side effects before interrupt(), because LangGraph re-runs the whole node on resume
  (verified 2026-11-18: the node body ran twice).
- The final answer is checked deterministically: every job_id it mentions must have appeared in
  a tool result, and it may not claim a save or update that didn't succeed this turn.
"""

import operator
import re
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from app.domains.agent import tools as agent_tools
from app.domains.agent.prompts import SYSTEM_PROMPT
from app.integrations.llm.base import ToolCallingLLM

MAX_MODEL_CALLS = 6
MAX_GROUNDING_RETRIES = 1
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_SAVE_CLAIM = re.compile(
    r"\b(i(?:'ve| have)? saved|saved (?:it|this|the job)|added (?:it )?to your saved)", re.I
)
_PREF_CLAIM = re.compile(
    r"\b(i(?:'ve| have)? (?:updated|stored|remembered)|i'll remember|noted your preference"
    r"|preference (?:has been|is now|was) (?:updated|saved|stored))",
    re.I,
)


def _union(a: list[str], b: list[str]) -> list[str]:
    return sorted(set(a) | set(b))


class AgentState(TypedDict, total=False):
    history: Annotated[list[dict[str, Any]], operator.add]  # provider-neutral chat items
    seen_job_ids: Annotated[list[str], _union]  # job_ids returned by any tool, ever
    model_calls: int  # per turn
    pending: list[dict[str, Any]] | None  # consequential calls awaiting confirmation
    succeeded_actions: list[str]  # consequential tools that returned ok this turn
    grounding_retries: int
    final: dict[str, Any] | None
    trace: list[dict[str, Any]]  # tool calls this turn, for audit/evaluation


def turn_input(user_text: str) -> AgentState:
    """Input for a new user turn: appends the message and resets per-turn fields."""
    return {
        "history": [{"role": "user", "text": user_text}],
        "model_calls": 0,
        "pending": None,
        "succeeded_actions": [],
        "grounding_retries": 0,
        "final": None,
        "trace": [],
    }


def confirmation_summary(name: str, args: dict[str, Any]) -> str:
    if name == "save_job":
        return f"Save job {args.get('job_id')} to your saved jobs"
    if name == "update_candidate_preferences":
        return f"Set your '{args.get('key')}' preference to {args.get('value')}"
    return f"Run {name}"


def build_graph(
    llm: ToolCallingLLM,
    ctx: agent_tools.ToolContext,
    context_text: Callable[[], str],
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[Any, Any, Any, Any]:
    specs = [t.spec() for t in agent_tools.TOOLS.values()]

    def agent(state: AgentState) -> AgentState:
        turn = llm.chat(
            SYSTEM_PROMPT.format(context=context_text()), state.get("history", []), specs
        )
        item = {
            "role": "assistant",
            "text": turn.text,
            "raw": turn.raw,
            "tool_calls": [
                {"call_id": c.call_id, "name": c.name, "arguments": c.arguments}
                for c in turn.tool_calls
            ],
            "usage": {
                "input_tokens": turn.usage.input_tokens,
                "output_tokens": turn.usage.output_tokens,
                "latency_ms": turn.usage.latency_ms,
            },
        }
        return {"history": [item], "model_calls": state.get("model_calls", 0) + 1}

    def after_agent(state: AgentState) -> str:
        last = state["history"][-1]
        if last["tool_calls"]:
            return "fail_safe" if state.get("model_calls", 0) >= MAX_MODEL_CALLS else "tools"
        return "ground"

    def run_tools(state: AgentState) -> AgentState:
        results: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        trace = list(state.get("trace", []))
        seen: list[str] = []
        for call in state["history"][-1]["tool_calls"]:
            checked = agent_tools.validate_arguments(call["name"], call["arguments"])
            if isinstance(checked, dict):  # unknown tool or invalid arguments
                results.append(
                    {
                        "role": "tool",
                        "call_id": call["call_id"],
                        "name": call["name"],
                        "result": checked,
                    }
                )
                trace.append(
                    {
                        "tool": call["name"],
                        "arguments": call["arguments"],
                        "ok": False,
                        "error_code": checked["error_code"],
                    }
                )
                continue
            tool, args = checked
            if tool.consequential:
                pending.append(
                    {
                        "call_id": call["call_id"],
                        "name": tool.name,
                        "arguments": args.model_dump(mode="json"),
                    }
                )
                continue
            out = agent_tools.execute(tool, ctx, args)
            seen += sorted(agent_tools.job_ids_in(out))
            results.append(
                {"role": "tool", "call_id": call["call_id"], "name": tool.name, "result": out}
            )
            trace.append(
                {
                    "tool": tool.name,
                    "arguments": args.model_dump(mode="json"),
                    "ok": out["ok"],
                    "error_code": out.get("error_code"),
                }
            )
        return {
            "history": results,
            "pending": pending or None,
            "trace": trace,
            "seen_job_ids": seen,
        }

    def after_tools(state: AgentState) -> str:
        return "confirm" if state.get("pending") else "agent"

    def confirm(state: AgentState) -> AgentState:
        pending = state["pending"] or []
        # NO side effects above this line: the node re-runs from the top when resumed.
        decision = interrupt(
            {
                "actions": [
                    {
                        "tool": p["name"],
                        "arguments": p["arguments"],
                        "summary": confirmation_summary(p["name"], p["arguments"]),
                    }
                    for p in pending
                ]
            }
        )
        approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
        results, trace = [], list(state.get("trace", []))
        succeeded = list(state.get("succeeded_actions", []))
        seen: list[str] = []
        for p in pending:
            if approved:
                tool = agent_tools.TOOLS[p["name"]]
                out = agent_tools.execute(
                    tool, ctx, tool.input_model.model_validate(p["arguments"])
                )
                if out["ok"]:
                    succeeded.append(p["name"])
                seen += sorted(agent_tools.job_ids_in(out))
            else:
                out = {
                    "ok": False,
                    "error_code": "declined_by_user",
                    "message": "The user declined this action. It was not performed.",
                }
            results.append(
                {"role": "tool", "call_id": p["call_id"], "name": p["name"], "result": out}
            )
            trace.append(
                {
                    "tool": p["name"],
                    "arguments": p["arguments"],
                    "ok": out["ok"],
                    "error_code": out.get("error_code"),
                    "confirmed": approved,
                }
            )
        return {
            "history": results,
            "pending": None,
            "succeeded_actions": succeeded,
            "trace": trace,
            "seen_job_ids": seen,
        }

    def ground(state: AgentState) -> AgentState:
        text = state["history"][-1]["text"] or ""
        issues = check_grounding(
            text, set(state.get("seen_job_ids", [])), set(state.get("succeeded_actions", []))
        )
        if issues and state.get("grounding_retries", 0) < MAX_GROUNDING_RETRIES:
            correction = (
                "[Automatic check] Your last answer has problems: "
                + "; ".join(issues)
                + ". Answer again using only facts from tool results."
            )
            return {
                "history": [{"role": "user", "text": correction, "internal": True}],
                "grounding_retries": state.get("grounding_retries", 0) + 1,
            }
        return {"final": {"text": text, "grounded": not issues, "issues": issues}}

    def after_ground(state: AgentState) -> str:
        return END if state.get("final") else "agent"

    def fail_safe(state: AgentState) -> AgentState:
        # The last assistant message asked for tools we won't run: answer them, then stop.
        closing = [
            {
                "role": "tool",
                "call_id": c["call_id"],
                "name": c["name"],
                "result": {
                    "ok": False,
                    "error_code": "step_limit",
                    "message": "Not run: step limit.",
                },
            }
            for c in state["history"][-1]["tool_calls"]
        ]
        text = (
            "I couldn't finish that within my step limit. Could you narrow the request "
            "(for example a role, a city or a salary)?"
        )
        return {
            "history": closing,
            "final": {"text": text, "grounded": True, "issues": ["step_limit"]},
        }

    g = StateGraph(AgentState)
    for name, fn in (
        ("agent", agent),
        ("tools", run_tools),
        ("confirm", confirm),
        ("ground", ground),
        ("fail_safe", fail_safe),
    ):
        g.add_node(name, fn)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", after_agent, ["tools", "ground", "fail_safe"])
    g.add_conditional_edges("tools", after_tools, ["confirm", "agent"])
    g.add_edge("confirm", "agent")
    g.add_conditional_edges("ground", after_ground, ["agent", END])
    g.add_edge("fail_safe", END)
    return g.compile(checkpointer=checkpointer)


def check_grounding(text: str, seen_job_ids: set[str], succeeded_actions: set[str]) -> list[str]:
    issues = []
    unknown = sorted({m.lower() for m in _UUID.findall(text)} - {s.lower() for s in seen_job_ids})
    if unknown:
        issues.append(f"mentions job_id(s) not returned by any tool: {', '.join(unknown)}")
    if _SAVE_CLAIM.search(text) and "save_job" not in succeeded_actions:
        issues.append("claims a job was saved, but save_job did not succeed in this turn")
    if _PREF_CLAIM.search(text) and "update_candidate_preferences" not in succeeded_actions:
        issues.append(
            "claims a preference was stored, but update_candidate_preferences did not succeed"
        )
    return issues
