from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.tools import verify_auth_token
from app.db_manager import get_db
from app.models_DB.users import User_db
from app.models_DB.balances import Balance_db


# Так как в двух разделах появляется
router = APIRouter(prefix="/balance", tags=["balance"])

@router.get("", response_model=Dict[str, float])
async def get_balances(api_key: str = Depends(verify_auth_token), db: AsyncSession = Depends(get_db)):
    user = await db.scalar(
        select(User_db).where(User_db.api_key == api_key)
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    balances_result = await db.execute(
        select(Balance_db).where(Balance_db.user_id == user.id)
    )
    balances = balances_result.scalars().all()
    response = {balance.ticker: balance.amount for balance in balances}
    return response

