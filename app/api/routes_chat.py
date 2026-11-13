from fastapi import APIRouter

from app.core.security import CurrentUser
from app.schemas.chat import ChatRequest
from app.services.rag_chatbot import generate_handover_response

router = APIRouter(prefix="/teams/{team_id}", tags=["Chat"])


@router.post("/chat")
async def chat(
    team_id: str,
    payload: ChatRequest,
    user: CurrentUser,
):
    response = await generate_handover_response(
        team_id=team_id,
        question=payload.question,
        token=user["access_token"],
    )
    return {"response": response}
