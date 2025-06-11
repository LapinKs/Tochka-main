from fastapi import HTTPException, Depends, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models_DB.users import User_db
from app.db_manager import get_db

auth_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_auth_token(token: str = Depends(auth_header)):
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing"
        )
    if not token.startswith("TOKEN "):
        raise HTTPException(status_code=401, detail="Api-key format is 'TOKEN <api_key>'")
    token = token.replace("TOKEN ", "")
    return token.strip()


async def fetch_authenticated_user(
        session: AsyncSession = Depends(get_db),
        token: str = Depends(verify_auth_token)
):
    user = await session.scalar(
        select(User_db).where(User_db.api_key == token)
    )


    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found"
        )

    return user


async def validate_admin(
        current_user: User_db = Depends(fetch_authenticated_user)
):
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required"
        )

    return current_user