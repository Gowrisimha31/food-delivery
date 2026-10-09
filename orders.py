# orders.py
# Takes an order, works out the bill, charges the customer,
# and saves everything to the database in one go.

import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from database import get_session
from models import Restaurant, MenuItem, Order, OrderLine
from payments import process_payment
from logger import log
import chaos

# Part of the "bad deploy" break switch: a new discount feature
# that a developer forgot to set up for Pizza Planet (restaurant 3).
DISCOUNTS = {1: 0.10, 2: 0.05}

router = APIRouter(tags=["Orders"])


# What a customer must send when placing an order.
class OrderItem(BaseModel):
    item_id: int
    quantity: int


class OrderRequest(BaseModel):
    restaurant_id: int
    items: list[OrderItem]


def order_details(session: Session, order: Order):
    """Builds a full view of an order, including its dishes."""
    lines = session.exec(select(OrderLine).where(OrderLine.order_id == order.id)).all()
    restaurant = session.get(Restaurant, order.restaurant_id)
    return {
        "order_id": order.id,
        "restaurant_name": restaurant.name,
        "items": [{"name": l.name, "quantity": l.quantity, "cost": l.cost} for l in lines],
        "total": order.total,
        "payment_id": order.payment_id,
        "placed_at": order.placed_at,
    }


@router.post("/orders")
def place_order(request: OrderRequest, session: Session = Depends(get_session)):
    # 1. Check the restaurant exists
    if not session.get(Restaurant, request.restaurant_id):
        log.warning("Order rejected: restaurant not found",
                    extra={"restaurant_id": request.restaurant_id})
        raise HTTPException(status_code=404, detail="Restaurant not found")

    if not request.items:
        log.warning("Order rejected: no items", extra={"restaurant_id": request.restaurant_id})
        raise HTTPException(status_code=400, detail="Order has no items")

    # 2. Work out the bill
    menu_rows = session.exec(
        select(MenuItem).where(MenuItem.restaurant_id == request.restaurant_id)
    ).all()
    menu = {item.id: item for item in menu_rows}

    lines = []
    total = 0
    for ordered in request.items:
        if ordered.item_id not in menu:
            log.warning("Order rejected: item not on menu",
                        extra={"restaurant_id": request.restaurant_id, "item_id": ordered.item_id})
            raise HTTPException(status_code=400, detail=f"Item {ordered.item_id} is not on this menu")
        if ordered.quantity <= 0:
            log.warning("Order rejected: bad quantity",
                        extra={"item_id": ordered.item_id, "quantity": ordered.quantity})
            raise HTTPException(status_code=400, detail="Quantity must be at least 1")
        dish = menu[ordered.item_id]
        cost = dish.price * ordered.quantity
        total += cost
        lines.append(OrderLine(order_id=0, menu_item_id=dish.id, name=dish.name,
                               quantity=ordered.quantity, cost=cost))

    # Break switch: the buggy new version is live.
    # Orders from restaurant 3 crash with a KeyError.
    if chaos.is_on("bad_deploy"):
        discount = DISCOUNTS[request.restaurant_id]
        total = round(total * (1 - discount))

    # 3. Create the order (flush gives it an id without saving permanently yet)
    order = Order(restaurant_id=request.restaurant_id, total=total, placed_at=time.time())
    session.add(order)
    session.flush()

    for line in lines:
        line.order_id = order.id
        session.add(line)

    # 4. Charge the customer
    payment = process_payment(session, order.id, total)
    order.payment_id = payment.id

    # 5. Save everything at once. If anything above failed,
    #    nothing gets saved: no half-finished orders.
    session.commit()
    session.refresh(order)
    log.info("Order placed",
             extra={"order_id": order.id, "restaurant_id": order.restaurant_id,
                    "total": order.total, "payment_id": order.payment_id})
    return order_details(session, order)


@router.get("/orders")
def list_orders(session: Session = Depends(get_session)):
    orders = session.exec(select(Order)).all()
    return [order_details(session, o) for o in orders]


@router.get("/orders/{order_id}")
def get_order(order_id: int, session: Session = Depends(get_session)):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order_details(session, order)