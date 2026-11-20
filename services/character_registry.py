import json
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from models import CharacterAsset

logger = logging.getLogger(__name__)

INITIAL_CHARACTER_GALLERY = [
    {
        "character_id": "buddy-robot",
        "name": "Buddy Robot",
        "category": "friendly",
        "description": "A friendly animated robot assistant with cheerful antenna and blinking LED eyes.",
        "animation_type": "lottie",
        "animation_url": "/characters/buddy-robot.json",
        "supported_animations": ["continuous", "idle", "greeting", "hover", "click"],
        "default_size": 64,
        "is_active": True,
        "display_order": 1,
    },
    {
        "character_id": "happy-assistant",
        "name": "Happy Assistant",
        "category": "friendly",
        "description": "A warm cheerful smiling assistant with rosy blush cheeks and playful bounce.",
        "animation_type": "lottie",
        "animation_url": "/characters/happy-assistant.json",
        "supported_animations": ["continuous", "idle", "greeting", "hover", "click"],
        "default_size": 64,
        "is_active": True,
        "display_order": 2,
    },
    {
        "character_id": "professional-bot",
        "name": "Professional Bot",
        "category": "professional",
        "description": "A sleek, sharp enterprise advisor with futuristic scanning visor display.",
        "animation_type": "lottie",
        "animation_url": "/characters/professional-bot.json",
        "supported_animations": ["continuous", "idle", "greeting", "hover", "click"],
        "default_size": 56,
        "is_active": True,
        "display_order": 3,
    },
    {
        "character_id": "smart-assistant",
        "name": "Smart Assistant",
        "category": "professional",
        "description": "An intelligent analytical assistant with precision orbital rings and neural core.",
        "animation_type": "lottie",
        "animation_url": "/characters/smart-assistant.json",
        "supported_animations": ["continuous", "idle", "greeting", "hover", "click"],
        "default_size": 56,
        "is_active": True,
        "display_order": 4,
    },
    {
        "character_id": "care-companion",
        "name": "Care Companion",
        "category": "healthcare",
        "description": "A warm, empathetic healthcare companion with rhythmic soothing heartbeat pulse.",
        "animation_type": "lottie",
        "animation_url": "/characters/care-companion.json",
        "supported_animations": ["continuous", "idle", "greeting", "hover", "click"],
        "default_size": 64,
        "is_active": True,
        "display_order": 5,
    },
    {
        "character_id": "healthcare-buddy",
        "name": "Healthcare Buddy",
        "category": "healthcare",
        "description": "A caring medical cross mascot with a friendly smile and protective emerald halo.",
        "animation_type": "lottie",
        "animation_url": "/characters/healthcare-buddy.json",
        "supported_animations": ["continuous", "idle", "greeting", "hover", "click"],
        "default_size": 64,
        "is_active": True,
        "display_order": 6,
    },
    {
        "character_id": "learning-mate",
        "name": "Learning Mate",
        "category": "education",
        "description": "An inspiring academic guide with a classic graduation mortarboard cap and tassel.",
        "animation_type": "lottie",
        "animation_url": "/characters/learning-mate.json",
        "supported_animations": ["continuous", "idle", "greeting", "hover", "click"],
        "default_size": 64,
        "is_active": True,
        "display_order": 7,
    },
    {
        "character_id": "study-companion",
        "name": "Study Companion",
        "category": "education",
        "description": "A curious wise owl assistant with round glasses and inquisitive head tilt.",
        "animation_type": "lottie",
        "animation_url": "/characters/study-companion.json",
        "supported_animations": ["continuous", "idle", "greeting", "hover", "click"],
        "default_size": 64,
        "is_active": True,
        "display_order": 8,
    },
    {
        "character_id": "minimal-orb",
        "name": "Minimal Orb",
        "category": "minimal",
        "description": "An elegant floating gradient AI sphere with smooth rotating cosmic particle rings.",
        "animation_type": "lottie",
        "animation_url": "/characters/minimal-orb.json",
        "supported_animations": ["continuous", "idle", "greeting", "hover", "click"],
        "default_size": 56,
        "is_active": True,
        "display_order": 9,
    },
    {
        "character_id": "floating-mascot",
        "name": "Floating Mascot",
        "category": "minimal",
        "description": "A modern minimalist teal diamond companion floating with breathing ground shadow.",
        "animation_type": "lottie",
        "animation_url": "/characters/floating-mascot.json",
        "supported_animations": ["continuous", "idle", "greeting", "hover", "click"],
        "default_size": 56,
        "is_active": True,
        "display_order": 10,
    },
]


def seed_character_gallery_if_needed(db: Session) -> int:
    """Ensure database has the initial character collection seeded."""
    count = db.query(CharacterAsset).count()
    if count > 0:
        return 0

    added = 0
    for item in INITIAL_CHARACTER_GALLERY:
        char_row = CharacterAsset(
            character_id=item["character_id"],
            name=item["name"],
            category=item["category"],
            description=item["description"],
            preview_image=item.get("preview_image"),
            animation_url=item["animation_url"],
            animation_type=item.get("animation_type", "lottie"),
            supported_animations=json.dumps(item.get("supported_animations", ["continuous", "idle", "greeting", "hover", "click"])),
            default_size=item.get("default_size", 56),
            is_active=item.get("is_active", True),
            display_order=item.get("display_order", 0),
        )
        db.add(char_row)
        added += 1

    db.commit()
    logger.info("Seeded %d character assets into database.", added)
    return added


def serialize_character_asset(char: CharacterAsset) -> Dict[str, Any]:
    """Serialize a CharacterAsset model instance to dictionary format."""
    supported = []
    if char.supported_animations:
        try:
            supported = json.loads(char.supported_animations)
        except Exception:
            supported = ["continuous", "idle", "greeting", "hover", "click"]
    else:
        supported = ["continuous", "idle", "greeting", "hover", "click"]

    return {
        "id": char.id,
        "character_id": char.character_id,
        "name": char.name,
        "category": char.category,
        "description": char.description,
        "preview_image": char.preview_image,
        "animation_url": char.animation_url,
        "animation_type": char.animation_type,
        "supported_animations": supported,
        "default_size": char.default_size,
        "is_active": char.is_active,
        "display_order": char.display_order,
        "created_at": char.created_at,
        "updated_at": char.updated_at,
    }
