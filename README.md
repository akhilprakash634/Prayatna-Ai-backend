# Prayatna-Ai-backend

FastAPI & RAG backend for **Prayatna Centre for Child Development** ([prayatna.co.in](https://prayatna.co.in/)).

## 🌟 Key Features
- **Healthcare AI Chat Service**: Powered by Google Gemini (`google-genai` SDK, `gemini-3.8-flash`) with strict healthcare safety instructions (no diagnosis, no prescription, empathetic guidance).
- **RAG Knowledge Base**: Local vector storage with persistent ChromaDB and local `sentence-transformers/all-MiniLM-L6-v2` embeddings.
- **Same-Domain Web Crawler**: Crawls `prayatna.co.in` with SSRF protection against private IP ranges and cloud metadata endpoints.
- **Document Processor**: Extracts and chunks PDF (`pypdf`), Word (`python-docx`), and text files.
- **Lead Capture & SQLite Storage**: Automatically extracts and registers parent appointment enquiries and payment support tickets.
- **RESTful API**: Comprehensive endpoints for chat, conversations, enquiries, knowledge documents, and dashboard analytics.

## 🛠️ Tech Stack
- FastAPI & Uvicorn
- Pydantic v2 & SQLAlchemy (SQLite)
- ChromaDB & Sentence Transformers
- Google Gemini API (`google-genai`)
- PyPDF, python-docx, BeautifulSoup4

## 🚀 Getting Started

### 1. Setup Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash
DATABASE_URL=sqlite:///./data/prayatna.db
CHROMA_PATH=./data/chroma
FRONTEND_URL=http://localhost:3000
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-this-password
```

### 3. Run the Backend Server
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- API Documentation: `http://127.0.0.1:8000/docs`
- Health Check: `http://127.0.0.1:8000/health`
