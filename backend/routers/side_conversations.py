"""Side-conversation message API (creation lives on the ticket)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session

from backend.api.deps import side_conversation_payload
from backend.api.schemas import SideMessageCreate
from backend.database import get_db
from backend.models import SideConversation, User
from backend.security import OPS_ROLES, require_roles
from backend.services.side_conversations import send_side_message

router = APIRouter(prefix="/api/side-conversations", tags=["side-conversations"])


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: int,
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    conversation = db.get(SideConversation, conversation_id)
    if conversation is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Conversation not found")
    return side_conversation_payload(conversation)


@router.post("/{conversation_id}/messages", status_code=http_status.HTTP_201_CREATED)
def post_message(
    conversation_id: int,
    payload: SideMessageCreate,
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    conversation = db.get(SideConversation, conversation_id)
    if conversation is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Conversation not found")
    return send_side_message(db, conversation, user, content=payload.content)
