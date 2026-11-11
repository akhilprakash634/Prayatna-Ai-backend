import logging
import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from migrations import run_migrations  # noqa: E402
from models import ChatbotSetting, KnowledgeDocument, Organization  # noqa: E402
from database import SessionLocal  # noqa: E402
from routes import auth, chat, client_settings, conversations, dashboard, enquiries, knowledge, super_admin  # noqa: E402
from services.rag import rag_service  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("prayatna_backend")

# Seed Prayatna knowledge base ONLY if Prayatna org has zero indexed docs and zero chunks
INITIAL_PRAYATNA_KNOWLEDGE = [
    {
        "title": "Prayatna Centre for Child Development - Overview",
        "url": "https://prayatna.co.in/about-us",
        "chunks": [
            "Prayatna Centre for Child Development is a premier multi-disciplinary pediatric development center. Our mission is to empower children with developmental delays, neurodevelopmental conditions, and learning challenges to achieve their maximum potential in a nurturing, evidence-based clinical environment.",
            "Our holistic interdisciplinary team includes Developmental Pediatricians, Speech-Language Pathologists, Occupational Therapists, Clinical and Child Psychologists, Behavioral Therapists (ABA), Special Educators, and Pediatric Physiotherapists. We work closely with parents through family-centered interventions.",
        ],
    },
    {
        "title": "Speech and Language Therapy",
        "url": "https://prayatna.co.in/services/speech-therapy",
        "chunks": [
            "Speech and Language Therapy at Prayatna focuses on evaluating and treating children with articulation disorders, expressive and receptive language delays, stuttering, childhood apraxia of speech, and social communication difficulties. Early intervention is crucial for toddlers and preschoolers showing speech delays.",
            "Our speech-language pathologists utilize play-based therapy, Augmentative and Alternative Communication (AAC) systems, oral motor exercises, and language enrichment strategies tailored to each child's individual developmental stage and communication goals.",
        ],
    },
    {
        "title": "Occupational Therapy & Sensory Integration",
        "url": "https://prayatna.co.in/services/occupational-therapy",
        "chunks": [
            "Occupational Therapy (OT) at Prayatna helps children develop fine and gross motor skills, sensory processing capabilities, bilateral coordination, and independence in activities of daily living (ADLs) such as dressing, eating, and handwriting.",
            "Our specialized Sensory Integration (SI) gyms are equipped with suspended swings, textured tactile walls, obstacle courses, and therapeutic ball pits to help children with sensory modulation difficulties, hyper-reactivity, hypo-reactivity, and attention regulation.",
        ],
    },
    {
        "title": "Behavior Therapy & ABA",
        "url": "https://prayatna.co.in/services/behavior-therapy",
        "chunks": [
            "Applied Behavior Analysis (ABA) and Behavior Modification therapy at Prayatna are designed to encourage positive behaviors, build communication and social reciprocity, and reduce interfering behaviors such as tantrums, aggression, or self-injury.",
            "Every behavior program begins with a functional behavior assessment (FBA) and involves structured parent training to ensure that skills acquired in the clinic generalize effectively to the home and school environments.",
        ],
    },
    {
        "title": "Developmental and Psychological Assessments",
        "url": "https://prayatna.co.in/services/assessments",
        "chunks": [
            "Prayatna conducts comprehensive multidisciplinary assessments including developmental milestone evaluations, autism diagnostic observation schedules (ADOS/CARS), ADHD psychoeducational testing, IQ/cognitive assessments, and speech-language diagnostics.",
            "Assessments are conducted in an empathetic, child-friendly setting. Parents receive a detailed evaluation report with actionable recommendations, individualized education plans (IEP), and therapy roadmaps.",
        ],
    },
    {
        "title": "Pediatric Physiotherapy & Special Education",
        "url": "https://prayatna.co.in/services/physiotherapy",
        "chunks": [
            "Pediatric Physiotherapy addresses motor milestones, muscle tone abnormalities (hypotonia/hypertonia), balance, posture, and gait rehabilitation for conditions such as cerebral palsy, torticollis, and developmental coordination disorder (DCD).",
            "Special Education and remedial instruction support children with specific learning disabilities (Dyslexia, Dyscalculia, Dysgraphia), helping them develop phonemic awareness, reading comprehension, mathematical concepts, and classroom adaptations.",
        ],
    },
    {
        "title": "Appointments, Timings and Contact Information",
        "url": "https://prayatna.co.in/contact-us",
        "chunks": [
            "Prayatna Centre for Child Development operates Monday through Saturday from 9:00 AM to 7:00 PM. We offer both in-center sessions and secure online tele-therapy consultations for families residing outside our primary catchment area.",
            "To schedule a developmental screening or consultation, parents can submit an appointment enquiry through our website or assistant. Our intake coordinators contact families within 24 to 48 business hours to assign an initial clinical assessment slot.",
        ],
    },
    {
        "title": "Payment Support & Fee Inquiries",
        "url": "https://prayatna.co.in/faq/payments",
        "chunks": [
            "Prayatna accepts secure digital payments including UPI, Net Banking, Debit/Credit Cards, and clinic receipts. If a payment is deducted from your bank account without immediate confirmation, banking networks typically reconcile within 24 to 48 hours.",
            "For payment receipts, billing discrepancies, or refund queries, parents can submit a Payment Support Enquiry with their name, transaction reference, and registered phone number. Our accounts desk reviews and responds within one business day.",
        ],
    },
]


def seed_initial_knowledge():
    if os.getenv("SKIP_INITIAL_KB_SEED", "").lower() == "true":
        return

    db = SessionLocal()
    try:
        prayatna_org = db.query(Organization).filter(Organization.slug == "prayatna").first()
        if not prayatna_org:
            return
        setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == prayatna_org.id).first()
        coll_name = setting.knowledge_collection if setting else "org_prayatna"

        existing_docs = (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.organization_id == prayatna_org.id)
            .count()
        )
        stats = rag_service.get_stats(org_slug="prayatna", collection_name=coll_name)

        if existing_docs == 0 and stats.get("total_chunks", 0) == 0:
            logger.info("Initializing Prayatna isolated vector store with core knowledge...")
            for item in INITIAL_PRAYATNA_KNOWLEDGE:
                doc_id = str(uuid.uuid4())
                rag_service.add_document_chunks(
                    document_id=doc_id,
                    chunks=item["chunks"],
                    source_title=item["title"],
                    source_url=item["url"],
                    source_type="seed_knowledge",
                    org_slug="prayatna",
                    collection_name=coll_name,
                )
                doc_record = KnowledgeDocument(
                    id=doc_id,
                    organization_id=prayatna_org.id,
                    filename=item["title"],
                    source_type="website",
                    source_url=item["url"],
                    chunk_count=len(item["chunks"]),
                    status="indexed",
                )
                db.add(doc_record)
            db.commit()
            logger.info("Initial Prayatna knowledge base successfully seeded.")
    except Exception as e:
        logger.error("Error seeding initial knowledge: %s", e)
        db.rollback()
    finally:
        db.close()


# Run schema migrations safely before serving requests
run_migrations()


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    seed_initial_knowledge()

    try:
        from services.embeddings import embedding_service
        embedding_service.embed_query("Prayatna Centre child development")
        logger.info("Embedding service pre-warmed successfully.")
    except Exception as e:
        logger.warning("Embedding warmup warning: %s", e)

    try:
        from services.gemini import gemini_service
        gemini_service._init_client()
        logger.info("Gemini service initialized at startup.")
    except Exception as e:
        logger.warning("Gemini client warmup warning: %s", e)

    yield


app = FastAPI(
    title="Prayatna Multi-Tenant AI SaaS API",
    description="Multi-tenant AI Customer Support & Enquiry Platform",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS configuration:
# Authenticated portal calls route through Next.js same-origin proxy (/api/*);
# Explicit ALLOWED_ORIGINS allow credentialed CORS if configured; otherwise public embeds run uncredentialed.
cors_origins_env = os.getenv("ALLOWED_ORIGINS") or os.getenv("FRONTEND_URL", "")
if cors_origins_env and cors_origins_env.strip() != "*":
    allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Attach API routers
app.include_router(auth.router)
app.include_router(super_admin.router)
app.include_router(client_settings.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(enquiries.router)
app.include_router(knowledge.router)
app.include_router(dashboard.router)


@app.get("/health", tags=["system"])
def health_check():
    stats = rag_service.get_stats(org_slug="prayatna", collection_name="org_prayatna")
    return {
        "status": "healthy",
        "service": "Prayatna Multi-Tenant AI SaaS",
        "mode": "multi_tenant_saas",
        "rag_chunks": stats.get("total_chunks", 0),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
