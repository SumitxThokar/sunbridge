from .state import SunBridgeState
from .schemas import ExtractionResult, ReconciliationResult, GapAnalysisResult
from .prompts import (
    EXTRACTION_SYSTEM, EXTRACTION_USER,
    RECONCILIATION_SYSTEM, RECONCILIATION_USER,
    GAP_ANALYSIS_SYSTEM, GAP_ANALYSIS_USER,
    REPORT_SYSTEM, REPORT_USER,
)
from typing import Any
import os
import fitz
from google import genai
from google.genai import types
import json
from dotenv import load_dotenv
load_dotenv()
from groq import Groq

# extract text and tables form a single plage
def _read_page(page) -> str:
    plain_text = page.get_text("text")
    
    tabs = page.find_tables()
    
    if not tabs.tables:
        return plain_text
    
    formatted_tables = []
    for table in tabs.tables:
        rows = table.extract()
        if not rows:
            continue
        
        lines = []

        for i, row in enumerate(rows):
             cells = [str(cell or "").strip().replace("\n", " ") for cell in row]
             lines.append("| " + " | ".join(cells) + " |")
             if i == 0:
                lines.append("|" + "|".join(["---"] * len(cells)) + "|")
            
        formatted_tables.append("\n".join(lines))
        
    return plain_text + "\n\n" + "\n\n".join(formatted_tables)
    
def _read_pdf(path: str) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"PDF not found: {path}")
    
    doc = fitz.open(path)
    pages = []
    for i in range(len(doc)):
        pages.append(_read_page(doc[i]))
    doc.close()
    
    full_text = "\n\n".join(pages)
    
    return full_text

def _get_client() -> genai.Client:
    return genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

def _get_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3.5-flash") 
    

# def _get_client() -> Groq:
#     return Groq(api_key=os.environ["GROQ_API_KEY"])


# def _get_model() -> str:
#     return os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

def _call_llm_structured(
    client: genai.Client,
    schema: type,
    system_prompt: str,
    user_prompt: str,
    step_name: str,
) -> dict | None:
    try:
        response = client.models.generate_content(
            model=_get_model(),
            contents=user_prompt,
            config=types.GenerateContentConfig(   # ← typed config, not raw dict
                system_instruction=system_prompt,
                response_mime_type="application/json",  # ← flat key
                response_json_schema=schema.model_json_schema(),            # ← flat key, pass class directly
            ),
        )
        result = schema.model_validate_json(response.text)
        return result.model_dump()

    except Exception as e:
        print(f"  FAIL: {step_name}: {e}")
        return None

def _call_llm_text(
    client: genai.Client,
    system_prompt: str,
    user_prompt: str,
    step_name: str,
) -> str | None:
    """Call Gemini for free-form text output (e.g. markdown report)."""
    try:
        response = client.models.generate_content(
            model=_get_model(),
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
        )
        return response.text
    except Exception as e:
        print(f"  FAIL [{step_name}]: {e}")
        return None
    
# def _call_llm_structured(
#     client: Groq,
#     schema: type,
#     system_prompt: str,
#     user_prompt: str,
#     step_name: str,
# ) -> dict | None:
#     try:
#         response = client.chat.completions.create(
#             model=_get_model(),
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user",   "content": user_prompt},
#             ],
#             response_format={
#                 "type": "json_schema",
#                 "json_schema": {
#                     "name":   step_name,
#                     # strict: False — our schemas have optional (non-required) fields
#                     # which strict mode doesn't allow. Switch to True only after
#                     # making every Pydantic field required (use X | None in `required`).
#                     "strict": False,
#                     "schema": schema.model_json_schema(),
#                 },
#             },
#         )
#         raw = response.choices[0].message.content or "{}"
#         result = schema.model_validate_json(raw)
#         return result.model_dump()

    except Exception as e:
        print(f"  FAIL [{step_name}]: {e}")
        return None


def _extract_pdf_data(
    state: SunBridgeState,
    text_key: str,       # "pdf1_text" or "pdf2_text"
    data_key: str,       # "pdf1_data" or "pdf2_data"
    step_name: str,      # "extract_pdf1" or "extract_pdf2"
    label: str,          # "PDF 1" or "PDF 2"
) -> dict:

    errors = list(state.get("errors", []))
    text = state.get(text_key)

    if not text:
        msg = f"{label} text not available -- skipping extraction"
        errors.append(msg)
        print(f"  WARN: {msg}")
        return {
            data_key: None,
            "errors": errors,
            "steps_completed": state.get("steps_completed", []) + [step_name],
        }

    client = _get_client()
    result = _call_llm_structured(
        client,
        ExtractionResult,
        EXTRACTION_SYSTEM,
        EXTRACTION_USER.format(text=text),
        step_name,
    )

    if result:
        products = result.get("products", [])
        models = ", ".join(p["product_info"]["model_number"] for p in products)
        print(f"  OK: {label} extraction complete -- {len(products)} product(s): {models}")
    else:
        errors.append(f"{label} extraction failed")

    return {
        data_key: result,
        "errors": errors,
        "steps_completed": state.get("steps_completed", []) + [step_name],
    }
 

def _slim_for_reconciliation(data: dict) -> dict:
    """
    Strip nulls and verbose additional fields before sending to the reconciliation
    LLM. Keeps all named spec fields that have values, plus the additional dicts,
    but drops null-only keys so the prompt stays concise.
    """
    def drop_nulls(d: dict) -> dict:
        return {k: v for k, v in d.items() if v is not None and v != {} and v != []}

    slimmed_products = []
    for p in data.get("products", []):
        es  = p.get("electrical_specs", {})
        ms  = p.get("mechanical_specs", {})
        env = p.get("environmental_specs", {})
        pf  = p.get("protection_features", {})

        slimmed_products.append({
            "product_info":        drop_nulls(p.get("product_info", {})),
            "electrical_specs":    drop_nulls({k: v for k, v in es.items()  if k != "additional"}),
            "electrical_additional": es.get("additional", {}),
            "mechanical_specs":    drop_nulls({k: v for k, v in ms.items()  if k != "additional"}),
            "environmental_specs": drop_nulls({k: v for k, v in env.items() if k != "additional"}),
            "protection_features": drop_nulls({k: v for k, v in pf.items()  if k != "additional"}),
            "communication_interfaces": p.get("communication_interfaces", []),
        })

    return {
        "products":             slimmed_products,
        "certifications":       data.get("certifications", []),
        "compliance_standards": data.get("compliance_standards", {}),
        "other_data":           data.get("other_data", {}),
    }

def _slim_for_gap_analysis(data: dict) -> str:
    """
    For gap analysis we only need product_info + electrical/environmental specs
    per product, plus certifications. Keeps the prompt token count manageable
    when there are 20 products in one PDF.
    """
    slimmed = []
    for p in data.get("products", []):
        pi  = p.get("product_info", {})
        es  = p.get("electrical_specs", {})
        env = p.get("environmental_specs", {})
        slimmed.append({
            "model":               pi.get("model_number"),
            "rated_power_kw":      pi.get("rated_power_kw"),
            "ac_output_voltage":   es.get("ac_output_voltage"),
            "ac_output_frequency": es.get("ac_output_frequency"),
            "mppt_voltage_range":  es.get("mppt_voltage_range"),
            "peak_efficiency":     es.get("peak_efficiency"),
            "ip_rating":           env.get("ip_rating"),
            "operating_temp":      env.get("operating_temp_range"),
        })
    return json.dumps({
        "products":             slimmed,
        "certifications":       data.get("certifications", []),
        "compliance_standards": data.get("compliance_standards", {}),
    }, indent=2)

def _fallback_report(state: SunBridgeState) -> str:
    r      = state.get("reconciliation") or {}
    g      = state.get("gap_analysis")   or {}
    errors = state.get("errors", [])

    lines = [
        "# SunBridge Trading — Nepal Import Compliance Review (DRAFT)",
        "",
        "> **DRAFT NOTICE:** This document was partially generated due to pipeline errors.",
        "> Manual review required before sharing with Nepal import agent.",
        "",
        "## Pipeline Errors",
        *[f"- {e}" for e in errors],
        "",
        "## Overall Assessment",
        r.get("overall_assessment", "Unknown"),
        "",
        "## Inconsistencies Found",
        *[
            f"- **{i.get('field')}**: PDF1=`{i.get('pdf1_value')}` / PDF2=`{i.get('pdf2_value')}`"
            for i in r.get("inconsistent", [])
        ],
        "",
        "## Missing NEPQA Requirements",
        *[
            f"- [{m.get('severity','?').upper()}] **{m.get('requirement')}**: {m.get('details')}"
            for m in g.get("missing", [])
        ],
        "",
        "## Overall Readiness",
        g.get("overall_readiness", "Unknown"),
        "",
        g.get("readiness_note", ""),
    ]
    return "\n".join(lines)

  
# node 1
def load_documents(state: SunBridgeState) -> dict:

    errors = list(state.get("errors", []))
    updates: dict[str, Any] = {"steps_completed": state.get("steps_completed", []) + ["load_documents"]}
    
    for k, pk in [('pdf1_text','pdf1_path'),
                  ('pdf2_text','pdf2_path'),
                  ('nepqa_text','nepqa_path'),]:
        
        path = state.get(pk, "")
        label = pk.replace("_path","").upper()
        
        try: 
            text = _read_pdf(path)
            # print(text)
            updates[k]  = text
            print(f"OK: {label} loaded ({len(text):,} chars) -- {path}")
        
        except FileNotFoundError:
            msg = f"{label}: file not found at '{path}'"
            errors.append(f"FAIL: {msg}")
            print(f" FAIL: {msg}")
            updates[k] = None
            
        except Exception as e:
            msg = f"{label}: error reading PDF -- {e}"
            errors.append(msg)
            print(f"  FAIL: {msg}")
            updates[k] = None
        
    updates["errors"] = errors
    return updates

# Node 2
def extract_pdf1_data(state: SunBridgeState) -> dict:
    print("\n> Step 2: Extracting PDF 1 data")
    return _extract_pdf_data(state, "pdf1_text", "pdf1_data", "extract_pdf1", "PDF 1")

# Node 3
def extract_pdf2_data(state: SunBridgeState) -> dict:
    print("\n> Step 3: Extracting PDF 2 data")
    return _extract_pdf_data(state, "pdf2_text", "pdf2_data", "extract_pdf2", "PDF 2")

# node 4
def reconcile_sources(state: SunBridgeState) -> dict:

    errors    = list(state.get("errors", []))
    step_name = "reconcile"
    base_return = lambda result: {
        "reconciliation": result,
        "errors": errors,
        "steps_completed": state.get("steps_completed", []) + [step_name],
    }

    pdf1_data = state.get("pdf1_data")
    pdf2_data = state.get("pdf2_data")

    if not pdf1_data and not pdf2_data:
        msg = "Both PDF extractions failed — cannot reconcile"
        errors.append(msg)
        print(f"  FAIL: {msg}")
        return base_return(None)

    if not pdf1_data or not pdf2_data:
        available = "PDF 1" if pdf1_data else "PDF 2"
        msg = f"Only {available} extracted — skipping LLM reconciliation"
        errors.append(msg)
        print(f"  WARN: {msg}")
        return base_return({
            "product_matches":    [],
            "consistent":         [],
            "inconsistent":       [],
            "pdf1_only_fields":   [],
            "pdf2_only_fields":   [],
            "overall_assessment": "different_products",
            "assessment_reasoning": msg,
            "summary": f"Only {available} was available. Full reconciliation requires both PDFs.",
        })

    client = _get_client()
    result = _call_llm_structured(
        client,
        ReconciliationResult,
        RECONCILIATION_SYSTEM,
        RECONCILIATION_USER.format(
            pdf1_data=json.dumps(_slim_for_reconciliation(pdf1_data), indent=2),
            pdf2_data=json.dumps(_slim_for_reconciliation(pdf2_data), indent=2),
        ),
        step_name,
    )

    if result:
        n_ok   = len(result.get("consistent",   []))
        n_bad  = len(result.get("inconsistent", []))
        assessment = result.get("overall_assessment", "unknown")
        print(f"  OK: Reconciliation complete — {n_ok} consistent, {n_bad} inconsistent")
        print(f"  Assessment: {assessment}")

        critical = [i for i in result.get("inconsistent", []) if i.get("severity") == "critical"]
        if critical:
            print(f"  WARN: {len(critical)} CRITICAL inconsistenc{'y' if len(critical) == 1 else 'ies'}:")
            for c in critical:
                print(f"    • {c['field']}: PDF1={c.get('pdf1_value')!r}  PDF2={c.get('pdf2_value')!r}")
    else:
        msg = "Reconciliation LLM call failed"
        errors.append(msg)
        result = {
            "product_matches":    [],
            "consistent":         [],
            "inconsistent":       [],
            "pdf1_only_fields":   [],
            "pdf2_only_fields":   [],
            "overall_assessment": "minor_issues",
            "assessment_reasoning": "LLM call failed — no reconciliation performed",
            "summary": "Reconciliation failed due to an LLM error.",
        }

    return base_return(result)

# node 5
def analyze_nepqa_gaps(state: SunBridgeState) -> dict:
    print("\n> Step 5: Analysing gaps vs NEPQA 2025")
    errors    = list(state.get("errors", []))
    step_name = "gap_analysis"

    nepqa_text     = state.get("nepqa_text") or "(NEPQA 2025 document not available)"
    reconciliation = state.get("reconciliation") or {}
    pdf1_data      = state.get("pdf1_data") or {}
    pdf2_data      = state.get("pdf2_data") or {}

    client = _get_client()
    result = _call_llm_structured(
        client,
        GapAnalysisResult,
        GAP_ANALYSIS_SYSTEM,
        GAP_ANALYSIS_USER.format(
            nepqa_text=nepqa_text[:12_000],
            reconciliation_summary=reconciliation.get("summary", "Not available"),
            pdf1_data=_slim_for_gap_analysis(pdf1_data),
            pdf2_data=_slim_for_gap_analysis(pdf2_data),
            inconsistencies=json.dumps(reconciliation.get("inconsistent", []), indent=2),
        ),
        step_name,
    )

    if result:
        n_covered = len(result.get("covered", []))
        n_missing = len(result.get("missing", []))
        n_unclear = len(result.get("unclear", []))
        readiness = result.get("overall_readiness", "unknown")
        print(f"  OK: Gap analysis complete — {n_covered} covered, {n_missing} missing, {n_unclear} unclear")
        print(f"  Readiness: {readiness}")

        critical_missing = [m for m in result.get("missing", []) if m.get("severity") == "critical"]
        if critical_missing:
            print(f"  WARN: {len(critical_missing)} CRITICAL missing requirement(s):")
            for m in critical_missing:
                print(f"    • [{m.get('category')}] {m.get('requirement')}")
    else:
        msg = "Gap analysis LLM call failed"
        errors.append(msg)
        result = {
            "covered":  [],
            "missing":  [],
            "unclear":  [],
            "nepal_grid_compatibility": {"status": "unconfirmed"},
            "overall_readiness": "unknown",
            "readiness_note":    "Analysis failed due to an LLM error.",
            "recommendations":   [],
        }

    return {
        "gap_analysis": result,
        "errors": errors,
        "steps_completed": state.get("steps_completed", []) + [step_name],
    }
    
def generate_report(state: SunBridgeState) -> dict:
    print("\n> Step 6: Generating draft report")
    errors    = list(state.get("errors", []))
    step_name = "generate_report"

    reconciliation = state.get("reconciliation") or {}
    gap_analysis   = state.get("gap_analysis")   or {}

    client = _get_client()
    draft  = _call_llm_text(
        client,
        REPORT_SYSTEM,
        REPORT_USER.format(
            overall_assessment   = reconciliation.get("overall_assessment",   "unknown"),
            assessment_reasoning = reconciliation.get("assessment_reasoning", ""),
            consistent_count     = len(reconciliation.get("consistent",   [])),
            inconsistent_count   = len(reconciliation.get("inconsistent", [])),
            covered_count        = len(gap_analysis.get("covered",  [])),
            missing_count        = len(gap_analysis.get("missing",  [])),
            unclear_count        = len(gap_analysis.get("unclear",  [])),
            grid_compatibility   = gap_analysis.get("nepal_grid_compatibility", {}).get("status", "unconfirmed"),
            overall_readiness    = gap_analysis.get("overall_readiness", "unknown"),
            reconciliation_json  = json.dumps(reconciliation, indent=2)[:6_000],
            gap_analysis_json    = json.dumps(gap_analysis,   indent=2)[:6_000],
        ),
        step_name,
    )

    if draft:
        print("  OK: Draft report generated")
    else:
        msg = "Report generation failed — using fallback"
        errors.append(msg)
        print(f"  WARN: {msg}")
        draft = _fallback_report(state)

    return {
        "draft_report": draft,
        "errors": errors,
        "steps_completed": state.get("steps_completed", []) + [step_name],
    }


