from typing import TypedDict
from langgraph.graph import StateGraph, END
from agent.nodes import (
    classify_query, decompose_query, route_documents,
    retrieve, evaluate_relevance, rewrite_query,
    generate_answer, should_continue,
)


class SubQuestion(TypedDict):
    question: str
    search_query: str
    mode: str              # sql / vector
    company: str | None
    year: int | None
    report_ids: list       # resolved by route_documents from SQLite reports table
    vector_docs: list
    sql_results: list
    relevance_score: float
    status: str            # pending / done / rewriting / best_effort
    retry_count: int


class AgentState(TypedDict):
    question: str
    query_type: str        # simple / multihop / cross_document
    mode: str
    sub_questions: list
    final_answer: str
    sources: list[str]


def _route_after_classify(state: AgentState) -> str:
    if state["query_type"] == "simple":
        return "route_documents"
    return "decompose"


def _route_after_evaluate(state: AgentState) -> str:
    return should_continue(state)


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("classify",        classify_query)
    graph.add_node("decompose",       decompose_query)
    graph.add_node("route_documents", route_documents)
    graph.add_node("retrieve",        retrieve)
    graph.add_node("evaluate",        evaluate_relevance)
    graph.add_node("rewrite",         rewrite_query)
    graph.add_node("generate",        generate_answer)

    graph.set_entry_point("classify")

    graph.add_conditional_edges("classify", _route_after_classify, {
        "route_documents": "route_documents",
        "decompose":       "decompose",
    })

    graph.add_edge("decompose",       "route_documents")
    graph.add_edge("route_documents", "retrieve")
    graph.add_edge("retrieve",        "evaluate")

    graph.add_conditional_edges("evaluate", _route_after_evaluate, {
        "rewrite":  "rewrite",
        "generate": "generate",
    })

    graph.add_edge("rewrite",  "retrieve")
    graph.add_edge("generate", END)

    return graph.compile()


app_graph = build_graph()
