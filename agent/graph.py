from langgraph.graph import END, StateGraph

from agent.db import create_checkpointer
from agent.nodes.forecast_node import forecast_node
from agent.nodes.notify_node import notify_node
from agent.nodes.po_draft_node import po_draft_node
from agent.nodes.risk_node import risk_node
from agent.nodes.sync_node import sync_node


def build_graph() -> StateGraph:
    workflow = StateGraph(dict)

    workflow.add_node("sync", sync_node)
    workflow.add_node("forecast", forecast_node)
    workflow.add_node("risk", risk_node)
    workflow.add_node("po_draft", po_draft_node)
    workflow.add_node("notify", notify_node)

    workflow.set_entry_point("sync")
    workflow.add_edge("sync", "forecast")
    workflow.add_edge("forecast", "risk")

    def has_risk_alerts(state: dict) -> str:
        alerts = state.get("risk_alerts", [])
        return "po_draft" if alerts else END

    workflow.add_conditional_edges("risk", has_risk_alerts, {
        "po_draft": "po_draft",
        END: END,
    })

    workflow.add_edge("po_draft", "notify")
    workflow.add_edge("notify", END)

    return workflow


async def get_compiled_graph():
    checkpointer = create_checkpointer()
    graph = build_graph()
    return graph.compile(checkpointer=checkpointer, interrupt_after=["po_draft"])
