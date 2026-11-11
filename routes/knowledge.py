import logging
import os
import uuid
from typing import List, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from database import get_db
from models import ChatbotSetting, KnowledgeDocument
from schemas import (
    KnowledgeDocumentResponse,
    KnowledgeTestRequest,
    KnowledgeTestResponse,
    KnowledgeTestResult,
    ScrapeRequest,
)
from services.document_processor import DocumentProcessor, sanitize_filename
from services.rag import rag_service
from services.scraper import WebsiteScraper, is_safe_url
from services.security import AuthContext, assert_org_access, require_client_admin
from services.tenant import record_usage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _get_org_rag_target(db: Session, ctx: AuthContext) -> Tuple[str, str]:
    org_slug = ctx.organization.slug if ctx.organization else "prayatna"
    setting = (
        db.query(ChatbotSetting)
        .filter(ChatbotSetting.organization_id == ctx.organization_id)
        .first()
    )
    collection_name = setting.knowledge_collection if setting else f"org_{org_slug.replace('-', '_')}"
    return org_slug, collection_name


@router.post("/scrape", response_model=List[KnowledgeDocumentResponse])
def scrape_website(
    payload: ScrapeRequest,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    url = payload.url.strip()
    if not is_safe_url(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL or restricted target IP address.",
        )

    try:
        scraper = WebsiteScraper(max_pages=25, delay=0.3)
        pages = scraper.scrape(url)
    except Exception as e:
        logger.error("Scraping failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Scraper failed while reading the target URL.",
        )

    if not pages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No readable web pages or text could be scraped from the specified URL.",
        )

    org_slug, collection_name = _get_org_rag_target(db, ctx)
    created_docs = []

    for page in pages:
        page_url = page["url"]
        page_title = page["title"]
        chunks = page["chunks"]

        existing_doc = (
            db.query(KnowledgeDocument)
            .filter(
                KnowledgeDocument.organization_id == ctx.organization_id,
                KnowledgeDocument.source_url == page_url,
            )
            .first()
        )
        if existing_doc:
            rag_service.delete_document_chunks(
                existing_doc.id,
                org_slug=org_slug,
                collection_name=collection_name,
            )
            doc_id = existing_doc.id
            doc_record = existing_doc
        else:
            doc_id = str(uuid.uuid4())
            doc_record = KnowledgeDocument(
                id=doc_id,
                organization_id=ctx.organization_id,
                filename=page_title[:100],
                source_type="website",
                source_url=page_url,
                chunk_count=0,
                status="processing",
            )
            db.add(doc_record)
            db.commit()

        chunk_count = rag_service.add_document_chunks(
            document_id=doc_id,
            chunks=chunks,
            source_title=page_title,
            source_url=page_url,
            source_type="website",
            org_slug=org_slug,
            collection_name=collection_name,
        )

        doc_record.chunk_count = chunk_count
        doc_record.status = "indexed"
        db.commit()
        db.refresh(doc_record)
        created_docs.append(doc_record)

    record_usage(db, ctx.organization_id, "website_scrape", len(created_docs), {"url": url})
    db.commit()
    return created_docs


@router.post("/upload", response_model=KnowledgeDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    try:
        clean_name = sanitize_filename(file.filename or "uploaded_file.txt")
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    org_slug, collection_name = _get_org_rag_target(db, ctx)

    existing_doc = (
        db.query(KnowledgeDocument)
        .filter(
            KnowledgeDocument.organization_id == ctx.organization_id,
            KnowledgeDocument.filename == clean_name,
            KnowledgeDocument.source_type != "website",
        )
        .first()
    )

    if existing_doc:
        rag_service.delete_document_chunks(
            existing_doc.id,
            org_slug=org_slug,
            collection_name=collection_name,
        )
        doc_id = existing_doc.id
        doc_record = existing_doc
    else:
        doc_id = str(uuid.uuid4())
        ext = os.path.splitext(clean_name)[1].lower().lstrip(".")
        doc_record = KnowledgeDocument(
            id=doc_id,
            organization_id=ctx.organization_id,
            filename=clean_name,
            source_type=ext or "document",
            source_url=None,
            chunk_count=0,
            status="processing",
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
            source_type="document",
            org_slug=org_slug,
            collection_name=collection_name,
        )
        doc_record.chunk_count = chunk_count
        doc_record.status = "indexed"
        record_usage(db, ctx.organization_id, "document_upload", 1, {"filename": clean_name})
        db.commit()
        db.refresh(doc_record)
        return doc_record
    except ValueError as ve:
        doc_record.status = "error"
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error("Error processing file %s: %s", clean_name, e)
        doc_record.status = "error"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document processing failed.",
        )


@router.get("/documents", response_model=List[KnowledgeDocumentResponse])
def list_documents(
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    return (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.organization_id == ctx.organization_id)
        .order_by(KnowledgeDocument.created_at.desc())
        .all()
    )


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    assert_org_access(doc.organization_id, ctx.organization_id, "Document")

    org_slug, collection_name = _get_org_rag_target(db, ctx)
    rag_service.delete_document_chunks(
        document_id,
        org_slug=org_slug,
        collection_name=collection_name,
    )

    db.delete(doc)
    db.commit()
    return {"message": "Document and associated vectors deleted successfully."}


@router.post("/test", response_model=KnowledgeTestResponse)
def test_knowledge(
    payload: KnowledgeTestRequest,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    query = payload.query.strip()
    org_slug, collection_name = _get_org_rag_target(db, ctx)
    results = rag_service.query(
        query,
        top_k=5,
        org_slug=org_slug,
        collection_name=collection_name,
    )

    test_results = [
        KnowledgeTestResult(
            content=r.get("content", ""),
            score=r.get("score"),
            metadata=r.get("metadata", {}),
        )
        for r in results
    ]

    return KnowledgeTestResponse(
        query=query,
        total_results=len(test_results),
        results=test_results,
    )
