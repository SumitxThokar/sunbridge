import os
import shutil
import tempfile
import asyncio
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import uvicorn
from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from src.graph import build_pipeline

app = FastAPI(title="SunBridge — Nepal Solar PV Compliance")
templates = Jinja2Templates(directory="templates")
_executor = ThreadPoolExecutor(max_workers=2)

DEFAULT_PATHS = {
    "pdf1":  "docs/188_1115.pdf",
    "pdf2":  "docs/DSS_GZES230100125901_combined-1.pdf",
    "nepqa": "docs/nepal-photovoltaic-quality-assurance-2025-nepqa-2025.pdf",
}

def _run_pipeline(pdf1_path: str, pdf2_path: str, nepqa_path: str) -> dict:
    pipeline = build_pipeline()
    return pipeline.invoke({
        "pdf1_path":       pdf1_path,
        "pdf2_path":       pdf2_path,
        "nepqa_path":      nepqa_path,
        "pdf1_text":       None,
        "pdf2_text":       None,
        "nepqa_text":      None,
        "pdf1_data":       None,
        "pdf2_data":       None,
        "reconciliation":  None,
        "gap_analysis":    None,
        "draft_report":    None,
        "errors":          [],
        "steps_completed": [],
    })

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,                          
        name="index.html",
        context={"defaults": {k: Path(v).name for k, v in DEFAULT_PATHS.items()}},
    )


@app.post("/run")
async def run_analysis(
    pdf1:  Optional[UploadFile] = File(None),
    pdf2:  Optional[UploadFile] = File(None),
    nepqa: Optional[UploadFile] = File(None),
):
    tmp = []

    def save(upload: UploadFile) -> str:
        _, path = tempfile.mkstemp(suffix=".pdf")
        with open(path, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        tmp.append(path)
        return path

    p1 = save(pdf1)  if (pdf1  and pdf1.filename)  else DEFAULT_PATHS["pdf1"]
    p2 = save(pdf2)  if (pdf2  and pdf2.filename)  else DEFAULT_PATHS["pdf2"]
    pn = save(nepqa) if (nepqa and nepqa.filename) else DEFAULT_PATHS["nepqa"]

    try:
        loop   = asyncio.get_running_loop()
        result = await loop.run_in_executor(_executor, _run_pipeline, p1, p2, pn)
        payload = {k: v for k, v in result.items()
                   if k not in ("pdf1_text", "pdf2_text", "nepqa_text")}
        return JSONResponse({"status": "ok", "result": payload})

    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    finally:
        for path in tmp:
            try:
                os.unlink(path)
            except OSError:
                pass


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)