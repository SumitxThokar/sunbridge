from .state import SunBridgeState
from .schemas import ExtractionResult
from .prompts import EXTRACTION_SYSTEM, EXTRACTION_USER
from typing import Any
import os
import fitz
from google import genai
from google.genai import types

from dotenv import load_dotenv
load_dotenv()

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
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash") 
    
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


def extract_pdf2_data(state: SunBridgeState) -> dict:
    print("\n> Step 3: Extracting PDF 2 data")
    return _extract_pdf_data(state, "pdf2_text", "pdf2_data", "extract_pdf2", "PDF 2")