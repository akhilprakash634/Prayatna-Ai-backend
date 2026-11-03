import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base, SessionLocal
from models import KnowledgeDocument
from routes import chat, conversations, enquiries, knowledge, dashboard
from services.rag import rag_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("prayatna_backend")

# Create tables in SQLite
Base.metadata.create_all(bind=engine)

# Seed realistic Prayatna knowledge base data if the vector store is empty
INITIAL_PRAYATNA_KNOWLEDGE = [
    {
        "title": "Prayatna Centre for Child Development - Overview",
        "url": "https://prayatna.co.in/about-us",
        "chunks": [
            "Prayatna Centre for Child Development is a premier multi-disciplinary pediatric development center. Our mission is to empower children with developmental delays, neurodevelopmental conditions, and learning challenges to achieve their maximum potential in a nurturing, evidence-based clinical environment.",
            "Our holistic interdisciplinary team includes Developmental Pediatricians, Speech-Language Pathologists, Occupational Therapists, Clinical and Child Psychologists, Behavioral Therapists (ABA), Special Educators, and Pediatric Physiotherapists. We work closely with parents through family-centered interventions."
        ]
    },
    {
        "title": "Speech and Language Therapy",
        "url": "https://prayatna.co.in/services/speech-therapy",
        "chunks": [
            "Speech and Language Therapy at Prayatna focuses on evaluating and treating children with articulation disorders, expressive and receptive language delays, stuttering, childhood apraxia of speech, and social communication difficulties. Early intervention is crucial for toddlers and preschoolers showing speech delays.",
            "Our speech-language pathologists utilize play-based therapy, Augmentative and Alternative Communication (AAC) systems, oral motor exercises, and language enrichment strategies tailored to each child's individual developmental stage and communication goals."
        ]
    },
    {
        "title": "Occupational Therapy & Sensory Integration",
        "url": "https://prayatna.co.in/services/occupational-therapy",
        "chunks": [
            "Occupational Therapy (OT) at Prayatna helps children develop fine and gross motor skills, sensory processing capabilities, bilateral coordination, and independence in activities of daily living (ADLs) such as dressing, eating, and handwriting.",
            "Our specialized Sensory Integration (SI) gyms are equipped with suspended swings, textured tactile walls, obstacle courses, and therapeutic ball pits to help children with sensory modulation difficulties, hyper-reactivity, hypo-reactivity, and attention regulation."
        ]
    },
    {
        "title": "Behavior Therapy & ABA",
        "url": "https://prayatna.co.in/services/behavior-therapy",
        "chunks": [
            "Applied Behavior Analysis (ABA) and Behavior Modification therapy at Prayatna are designed to encourage positive behaviors, build communication and social reciprocity, and reduce interfering behaviors such as tantrums, aggression, or self-injury.",
            "Every behavior program begins with a functional behavior assessment (FBA) and involves structured parent training to ensure that skills acquired in the clinic generalize effectively to the home and school environments."
        ]
    },
    {
        "title": "Developmental and Psychological Assessments",
        "url": "https://prayatna.co.in/services/assessments",
        "chunks": [
            "Prayatna conducts comprehensive multidisciplinary assessments including developmental milestone evaluations, autism diagnostic observation schedules (ADOS/CARS), ADHD psychoeducational testing, IQ/cognitive assessments, and speech-language diagnostics.",
            "Assessments are conducted in an empathetic, child-friendly setting. Parents receive a detailed evaluation report with actionable recommendations, individualized education plans (IEP), and therapy roadmaps."
        ]
    },
    {
        "title": "Pediatric Physiotherapy & Special Education",
        "url": "https://prayatna.co.in/services/physiotherapy",
        "chunks": [
            "Pediatric Physiotherapy addresses motor milestones, muscle tone abnormalities (hypotonia/hypertonia), balance, posture, and gait rehabilitation for conditions such as cerebral palsy, torticollis, and developmental coordination disorder (DCD).",
            "Special Education and remedial instruction support children with specific learning disabilities (Dyslexia, Dyscalculia, Dysgraphia), helping them develop phonemic awareness, reading comprehension, mathematical concepts, and classroom adaptations."
        ]
    },
    {
        "title": "Appointments, Timings and Contact Information",
        "url": "https://prayatna.co.in/contact-us",
        "chunks": [
            "Prayatna Centre for Child Development operates Monday through Saturday from 9:00 AM to 7:00 PM. We offer both in-center sessions and secure online tele-therapy consultations for families residing outside our primary catchment area.",
            "To schedule a developmental screening or consultation, parents can submit an appointment enquiry through our website or assistant. Our intake coordinators contact families within 24 to 48 business hours to assign an initial clinical assessment slot."
        ]
    },
    {
        "title": "Payment Support & Fee Inquiries",
        "url": "https://prayatna.co.in/faq/payments",
        "chunks": [
            "Prayatna accepts secure digital payments including UPI, Net Banking, Debit/Credit Cards, and clinic receipts. If a payment is deducted from your bank account without immediate confirmation, banking networks typically reconcile within 24 to 48 hours.",
            "For payment receipts, billing discrepancies, or refund queries, parents can submit a Payment Support Enquiry with their name, transaction reference, and registered phone number. Our accounts desk reviews and responds within one business day."
        ]
    }
]

def seed_initial_knowledge():
    stats = rag_service.get_stats()
    if stats.get("total_chunks", 0) == 0:
        logger.info("Initializing vector store with Prayatna core knowledge...")
        db = SessionLocal()
        try:
            for item in INITIAL_PRAYATNA_KNOWLEDGE:
                import uuid
                doc_id = str(uuid.uuid4())
                rag_service.add_document_chunks(
                    document_id=doc_id,
                    chunks=item["chunks"],
                    source_title=item["title"],
                    source_url=item["url"],
                    source_type="seed_knowledge"
                )
                doc_record = KnowledgeDocument(
                    id=doc_id,
                    filename=item["title"],
                    source_type="website",
                    source_url=item["url"],
                    chunk_count=len(item["chunks"]),
                    status="indexed"
                )
                db.add(doc_record)
            db.commit()
            logger.info("Initial Prayatna knowledge base successfully seeded.")
        except Exception as e:
            logger.error(f"Error seeding initial knowledge: {e}")
            db.rollback()
        finally:
            db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    seed_initial_knowledge()
    yield
    # Shutdown actions

app = FastAPI(
    title="Prayatna AI API",
    description="Customer Support & Enquiry Assistant Backend for Prayatna Centre for Child Development",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration - dynamically configured via environment variables
cors_origins_env = os.getenv("ALLOWED_ORIGINS") or os.getenv("FRONTEND_URL", "*")
cors_regex_env = os.getenv("CORS_ORIGIN_REGEX")

if cors_regex_env:
    # Custom regex from .env (e.g. to match any subdomain: ^https?://([a-zA-Z0-9-]+\.)*yourdomain\.com(:[0-9]+)?$)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=cors_regex_env,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
elif cors_origins_env.strip() == "*":
    # Allow all origins via regex while supporting credentials and custom headers
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Specific comma-separated origins specified in .env
    allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )



# Attach API routers
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(enquiries.router)
app.include_router(knowledge.router)
app.include_router(dashboard.router)

@app.get("/health", tags=["system"])
def health_check():
    return {
        "status": "healthy",
        "service": "Prayatna AI Assistant",
        "rag_chunks": rag_service.get_stats().get("total_chunks", 0)
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
