#!/usr/bin/env python3
"""
LDmicro Web Simulator - FastAPI Server

Text-export-only mode:
- Upload/compile LDmicro ladder text export
- Return simulation-ready JSON
"""

import os
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from interpreter import (
    transpile_unified,
    detect_format,
)


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="LDmicro Web Simulator",
    description="Simulate LDmicro ladder diagrams in your browser",
    version="1.0.0"
)

# CORS - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request/Response Models
# ============================================================================

class CompileRequest(BaseModel):
    """Request to compile LDmicro text export."""
    source_code: str


class CompileResponse(BaseModel):
    """Response from compilation."""
    success: bool
    message: str
    simulation: dict | None = None


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - serve the web UI."""
    static_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(static_path):
        return FileResponse(static_path)
    return {
        "message": "LDmicro Web Simulator API",
        "docs": "/docs",
        "endpoints": {
            "POST /api/compile": "Compile LDmicro text export to simulation JSON",
            "POST /api/upload": "Upload LDmicro text export file",
        }
    }


@app.post("/api/compile", response_model=CompileResponse)
async def compile_code(request: CompileRequest):
    """
    Compile LDmicro text export to simulation-ready JSON.
    """
    try:
        format_type = detect_format(request.source_code)
        if format_type != "ladder":
            return CompileResponse(
                success=False,
                message=(
                    "Only LDmicro text export is supported. "
                    "Use LDmicro 'Export As -> Text' and paste that content."
                ),
                simulation=None,
            )
        program = transpile_unified(request.source_code)

        return CompileResponse(
            success=True,
            message="Compilation successful (text export)",
            simulation=program.to_dict()
        )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return CompileResponse(
            success=False,
            message=f"Compilation error: {str(e)}",
            simulation=None
        )


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload an LDmicro text export file and compile it.
    """
    valid_extensions = ('.txt', '.ld')
    if not any(file.filename.endswith(ext) for ext in valid_extensions):
        raise HTTPException(
            status_code=400,
            detail="File must be .txt or .ld file (LDmicro text export)"
        )
    
    try:
        content = await file.read()
        source_code = content.decode('utf-8')

        format_type = detect_format(source_code)
        if format_type != "ladder":
            raise HTTPException(
                status_code=400,
                detail="Only LDmicro text export is supported",
            )
        program = transpile_unified(source_code)

        return {
            "success": True,
            "filename": file.filename,
            "format": format_type,
            "message": "File uploaded and compiled successfully (text export)",
            "simulation": program.to_dict()
        }
    
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="File must be UTF-8 encoded"
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Compilation error: {str(e)}"
        )


@app.get("/api/example")
async def get_example():
    """
    Get example LDmicro text export.
    """
    example_path = os.path.join(
        os.path.dirname(__file__),
        "examples",
        "simple_ladder.txt"
    )
    
    if not os.path.exists(example_path):
        raise HTTPException(
            status_code=404,
            detail="Example file not found"
        )
    
    with open(example_path, 'r') as f:
        source_code = f.read()
    
    return {
        "filename": "simple_ladder.txt",
        "source_code": source_code
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# ============================================================================
# Static Files (for frontend)
# ============================================================================

# Mount static files if the directory exists
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

