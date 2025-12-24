#!/usr/bin/env python3
"""
LDmicro Web Simulator - FastAPI Server

Provides endpoints for:
- Uploading and parsing LDmicro exports (C code OR ladder text)
- Getting simulation configuration

Supports both export formats from LDmicro:
1. C code export
2. Text ladder diagram export
"""

import os
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from interpreter import Lexer, transpile_unified, detect_format


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
    """Request to compile C code."""
    source_code: str


class CompileResponse(BaseModel):
    """Response from compilation."""
    success: bool
    message: str
    simulation: dict | None = None


class TokenInfo(BaseModel):
    """Token information for debugging."""
    type: str
    value: str
    line: int
    column: int


class LexerResponse(BaseModel):
    """Response from lexer (for debugging)."""
    success: bool
    tokens: list[TokenInfo]
    message: str = ""


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
            "POST /api/compile": "Compile C code to simulation JSON",
            "POST /api/upload": "Upload a C file",
            "POST /api/lex": "Tokenize C code (debug)",
        }
    }


@app.post("/api/compile", response_model=CompileResponse)
async def compile_code(request: CompileRequest):
    """
    Compile LDmicro export to simulation-ready JSON.
    
    Supports both formats:
    - C code export
    - Text ladder diagram export
    
    Auto-detects the format and parses accordingly.
    """
    try:
        # Detect format and transpile
        format_type = detect_format(request.source_code)
        program = transpile_unified(request.source_code)
        
        return CompileResponse(
            success=True,
            message=f"Compilation successful (detected: {format_type} format)",
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
    Upload an LDmicro export file and compile it.
    Supports .c (C code) and .txt (ladder diagram) files.
    """
    valid_extensions = ('.c', '.txt', '.ld')
    if not any(file.filename.endswith(ext) for ext in valid_extensions):
        raise HTTPException(
            status_code=400,
            detail="File must be .c, .txt, or .ld file"
        )
    
    try:
        content = await file.read()
        source_code = content.decode('utf-8')
        
        format_type = detect_format(source_code)
        program = transpile_unified(source_code)
        
        return {
            "success": True,
            "filename": file.filename,
            "format": format_type,
            "message": f"File uploaded and compiled successfully ({format_type} format)",
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


@app.post("/api/lex", response_model=LexerResponse)
async def lex_code(request: CompileRequest):
    """
    Tokenize C code (for debugging).
    Returns the list of tokens.
    """
    try:
        lexer = Lexer(request.source_code)
        tokens = lexer.tokenize()
        
        token_info = [
            TokenInfo(
                type=t.type.name,
                value=t.value,
                line=t.line,
                column=t.column
            )
            for t in tokens
        ]
        
        return LexerResponse(
            success=True,
            tokens=token_info
        )
    
    except Exception as e:
        return LexerResponse(
            success=False,
            tokens=[],
            message=f"Lexer error: {str(e)}"
        )


@app.get("/api/example")
async def get_example():
    """
    Get example LDmicro C code.
    """
    example_path = os.path.join(
        os.path.dirname(__file__),
        "examples",
        "simple_ladder.c"
    )
    
    if not os.path.exists(example_path):
        raise HTTPException(
            status_code=404,
            detail="Example file not found"
        )
    
    with open(example_path, 'r') as f:
        source_code = f.read()
    
    return {
        "filename": "simple_ladder.c",
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

