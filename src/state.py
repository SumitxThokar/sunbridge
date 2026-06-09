# Plan: 

# 1. Load PDFs:  ins: pdf's path outs: pdf1_text, pdf2_text, nepqa_text
# 2. Extract PDF 1:  outs: structured pdf1_data,   
# 3. Extract PDF 2: outs: structured pdf2_data
# 4. Reconcile: outs: reconciliation
# 5. Gap Analysis: outs: gap analysis
# 6. Generate Report: outs: draft_report

from typing import TypedDict, List

class SunBridgeState(TypedDict):
    
    pdf1_path: str
    pdf2_path: str
    nepqa_path: str
    
    pdf1_text: str | None
    pdf2_text: str | None
    nepqa_text: str | None
    
    pdf1_data: dict| None
    pdf2_data: dict| None
    
    reconciliation: dict| None
    
    gap_analysis: dict| None
    
    draft_report: dict| None
    
    errors: List[str]
    steps_completed: List[str]
