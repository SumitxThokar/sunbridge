from langgraph.graph import StateGraph, END

from .state import SunBridgeState
from .nodes import (
    load_documents,
    extract_pdf1_data,
    extract_pdf2_data,
    reconcile_sources,
    analyze_nepqa_gaps,
    generate_report,
)

def build_pipeline():
    workflow = StateGraph(SunBridgeState)
    workflow.add_node("load_documents",  load_documents)
    workflow.add_node("extract_pdf1",    extract_pdf1_data)
    workflow.add_node("extract_pdf2",    extract_pdf2_data)
    workflow.add_node("reconcile",       reconcile_sources)
    workflow.add_node("gap_analysis",    analyze_nepqa_gaps)
    workflow.add_node("generate_report", generate_report)
    
    workflow.set_entry_point("load_documents")
    workflow.add_edge("load_documents",  "extract_pdf1")
    workflow.add_edge("extract_pdf1",    "extract_pdf2")
    workflow.add_edge("extract_pdf2",    "reconcile")
    workflow.add_edge("reconcile",       "gap_analysis")
    workflow.add_edge("gap_analysis",    "generate_report")
    workflow.add_edge("generate_report", END)
    return workflow.compile()


def get_graph_mermaid() -> str:
    app = build_pipeline()
    return app.get_graph().draw_mermaid()
