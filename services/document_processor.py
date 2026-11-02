import os
import io
import re
from typing import List, Dict, Any, Tuple
from pypdf import PdfReader
import docx

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

def sanitize_filename(filename: str) -> str:
    """Sanitize the uploaded filename to prevent directory traversal attacks."""
    basename = os.path.basename(filename)
    # Strip dangerous characters
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", basename)
    # Ensure extension is preserved and valid
    name, ext = os.path.splitext(cleaned)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file extension: {ext}. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}")
    return cleaned

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> List[str]:
    """Chunk text by words with specified overlap."""
    words = text.split()
    if not words:
        return []
    
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk.strip())
        if i + chunk_size >= len(words):
            break
        i += (chunk_size - overlap)
    return chunks

class DocumentProcessor:
    @staticmethod
    def process_file(filename: str, file_bytes: bytes) -> Tuple[str, List[str]]:
        """Validate, extract text from PDF, DOCX, or TXT bytes, and return (cleaned_text, chunks)."""
        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File size exceeds limit of {MAX_FILE_SIZE_BYTES // (1024*1024)}MB")

        _, ext = os.path.splitext(filename.lower())
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"File type '{ext}' not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

        extracted_text = ""

        if ext == ".txt":
            try:
                extracted_text = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                extracted_text = file_bytes.decode("latin-1", errors="replace")

        elif ext == ".pdf":
            try:
                reader = PdfReader(io.BytesIO(file_bytes))
                pages_text = []
                for idx, page in enumerate(reader.pages):
                    pt = page.extract_text()
                    if pt:
                        pages_text.append(pt)
                extracted_text = "\n\n".join(pages_text)
            except Exception as e:
                raise ValueError(f"Failed to parse PDF document: {str(e)}")

        elif ext == ".docx":
            try:
                doc = docx.Document(io.BytesIO(file_bytes))
                paras = [p.text for p in doc.paragraphs if p.text.strip()]
                extracted_text = "\n\n".join(paras)
            except Exception as e:
                raise ValueError(f"Failed to parse DOCX document: {str(e)}")

        # Normalize whitespace
        cleaned = re.sub(r"\s+", " ", extracted_text).strip()
        if not cleaned:
            raise ValueError("No readable text found in document.")

        chunks = chunk_text(cleaned, chunk_size=450, overlap=70)
        return cleaned, chunks
