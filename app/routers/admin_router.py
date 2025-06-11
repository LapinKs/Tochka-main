from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, delete
from re import match
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import (Body_deposit_api_v1_admin_balance_deposit_post, Body_withdraw_api_v1_admin_balance_withdraw_post,Instrument,Ok)
from app.models_DB.users import User_db
from app.models_DB.balances import Balance_db
from app.models_DB.instruments import Instrument_db
from app.db_manager import get_db
from app.tools import validate_admin, verify_auth_token

admin_router = APIRouter(prefix="/admin", tags=["admin"])
balance_router = APIRouter(prefix="/admin", tags=["balance","admin"])

@admin_router.post("/instrument", responses={200: {"model": Ok}})
async def add_instrument(
    instrument: Instrument,
    user: User_db = Depends(validate_admin),
    db: AsyncSession = Depends(get_db)
):
    instrument_find = await db.scalar(
        select(Instrument_db).where(Instrument_db.ticker == instrument.ticker)
    )

    if instrument_find:
        raise HTTPException(status_code=400, detail="Ticker must be unique")
    if not match('^[A-Z]{2,10}$', instrument.ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format")

    instrument_create = Instrument_db(
        name=instrument.name,
        ticker=instrument.ticker
    )
    db.add(instrument_create)
    await db.commit()
    return Ok()

@admin_router.delete("/instrument/{ticker}", response_model=Ok)
async def delete_instrument(
    ticker: str,
    user: User_db = Depends(validate_admin),
    db: AsyncSession = Depends(get_db)
):
    instrument_delete = await db.scalar(
        select(Instrument_db).where(Instrument_db.ticker == ticker)
    )

    if not instrument_delete:
        raise HTTPException(status_code=404, detail="Instrument not found")

    await db.execute(delete(Instrument_db).where(Instrument_db.ticker == ticker))
    await db.commit()
    # Нужно ли удалять order book при удалении
    return Ok()


@balance_router.post("/balance/deposit", response_model=Ok)
async def deposit(
        request: Body_deposit_api_v1_admin_balance_deposit_post,
        api_key: str = Depends(verify_auth_token),
        user: User_db = Depends(validate_admin),
        db: AsyncSession = Depends(get_db)
):
    user = await db.scalar(
        select(User_db).where(User_db.id == request.user_id)
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    balance = await db.scalar(
        select(Balance_db)
        .where(Balance_db.user_id == request.user_id, Balance_db.ticker == request.ticker)
    )

    if balance:
        balance.amount += request.amount
    else:
        balance = Balance_db(
            user_id=request.user_id,
            ticker=request.ticker,
            amount=request.amount
        )
        db.add(balance)

    await db.commit()

    return Ok()


@balance_router.post("/balance/withdraw", response_model=Ok)
async def withdraw(
        request: Body_withdraw_api_v1_admin_balance_withdraw_post,
        api_key: str = Depends(verify_auth_token),
        user: User_db = Depends(validate_admin),
        db: AsyncSession = Depends(get_db)
):
    user = await db.scalar(
        select(User_db).where(User_db.id == request.user_id)
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    balance = await db.scalar(
        select(Balance_db)
        .where(Balance_db.user_id == request.user_id, Balance_db.ticker == request.ticker)
    )

    if not balance or balance.amount < request.amount:
        raise HTTPException(status_code=400, detail="Not enough balance")

    balance.amount -= request.amount
    await db.commit()

    return Ok()