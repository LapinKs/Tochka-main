from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from app.models_DB.users import User_db
from app.models import User
from app.db_manager import get_db
from uuid import UUID
from app.tools import validate_admin, verify_auth_token

router = APIRouter(prefix="/admin/user", tags=["user", "admin"])
@router.delete("/{user_id}", response_model=User)
async def delete_user(
    user_id: UUID,
    api_key: str = Depends(verify_auth_token),
    user: User_db = Depends(validate_admin),
    db: AsyncSession = Depends(get_db)
):
    user = await db.scalar(
        select(User_db).where(User_db.id == user_id)
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.execute(
        delete(User_db).where(User_db.id == user_id)
    )

    await db.commit()

    return user
