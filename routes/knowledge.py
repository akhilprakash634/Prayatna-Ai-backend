import os
import uuid
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from database import get_db
from models import KnowledgeDocument
from schemas import (
    ScrapeRequest,
    KnowledgeDocumentResponse,
    KnowledgeTestRequest,
    KnowledgeTestResponse,
    KnowledgeTestResult
)
from services.scraper import WebsiteScraper, is_safe_url
from services.document_processor import DocumentProcessor, sanitize_filename
from services.rag import rag_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

@router.post("/scrape", response_model=List[KnowledgeDocumentResponse])
def scrape_website(payload: ScrapeRequest, db: Session = Depends(get_db)):
    url = payload.url.strip()
    if not is_safe_url(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL or restricted target IP address."
        )

    try:
        scraper = WebsiteScraper(max_pages=25, delay=0.3)
        pages = scraper.scrape(url)
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Scraper error: {str(e)}")

    if not pages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No readable web pages or text could be scraped from the specified URL."
        )

    created_docs = []
    for page in pages:
        page_url = page["url"]
        page_title = page["title"]
        chunks = page["chunks"]

        # Check for existing document for this URL to prevent duplicate vectors
        existing_doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.source_url == page_url).first()
        if existing_doc:
            # Delete old vectors
            rag_service.delete_document_chunks(existing_doc.id)
            doc_id = existing_doc.id
            doc_record = existing_doc
        else:
            doc_id = str(uuid.uuid4())
            doc_record = KnowledgeDocument(
                id=doc_id,
                filename=page_title[:100],
                source_type="website",
                source_url=page_url,
                chunk_count=0,
                status="processing"
            )
            db.add(doc_record)
            db.commit()

        # Add chunks to ChromaDB
        chunk_count = rag_service.add_document_chunks(
            document_id=doc_id,
            chunks=chunks,
            source_title=page_title,
            source_url=page_url,
            source_type="website"
        )

        doc_record.chunk_count = chunk_count
        doc_record.status = "indexed"
        db.commit()
        db.refresh(doc_record)
        created_docs.append(doc_record)

    return created_docs

@router.post("/upload", response_model=KnowledgeDocumentResponse)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        clean_name = sanitize_filename(file.filename or "uploaded_file.txt")
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    # Read bytes
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    # Check for existing document with same filename
    existing_doc = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.filename == clean_name,
        KnowledgeDocument.source_type != "website"
    ).first()

    if existing_doc:
        rag_service.delete_document_chunks(existing_doc.id)
        doc_id = existing_doc.id
        doc_record = existing_doc
    else:
        doc_id = str(uuid.uuid4())
        ext = os.path.splitext(clean_name)[1].lower().lstrip(".")
        doc_record = KnowledgeDocument(
            id=doc_id,
            filename=clean_name,
            source_type=ext or "document",
            source_url=None,
            chunk_count=0,
            status="processing"
        )
        db.add(doc_record)
        db.commit()

    try:
        _, chunks = DocumentProcessor.process_file(clean_name, file_bytes)
        chunk_count = rag_service.add_document_chunks(
            document_id=doc_id,
            chunks=chunks,
            source_title=clean_name,
            source_url="Local Upload",
            source_type="document"
        )
        doc_record.chunk_count = chunk_count
        doc_record.status = "indexed"
        db.commit()
        db.refresh(doc_record)
        return doc_record
    except ValueError as ve:
        doc_record.status = "error"
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error processing file {clean_name}: {e}")
        doc_record.status = "error"
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document processing failed.")

@router.get("/documents", response_model=List[KnowledgeDocumentResponse])
def list_documents(db: Session = Depends(get_db)):
    return db.query(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()).all()

@router.delete("/documents/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Delete vectors from ChromaDB
    rag_service.delete_document_chunks(document_id)

    # Delete database record
    db.delete(doc)
    db.commit()
    return {"message": "Document and associated vectors deleted successfully."}

@router.post("/test", response_model=KnowledgeTestResponse)
def test_knowledge(payload: KnowledgeTestRequest):
    query = payload.query.strip()
    results = rag_service.query(query, top_k=5)

    test_results = [
        KnowledgeTestResult(
            content=r.get("content", ""),
            score=r.get("score"),
            metadata=r.get("metadata", {})
        )
        for r in results
    ]

    return KnowledgeTestResponse(
        query=query,
        total_results=len(test_results),
        results=test_results
    )
