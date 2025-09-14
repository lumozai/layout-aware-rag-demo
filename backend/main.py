from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import shutil
import uuid
import logging
import traceback
from pathlib import Path
from dotenv import load_dotenv

from models import QueryRequest, QueryResponse
from docling_processor import DoclingProcessor
from neo4j_handler import Neo4jHandler
from citation_processor import CitationProcessor

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('../logs/backend.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Layout Aware RAG API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "../uploads"))
DOCUMENTS_DIR = Path(os.getenv("DOCUMENTS_DIR", "../documents"))
UPLOAD_DIR.mkdir(exist_ok=True)
DOCUMENTS_DIR.mkdir(exist_ok=True)

app.mount("/documents", StaticFiles(directory=str(DOCUMENTS_DIR)), name="documents")

docling_processor = DoclingProcessor()
neo4j_handler = Neo4jHandler()
citation_processor = CitationProcessor(neo4j_handler)


@app.on_event("startup")
async def startup_event():
    """Initialize database constraints and indexes"""
    neo4j_handler.setup_constraints_and_indexes()


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connection"""
    neo4j_handler.close()


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload and process a PDF file"""
    logger.info(f"Starting PDF upload: {file.filename}")

    if not file.filename.lower().endswith('.pdf'):
        logger.error(f"Invalid file type: {file.filename}")
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    doc_id = str(uuid.uuid4())
    filename = f"{doc_id}.pdf"
    upload_path = UPLOAD_DIR / filename
    documents_path = DOCUMENTS_DIR / filename

    try:
        logger.info(f"Saving uploaded file to: {upload_path}")
        with open(upload_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"File saved. Size: {upload_path.stat().st_size} bytes")

        logger.info(f"Copying file to documents directory: {documents_path}")
        shutil.copy2(upload_path, documents_path)

        logger.info("Starting Docling processing...")
        docling_data = docling_processor.parse_pdf_with_docling(str(upload_path))

        logger.info("Extracting document metadata...")
        doc_meta = docling_processor.extract_document_metadata(
            docling_data, doc_id, str(documents_path)
        )

        logger.info("Extracting page metadata...")
        pages_meta = docling_processor.extract_page_metadata(docling_data, doc_id)

        logger.info("Starting structure-aware chunking...")
        chunks = docling_processor.structure_aware_chunking(str(upload_path))

        logger.info(f"Storing {len(chunks)} chunks in Neo4j...")
        neo4j_handler.upsert_document(doc_meta, pages_meta, chunks)

        logger.info("Cleaning up temporary files...")
        upload_path.unlink()

        result = {
            "doc_id": doc_id,
            "title": doc_meta.title,
            "pages": len(pages_meta),
            "chunks": len(chunks),
            "message": "PDF processed successfully"
        }

        logger.info(f"Upload completed successfully. Document: {doc_meta.title}, Pages: {len(pages_meta)}, Chunks: {len(chunks)}")
        return result

    except Exception as e:
        error_msg = f"Processing failed: {str(e)}"
        logger.error(f"Upload failed for {file.filename}: {error_msg}")
        logger.error(f"Full traceback: {traceback.format_exc()}")

        # Clean up files on error
        if upload_path.exists():
            logger.info("Cleaning up upload file after error")
            upload_path.unlink()
        if documents_path.exists():
            logger.info("Cleaning up document file after error")
            documents_path.unlink()

        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    """Query documents and return answer with citations"""
    logger.info(f"Processing query: '{request.query}' with k={request.k}, limit={request.limit}, doc_type={request.doc_type}")

    try:
        logger.info("Generating query embedding...")
        query_embedding = docling_processor.get_embedding(request.query)
        logger.info(f"Query embedding generated: {len(query_embedding)} dimensions")

        logger.info("Starting vector search with Neo4j...")
        search_results = neo4j_handler.vector_search(
            query_embedding,
            k=request.k,
            doc_type=request.doc_type,
            limit=request.limit
        )

        logger.info(f"Vector search completed. Found {len(search_results)} results before limit")

        if not search_results:
            logger.warning("No search results found - returning empty response")
            return QueryResponse(
                answer="No relevant documents found for your query.",
                chunks=[],
                cited_chunks={}
            )

        logger.info(f"Processing {len(search_results)} search results for citation generation")
        # Log some details about the search results
        for i, result in enumerate(search_results[:3]):  # Log first 3 results
            chunk_text_preview = result.chunk['text'][:100] + "..." if len(result.chunk['text']) > 100 else result.chunk['text']
            logger.info(f"Result {i+1}: score={result.score:.3f}, chunk_id={result.chunk['id'][:8]}..., text_preview='{chunk_text_preview}'")

        logger.info("Generating answer with citations...")
        answer_with_citations = citation_processor.generate_answer_with_citations(
            request.query, search_results
        )

        logger.info("Extracting cited chunks...")
        cited_chunks = citation_processor.extract_cited_chunks(
            answer_with_citations, search_results
        )

        logger.info(f"Query completed successfully. Answer length: {len(answer_with_citations)} chars, Cited chunks: {len(cited_chunks)}")

        return QueryResponse(
            answer=answer_with_citations,
            chunks=search_results,
            cited_chunks=cited_chunks
        )

    except Exception as e:
        error_msg = f"Query failed: {str(e)}"
        logger.error(f"Query processing failed: {error_msg}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """Serve PDF documents"""
    doc_path = DOCUMENTS_DIR / f"{doc_id}.pdf"
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(doc_path, media_type="application/pdf")


@app.get("/viewer")
async def get_viewer():
    """Serve the PDF viewer with evidence pins"""
    viewer_path = Path(__file__).parent.parent / "frontend" / "viewer.html"
    return FileResponse(viewer_path, media_type="text/html")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)