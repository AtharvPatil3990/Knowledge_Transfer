from fastapi import APIRouter, HTTPException, status
from supabase_auth.errors import AuthApiError

from app.core.security import CurrentUser
from app.db.supabase_client import get_supabase_client
from app.models.auth import LoginRequest, RefreshRequest, SignUpRequest

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _auth_error(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=str(error) or "Authentication request failed.",
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: SignUpRequest):
    try:
        response = get_supabase_client().auth.sign_up({
            "email": payload.email,
            "password": payload.password,
            "options": {"data": {"full_name": payload.full_name}},
        })
    except AuthApiError as error:
        raise _auth_error(error) from error

    if not response.user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supabase did not create a user.",
        )
    return {"user": response.user, "session": response.session}


@router.post("/login")
def login(payload: LoginRequest):
    try:
        response = get_supabase_client().auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password,
        })
    except AuthApiError as error:
        raise _auth_error(error) from error

    if not response.session or not response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login did not return a valid session.",
        )
    return {"user": response.user, "session": response.session}


@router.post("/refresh")
def refresh(payload: RefreshRequest):
    try:
        response = get_supabase_client().auth.refresh_session(payload.refresh_token)
    except AuthApiError as error:
        raise _auth_error(error) from error

    if not response.session or not response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or expired.",
        )
    return {"user": response.user, "session": response.session}


@router.get("/me")
def me(user: CurrentUser):
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "role": user["role"],
    }
