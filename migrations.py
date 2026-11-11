import logging
import os
import secrets
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Base, engine, SessionLocal
from models import (
    ChatbotSetting,
    Conversation,
    Enquiry,
    KnowledgeDocument,
    Message,
    Organization,
    Subscription,
    User,
    utc_now,
)
from services.rag import rag_service
from services.security import hash_password
from services.tenant import PLAN_DEFAULTS, create_setup_token_for_user

logger = logging.getLogger(__name__)


def _existing_columns(db: Session, table_name: str) -> set[str]:
    rows = db.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def _ensure_column_and_index(db: Session, table_name: str, column_name: str, column_ddl: str) -> None:
    cols = _existing_columns(db, table_name)
    if column_name not in cols:
        logger.info("Adding column '%s' to table '%s'", column_name, table_name)
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}"))
        db.commit()

    idx_name = f"ix_{table_name}_{column_name}"
    db.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({column_name})"))
    db.commit()


def run_migrations() -> dict:
    """
    Idempotent SQLite + ChromaDB migration from single-tenant Prayatna to multi-tenant SaaS.
    Preserves 100% of existing conversations, messages, enquiries, documents, and Chroma vectors.
    """
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 1. Add tenant columns cleanly to existing SQLite tables if missing
        _ensure_column_and_index(db, "conversations", "organization_id", "VARCHAR(36)")
        _ensure_column_and_index(db, "conversations", "chatbot_id", "VARCHAR(100)")
        _ensure_column_and_index(db, "messages", "organization_id", "VARCHAR(36)")
        _ensure_column_and_index(db, "enquiries", "organization_id", "VARCHAR(36)")
        _ensure_column_and_index(db, "knowledge_documents", "organization_id", "VARCHAR(36)")

        # 2. Ensure Prayatna organization exists
        prayatna_org = db.query(Organization).filter(Organization.slug == "prayatna").first()
        if not prayatna_org:
            prayatna_org = Organization(
                name="Prayatna Centre for Child Development",
                slug="prayatna",
                website="https://prayatna.co.in/",
                industry="Healthcare / Child Development",
                status="active",
                plan="Enterprise",
            )
            db.add(prayatna_org)
            db.flush()
            logger.info("Created default organization '%s' (id=%s)", prayatna_org.slug, prayatna_org.id)

        # 3. Ensure Prayatna ChatbotSetting exists
        chatbot = (
            db.query(ChatbotSetting)
            .filter(ChatbotSetting.organization_id == prayatna_org.id)
            .first()
        )
        if not chatbot:
            chatbot = ChatbotSetting(
                organization_id=prayatna_org.id,
                chatbot_id="prayatna-bot",
                bot_name="Prayatna Virtual Assistant",
                assistant_name="Prayatna Support",
                welcome_message=(
                    "Namaste! Welcome to Prayatna Centre for Child Development. "
                    "I am your virtual assistant for speech therapy, occupational therapy, "
                    "ABA behavioral support, assessments, and appointments. How can I help your family today?"
                ),
                primary_color="#0d9488",
                knowledge_collection="org_prayatna",
                is_active=True,
            )
            db.add(chatbot)
            db.flush()

        # 4. Ensure Prayatna Subscription exists
        subscription = (
            db.query(Subscription)
            .filter(Subscription.organization_id == prayatna_org.id)
            .first()
        )
        if not subscription:
            plan_cfg = PLAN_DEFAULTS.get(prayatna_org.plan, PLAN_DEFAULTS["Enterprise"])
            now = utc_now()
            subscription = Subscription(
                organization_id=prayatna_org.id,
                plan_name=prayatna_org.plan,
                monthly_price=plan_cfg["monthly_price"],
                status="active",
                start_date=now,
                renewal_date=now + timedelta(days=30),
                conversation_limit=plan_cfg["conversation_limit"],
                ai_usage_limit=plan_cfg["ai_usage_limit"],
            )
            db.add(subscription)
            db.flush()

        # 5. Backfill all unowned legacy rows to Prayatna (idempotent)
        migrated_convs = (
            db.query(Conversation)
            .filter(Conversation.organization_id.is_(None))
            .update(
                {"organization_id": prayatna_org.id, "chatbot_id": chatbot.chatbot_id},
                synchronize_session=False,
            )
        )
        migrated_msgs = (
            db.query(Message)
            .filter(Message.organization_id.is_(None))
            .update({"organization_id": prayatna_org.id}, synchronize_session=False)
        )
        migrated_enqs = (
            db.query(Enquiry)
            .filter(Enquiry.organization_id.is_(None))
            .update({"organization_id": prayatna_org.id}, synchronize_session=False)
        )
        migrated_docs = (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.organization_id.is_(None))
            .update({"organization_id": prayatna_org.id}, synchronize_session=False)
        )
        db.commit()

        # 6. Ensure initial Super Admin user exists (never hardcodes passwords in code)
        super_admin = db.query(User).filter(User.role == "super_admin").first()
        if not super_admin:
            sa_email = os.getenv("SUPER_ADMIN_EMAIL", "superadmin@prayatna-saas.local").strip().lower()
            sa_name = os.getenv("SUPER_ADMIN_NAME", "Platform Super Admin").strip()
            env_sa_pw = os.getenv("SUPER_ADMIN_PASSWORD", "").strip()
            generated_sa_pw = env_sa_pw or secrets.token_urlsafe(14)

            super_admin = User(
                name=sa_name,
                email=sa_email,
                password_hash=hash_password(generated_sa_pw),
                role="super_admin",
                organization_id=None,
                status="active",
            )
            db.add(super_admin)
            db.flush()

            if not env_sa_pw:
                raw_setup = create_setup_token_for_user(db, super_admin.id, expires_hours=72)
                logger.warning(
                    "Created initial Super Admin '%s'. Set SUPER_ADMIN_PASSWORD env or complete setup via /setup-account?token=%s",
                    sa_email,
                    raw_setup,
                )
            else:
                logger.info("Seeded initial Super Admin '%s' from environment configuration.", sa_email)
            db.commit()

        # 7. Ensure initial Prayatna Client Admin user exists
        prayatna_admin = (
            db.query(User)
            .filter(User.organization_id == prayatna_org.id, User.role == "client_admin")
            .first()
        )
        if not prayatna_admin:
            pa_email = os.getenv("PRAYATNA_ADMIN_EMAIL", "admin@prayatna.co.in").strip().lower()
            pa_name = os.getenv("PRAYATNA_ADMIN_NAME", "Prayatna Admin").strip()
            env_pa_pw = (
                os.getenv("PRAYATNA_ADMIN_PASSWORD", "").strip()
                or os.getenv("ADMIN_PASSWORD", "").strip()
            )
            generated_pa_pw = env_pa_pw or secrets.token_urlsafe(14)

            prayatna_admin = User(
                name=pa_name,
                email=pa_email,
                password_hash=hash_password(generated_pa_pw),
                role="client_admin",
                organization_id=prayatna_org.id,
                status="active",
            )
            db.add(prayatna_admin)
            db.flush()

            if not env_pa_pw:
                raw_setup = create_setup_token_for_user(db, prayatna_admin.id, expires_hours=72)
                logger.warning(
                    "Created Prayatna Client Admin '%s'. Complete setup via /setup-account?token=%s",
                    pa_email,
                    raw_setup,
                )
            else:
                logger.info("Seeded Prayatna Client Admin '%s' for organization '%s'.", pa_email, prayatna_org.slug)
            db.commit()

        # 8. Migrate legacy ChromaDB vectors idempotently into Prayatna's isolated collection
        migrated_vectors = rag_service.migrate_legacy_collection(
            legacy_collection_name="prayatna_knowledge",
            target_org_slug=prayatna_org.slug,
            target_collection_name=chatbot.knowledge_collection,
        )

        return {
            "prayatna_org_id": prayatna_org.id,
            "chatbot_id": chatbot.chatbot_id,
            "migrated_conversations": migrated_convs,
            "migrated_messages": migrated_msgs,
            "migrated_enquiries": migrated_enqs,
            "migrated_documents": migrated_docs,
            "migrated_vectors": migrated_vectors,
        }
    finally:
        db.close()

