"""python examples/before_demo.py

Same pipeline as demo.py but built with LangGraph and no FailSafe.
Data flows between agents with zero validation — secrets leak,
required fields go missing, and nothing stops it.
"""

from typing import TypedDict
from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    query: str
    sources: list[str]
    summary: str
    api_key: str       # secret that should never leak
    draft: str
    review: str


def research_agent(state: State) -> dict:
    return {
        "query": state.get("query", ""),
        "sources": state.get("sources", []),
        "summary": state.get("summary", ""),
        "api_key": state.get("api_key", ""),  # leaks silently
    }


def writer_agent(state: State) -> dict:
    if not state.get("sources"):
        # no sources — writer has nothing to work with, but graph keeps going
        return {"draft": ""}
    return {"draft": f"Draft about: {state['query']}. Sources: {', '.join(state['sources'])}"}


def review_agent(state: State) -> dict:
    if not state.get("draft"):
        return {"review": "Nothing to review — draft was empty"}
    return {"review": f"Approved: {state['draft'][:60]}..."}


graph = StateGraph(State)
graph.add_node("research", research_agent)
graph.add_node("writer", writer_agent)
graph.add_node("review", review_agent)
graph.add_edge(START, "research")
graph.add_edge("research", "writer")
graph.add_edge("writer", "review")
graph.add_edge("review", END)
app = graph.compile()

# --- run the same scenarios as demo.py ---

# clean handoff
r1 = app.invoke({"query": "AI safety", "sources": ["arxiv.org/1234", "arxiv.org/5678"], "summary": "Overview of recent alignment research"})
print(f"research → writer → review:  OK — {r1['review'][:60]}")

# leaking secrets — goes through with no warning
r2 = app.invoke({"query": "AI safety", "sources": ["arxiv.org/1234"], "api_key": "sk-secret-123"})
print(f"research → writer → review:  OK — api_key '{r2['api_key']}' leaked to every agent")

# missing required field — no one catches it
r3 = app.invoke({"query": "AI safety"})
print(f"research → writer → review:  OK — draft is empty, review says: '{r3['review']}'")
