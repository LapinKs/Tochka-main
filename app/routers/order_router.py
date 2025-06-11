from datetime import datetime
from typing import List, Union, Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from dateutil.tz import tzlocal
from uuid import uuid4, UUID
from sqlalchemy import select, cast, String
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.exc import IntegrityError, DBAPIError

from app.models_DB.users import User_db
from app.models_DB.limit_orders import LimitOrder_db
from app.models_DB.market_orders import MarketOrder_db
from app.models_DB.orderbook import OrderBook_db
from app.models_DB.transactions import Transaction_db
from app.models_DB.balances import Balance_db
from app.models import LimitOrderRequest, LimitOrder, MarketOrder, MarketOrderRequest, CreateOrderResponse, Direction, OrderState, Ok
from app.db_manager import get_db
from app.tools import verify_auth_token

router = APIRouter(prefix="/order", tags=["order"])


@router.post("", responses={200: {"model": CreateOrderResponse}})
async def create_order(
        order_body: LimitOrderRequest | MarketOrderRequest,
        api_key: str = Depends(verify_auth_token),
        db: AsyncSession = Depends(get_db)
):
    async with db.begin():
        try:
            user = await db.scalar(select(User_db).where(User_db.api_key == api_key))
            if not user:
                raise HTTPException(status_code=404, detail="User account not found")

            # Проверка и резервирование средств
            if order_body.direction == "SELL":
                balance = await db.scalar(
                    select(Balance_db).where(
                        Balance_db.user_id == user.id,
                        Balance_db.ticker == order_body.ticker
                    )
                )
                if balance is None or balance.amount < order_body.qty:
                    raise HTTPException(status_code=400, detail="Inappropriate balance for SELL order")
            elif order_body.direction == "BUY" and isinstance(order_body, LimitOrderRequest):
                rub_balance = await db.scalar(
                    select(Balance_db).where(
                        Balance_db.user_id == user.id,
                        Balance_db.ticker == "RUB"
                    )
                )
                total_cost = order_body.qty * order_body.price
                if rub_balance is None or rub_balance.amount < total_cost:
                    raise HTTPException(status_code=400, detail="Inappropriate RUB balance for BUY order")

            # Создание записи ордера
            order_id = uuid4()
            if isinstance(order_body, LimitOrderRequest):
                order = LimitOrder_db(
                    id=order_id,
                    status=OrderState.NEW,
                    user_id=user.id,
                    timestamp=datetime.now(),
                    direction=order_body.direction,
                    ticker=order_body.ticker,
                    qty=order_body.qty,
                    price=order_body.price,
                    filled=0
                )
            else:
                order = MarketOrder_db(
                    id=order_id,
                    status=OrderState.NEW,
                    user_id=user.id,
                    timestamp=datetime.now(),
                    direction=order_body.direction,
                    ticker=order_body.ticker,
                    qty=order_body.qty
                )
            db.add(order)
            await db.flush()

            # Получение или создание стакана
            orderbook = await db.scalar(
                select(OrderBook_db).where(OrderBook_db.ticker == order_body.ticker)
            )
            if not orderbook:
                orderbook = OrderBook_db(
                    ticker=order_body.ticker,
                    bid_levels=[],
                    ask_levels=[]
                )
                db.add(orderbook)
                await db.flush()

            # Исполнение ордера
            if isinstance(order_body, MarketOrderRequest):
                # Код исполнения рыночного ордера
                is_buy = order.direction == "BUY"
                levels = orderbook.ask_levels if is_buy else orderbook.bid_levels

                total_available_qty = sum(level["qty"] for level in levels)
                if total_available_qty < order.qty:
                    order.filled = 0
                    order.status = OrderState.NEW
                else:
                    remaining_qty = order.qty
                    executed_qty = 0
                    executed_levels = []

                    for level in levels:
                        if remaining_qty <= 0:
                            break

                        price = level["price"]
                        trade_qty = min(level["qty"], remaining_qty)
                        remaining_qty -= trade_qty
                        executed_qty += trade_qty

                        buyer_id = order.user_id if is_buy else UUID(level["user_id"])
                        seller_id = UUID(level["user_id"]) if is_buy else order.user_id

                        # Создание транзакции
                        transaction = Transaction_db(
                            ticker=order.ticker,
                            amount=trade_qty,
                            price=price,
                            timestamp=datetime.now(tzlocal())
                        )
                        db.add(transaction)
                        # Обновление балансов
                        total_cost = trade_qty * price

                        # Баланс RUB покупателя
                        buyer_rub_balance = await db.scalar(
                            select(Balance_db).where(
                                Balance_db.user_id == buyer_id,
                                Balance_db.ticker == "RUB"
                            )
                        )
                        if buyer_rub_balance is None:
                            buyer_rub_balance = Balance_db(user_id=buyer_id, ticker="RUB", amount=-total_cost)
                        else:
                            buyer_rub_balance.amount -= total_cost
                        db.add(buyer_rub_balance)

                        # Баланс актива покупателя
                        buyer_asset_balance = await db.scalar(
                            select(Balance_db).where(
                                Balance_db.user_id == buyer_id,
                                Balance_db.ticker == order.ticker
                            )
                        )
                        if buyer_asset_balance is None:
                            buyer_asset_balance = Balance_db(user_id=buyer_id, ticker=order.ticker, amount=trade_qty)
                        else:
                            buyer_asset_balance.amount += trade_qty
                        db.add(buyer_asset_balance)

                        # Баланс актива продавца
                        seller_asset_balance = await db.scalar(
                            select(Balance_db).where(
                                Balance_db.user_id == seller_id,
                                Balance_db.ticker == order.ticker
                            )
                        )
                        if seller_asset_balance is None:
                            seller_asset_balance = Balance_db(user_id=seller_id, ticker=order.ticker, amount=-trade_qty)
                        else:
                            seller_asset_balance.amount -= trade_qty
                        db.add(seller_asset_balance)

                        # Баланс RUB продавца
                        seller_rub_balance = await db.scalar(
                            select(Balance_db).where(
                                Balance_db.user_id == seller_id,
                                Balance_db.ticker == "RUB"
                            )
                        )
                        if seller_rub_balance is None:
                            seller_rub_balance = Balance_db(user_id=seller_id, ticker="RUB", amount=total_cost)
                        else:
                            seller_rub_balance.amount += total_cost
                        db.add(seller_rub_balance)

                        if is_buy:
                            level["reserved_funds"] -= trade_qty * price
                        else:
                            level["reserved_funds"] -= trade_qty
                        level["reserved_funds"] = max(level["reserved_funds"], 0)

                        level["qty"] -= trade_qty

                        if "order_id" in level:
                            matched_order_id = UUID(level["order_id"])
                            matched_order = await db.get(LimitOrder_db, matched_order_id)
                            if matched_order:
                                matched_order.filled += trade_qty
                                if matched_order.filled >= matched_order.qty:
                                    matched_order.status = OrderState.EXECUTED
                                else:
                                    matched_order.status = OrderState.PARTIALLY_EXECUTED
                                db.add(matched_order)

                        if level["qty"] <= 0:
                            executed_levels.append(level)

                    for level in executed_levels:
                        levels.remove(level)

                    if is_buy:
                        orderbook.ask_levels = levels
                        flag_modified(orderbook, "ask_levels")
                    else:
                        orderbook.bid_levels = levels
                        flag_modified(orderbook, "bid_levels")

                    order.filled = executed_qty
                    order.status = OrderState.EXECUTED
            else:
                # Код исполнения лимитного ордера
                levels = orderbook.ask_levels if order.direction == "BUY" else orderbook.bid_levels
                is_buy = order.direction == "BUY"

                matched_qty = 0
                remaining_qty = order.qty
                executed_levels = []

                for level in levels:
                    if remaining_qty <= 0:
                        break

                    level_price = level["price"]
                    if (is_buy and level_price > order.price) or (not is_buy and level_price < order.price):
                        break

                    trade_qty = min(remaining_qty, level["qty"])
                    remaining_qty -= trade_qty
                    matched_qty += trade_qty

                    buyer_id = order.user_id if is_buy else UUID(level["user_id"])
                    seller_id = UUID(level["user_id"]) if is_buy else order.user_id

                    # Создание транзакции
                    transaction = Transaction_db(
                        ticker=order.ticker,
                        amount=trade_qty,
                        price=level_price,
                        timestamp=datetime.now(tzlocal())
                    )
                    db.add(transaction)
                    # Обновление балансов
                    total_cost = trade_qty * level_price

                    # Баланс RUB покупателя
                    buyer_rub_balance = await db.scalar(
                        select(Balance_db).where(
                            Balance_db.user_id == buyer_id,
                            Balance_db.ticker == "RUB"
                        )
                    )
                    if buyer_rub_balance is None:
                        buyer_rub_balance = Balance_db(user_id=buyer_id, ticker="RUB", amount=-total_cost)
                    else:
                        buyer_rub_balance.amount -= total_cost
                    db.add(buyer_rub_balance)

                    # Баланс актива покупателя
                    buyer_asset_balance = await db.scalar(
                        select(Balance_db).where(
                            Balance_db.user_id == buyer_id,
                            Balance_db.ticker == order.ticker
                        )
                    )
                    if buyer_asset_balance is None:
                        buyer_asset_balance = Balance_db(user_id=buyer_id, ticker=order.ticker, amount=trade_qty)
                    else:
                        buyer_asset_balance.amount += trade_qty
                    db.add(buyer_asset_balance)

                    # Баланс актива продавца
                    seller_asset_balance = await db.scalar(
                        select(Balance_db).where(
                            Balance_db.user_id == seller_id,
                            Balance_db.ticker == order.ticker
                        )
                    )
                    if seller_asset_balance is None:
                        seller_asset_balance = Balance_db(user_id=seller_id, ticker=order.ticker, amount=-trade_qty)
                    else:
                        seller_asset_balance.amount -= trade_qty
                    db.add(seller_asset_balance)

                    # Баланс RUB продавца
                    seller_rub_balance = await db.scalar(
                        select(Balance_db).where(
                            Balance_db.user_id == seller_id,
                            Balance_db.ticker == "RUB"
                        )
                    )
                    if seller_rub_balance is None:
                        seller_rub_balance = Balance_db(user_id=seller_id, ticker="RUB", amount=total_cost)
                    else:
                        seller_rub_balance.amount += total_cost
                    db.add(seller_rub_balance)

                    if is_buy:
                        level["reserved_funds"] -= trade_qty
                    else:
                        level["reserved_funds"] -= trade_qty * level_price
                    level["reserved_funds"] = max(level["reserved_funds"], 0)

                    level["qty"] -= trade_qty
                    if level["qty"] <= 0:
                        executed_levels.append(level)

                        if "order_id" in level:
                            matched_order_id = UUID(level["order_id"])
                            matched_order = await db.get(LimitOrder_db, matched_order_id)
                            if matched_order:
                                matched_order.filled = matched_order.qty
                                matched_order.status = OrderState.EXECUTED
                                db.add(matched_order)
                    else:
                        if "order_id" in level:
                            matched_order_id = UUID(level["order_id"])
                            matched_order = await db.get(LimitOrder_db, matched_order_id)
                            if matched_order:
                                matched_order.filled += trade_qty
                                matched_order.status = OrderState.PARTIALLY_EXECUTED
                                db.add(matched_order)

                for lvl in executed_levels:
                    levels.remove(lvl)

                if is_buy:
                    orderbook.ask_levels = levels
                    flag_modified(orderbook, "ask_levels")
                else:
                    orderbook.bid_levels = levels
                    flag_modified(orderbook, "bid_levels")

                order.filled = matched_qty

                if matched_qty == 0:
                    order.status = OrderState.NEW
                    # Добавление в стакан
                    qty_left = order.qty
                    reserved_funds = qty_left * order.price if order.direction == "BUY" else qty_left

                    new_level = {
                        "price": order.price,
                        "qty": qty_left,
                        "user_id": str(order.user_id),
                        "order_id": str(order.id),
                        "reserved_funds": reserved_funds
                    }

                    levels = orderbook.bid_levels if order.direction == "BUY" else orderbook.ask_levels

                    # Объединение уровней
                    merged = False
                    for level in levels:
                        if (
                                level["price"] == new_level["price"] and
                                level.get("user_id") == new_level.get("user_id") and
                                level.get("order_id") == new_level.get("order_id")
                        ):
                            level["qty"] += new_level["qty"]
                            for key in ["reserved_rub", "reserved_funds"]:
                                if key in new_level:
                                    level[key] = level.get(key, 0) + new_level.get(key, 0)
                            merged = True
                            break

                    if not merged:
                        levels.append(new_level)

                    if order.direction == "BUY":
                        orderbook.bid_levels = sorted(levels, key=lambda x: -x["price"])
                        flag_modified(orderbook, "bid_levels")
                    else:
                        orderbook.ask_levels = sorted(levels, key=lambda x: x["price"])
                        flag_modified(orderbook, "ask_levels")
                elif remaining_qty == 0:
                    order.status = OrderState.EXECUTED
                else:
                    order.status = OrderState.PARTIALLY_EXECUTED
                    # Добавление в стакан оставшегося количества
                    qty_left = remaining_qty
                    reserved_funds = qty_left * order.price if order.direction == "BUY" else qty_left

                    new_level = {
                        "price": order.price,
                        "qty": qty_left,
                        "user_id": str(order.user_id),
                        "order_id": str(order.id),
                        "reserved_funds": reserved_funds
                    }

                    levels = orderbook.bid_levels if order.direction == "BUY" else orderbook.ask_levels

                    # Объединение уровней
                    merged = False
                    for level in levels:
                        if (
                                level["price"] == new_level["price"] and
                                level.get("user_id") == new_level.get("user_id") and
                                level.get("order_id") == new_level.get("order_id")
                        ):
                            level["qty"] += new_level["qty"]
                            for key in ["reserved_rub", "reserved_funds"]:
                                if key in new_level:
                                    level[key] = level.get(key, 0) + new_level.get(key, 0)
                            merged = True
                            break

                    if not merged:
                        levels.append(new_level)

                    if order.direction == "BUY":
                        orderbook.bid_levels = sorted(levels, key=lambda x: -x["price"])
                        flag_modified(orderbook, "bid_levels")
                    else:
                        orderbook.ask_levels = sorted(levels, key=lambda x: x["price"])
                        flag_modified(orderbook, "ask_levels")

            return CreateOrderResponse(success=True, order_id=order.id)

        except Exception as e:
            await db.rollback()
            if isinstance(e, IntegrityError):
                raise HTTPException(status_code=400, detail=f"Database integrity error: {str(e)}")
            elif isinstance(e, HTTPException):
                raise e
            elif isinstance(e, DBAPIError):
                raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
            else:
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("", response_model=List[Union[LimitOrder, MarketOrder]])
async def list_orders(
        api_key: str = Depends(verify_auth_token),
        db: AsyncSession = Depends(get_db)
):
    user = await db.scalar(
        select(User_db).where(User_db.api_key == api_key)
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    limit_orders = await db.scalars(
        select(LimitOrder_db).where(
            (LimitOrder_db.user_id == user.id) &
            (cast(LimitOrder_db.status, String) != "CANCELLED")
        )
    )
    limit_orders = limit_orders.all()

    market_orders = await db.scalars(
        select(MarketOrder_db).where(
            (MarketOrder_db.user_id == user.id) &
            (cast(MarketOrder_db.status, String) != "CANCELLED")
        )
    )
    market_orders = market_orders.all()

    orders = []
    for order in limit_orders:
        orders.append(LimitOrder(
            id=order.id,
            status=OrderState(order.status),
            user_id=order.user_id,
            timestamp=order.timestamp.isoformat() + "Z",
            body=LimitOrderRequest(
                direction=Direction(order.direction),
                ticker=order.ticker,
                qty=order.qty,
                price=order.price
            ),
            filled=order.filled
        ))

    for order in market_orders:
        orders.append(MarketOrder(
            id=order.id,
            status=OrderState(order.status),
            user_id=order.user_id,
            timestamp=order.timestamp.isoformat() + "Z",
            body=MarketOrderRequest(
                direction=Direction(order.direction),
                ticker=order.ticker,
                qty=order.qty
            )
        ))

    return orders


@router.get("/{order_id}", response_model=Union[LimitOrder, MarketOrder])
async def get_order(
        order_id: UUID,
        api_key: str = Depends(verify_auth_token),
        db: AsyncSession = Depends(get_db)
):
    user = await db.scalar(
        select(User_db).where(User_db.api_key == api_key)
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    limit_order = await db.scalar(
        select(LimitOrder_db).where(LimitOrder_db.id == order_id)
    )

    market_order = await db.scalar(
        select(MarketOrder_db).where(MarketOrder_db.id == order_id)
    )

    if limit_order:
        if limit_order.user_id != user.id:
            raise HTTPException(status_code=403, detail="Access denied")

        return LimitOrder(
            id=limit_order.id,
            status=OrderState(limit_order.status),
            user_id=limit_order.user_id,
            timestamp=limit_order.timestamp.isoformat() + "Z",
            body=LimitOrderRequest(
                direction=Direction(limit_order.direction),
                ticker=limit_order.ticker,
                qty=limit_order.qty,
                price=limit_order.price
            ),
            filled=limit_order.filled
        )
    elif market_order:
        if market_order.user_id != user.id:
            raise HTTPException(status_code=403, detail="Access denied")

        return MarketOrder(
            id=market_order.id,
            status=OrderState(market_order.status),
            user_id=market_order.user_id,
            timestamp=market_order.timestamp.isoformat() + "Z",
            body=MarketOrderRequest(
                direction=Direction(market_order.direction),
                ticker=market_order.ticker,
                qty=market_order.qty
            )
        )
    else:
        raise HTTPException(status_code=404, detail="Order not found")


@router.delete("/{order_id}", response_model=Ok)
async def cancel_order(
        order_id: UUID,
        api_key: str = Depends(verify_auth_token),
        db: AsyncSession = Depends(get_db)
):
    user = await db.scalar(
        select(User_db).where(User_db.api_key == api_key)
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    limit_order = await db.scalar(
        select(LimitOrder_db).where(LimitOrder_db.id == order_id)
    )

    if not limit_order:
        raise HTTPException(status_code=404, detail="Limit order not found (cannot cancel market orders)")

    if limit_order.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if limit_order.status not in [OrderState.NEW, OrderState.PARTIALLY_EXECUTED]:
        raise HTTPException(status_code=400, detail="Order cannot be cancelled")

    unfilled_qty = limit_order.qty - limit_order.filled
    if unfilled_qty <= 0:
        raise HTTPException(status_code=400, detail="Order already fully executed")

    if limit_order.direction == "BUY":
        refund_amount = unfilled_qty * limit_order.price
        rub_balance = await db.scalar(
            select(Balance_db).where(
                Balance_db.user_id == user.id,
                Balance_db.ticker == "RUB"
            )
        )
        if rub_balance is None:
            rub_balance = Balance_db(user_id=user.id, ticker="RUB", amount=refund_amount)
        else:
            rub_balance.amount += refund_amount
    else:
        asset_balance = await db.scalar(
            select(Balance_db).where(
                Balance_db.user_id == user.id,
                Balance_db.ticker == limit_order.ticker
            )
        )
        if asset_balance is None:
            asset_balance = Balance_db(user_id=user.id, ticker=limit_order.ticker, amount=unfilled_qty)
        else:
            asset_balance.amount += unfilled_qty

    db.add(rub_balance if limit_order.direction == "BUY" else asset_balance)

    orderbook = await db.scalar(
        select(OrderBook_db).where(OrderBook_db.ticker == limit_order.ticker)
    )

    if orderbook:
        levels = orderbook.bid_levels if limit_order.direction == "BUY" else orderbook.ask_levels
        for level in levels:
            if level["price"] == limit_order.price:
                level["qty"] -= unfilled_qty
                break

        levels[:] = [lvl for lvl in levels if lvl["qty"] > 0]

        if limit_order.direction == "BUY":
            orderbook.bid_levels = sorted(levels, key=lambda x: -x["price"])
            flag_modified(orderbook, "bid_levels")
        else:
            orderbook.ask_levels = sorted(levels, key=lambda x: x["price"])
            flag_modified(orderbook, "ask_levels")

    limit_order.status = OrderState.CANCELLED
    db.add(limit_order)

    await db.commit()

    return Ok()