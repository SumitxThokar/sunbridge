# Plan: 

# 1. Load PDFs:  ins: pdf's path outs: pdf1_text, pdf2_text, nepqa_text
# 2. Extract PDF 1:  outs: structured pdf1_data,   
# 3. Extract PDF 2: outs: structured pdf2_data
# 4. Reconcile: outs: reconciliation
# 5. Gap Analysis: outs: gap analysis
# 6. Generate Report: outs: draft_report

from typing import TypedDict, Optional, List

class SunBridgeState(TypedDict):
    
    pdf1_path: str
    pdf2_path: str
    nepqa_path: str
    
    pdf1_text: Optional[str]
    pdf2_text: Optional[str]
    nepqa_text: Optional[str]
    
    pdf1_data: Optional[dict]
    pdf2_data: Optional[dict]
    
    reconciliation: Optional[dict]
    
    gap_analysis: Optional[dict]
    
    draft_report: Optional[str]
    
    errors: List[str]
    steps_completed: List[str]
