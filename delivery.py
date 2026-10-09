# delivery.py
# Tracks where an order is, from kitchen to doorstep.
# To keep things simple, the status moves forward automatically with time.

import time
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from database import get_session
from models import Order, Restaurant

router = APIRouter(tags=["Delivery"])

# Each stage, and how many seconds after ordering it begins.
# (Sped up so you can watch it change. Real life would be minutes.)
STAGES = [
    (0, "preparing"),
    (20, "out_for_delivery"),
    (40, "delivered"),
]


def current_stage(placed_at: float):
    seconds_passed = time.time() - placed_at
    status = STAGES[0][1]
    for start, name in STAGES:
        if seconds_passed >= start:
            status = name
    return status


@router.get("/orders/{order_id}/track")
def track_order(order_id: int, session: Session = Depends(get_session)):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    restaurant = session.get(Restaurant, order.restaurant_id)
    return {
        "order_id": order.id,
        "restaurant": restaurant.name,
        "status": current_stage(order.placed_at),
    }