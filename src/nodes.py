from .state import SunBridgeState
from typing import Any
import os
import fitz

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
            errors.append("FAIL: {msg}")
            updates[k] = None
            
        except Exception as e:
            msg = f"{label}: error reading PDF -- {e}"
            errors.append(msg)
            print(f"  FAIL: {msg}")
            updates[k] = None
        
    updates["errors"] = errors
    return updates

