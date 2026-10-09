# payments.py
# Pretends to be a payment company like Razorpay.
# No real money moves. It just approves or rejects payments.

import time
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from database import get_session
from models import Payment
from logger import log
import chaos

router = APIRouter(tags=["Payments"])


def process_payment(session: Session, order_id: int, amount: int):
    """Charge the customer. Called by the orders part of the app."""
    if amount <= 0:
        log.error("Payment rejected: invalid amount", extra={"order_id": order_id, "amount": amount})
        raise HTTPException(status_code=400, detail="Invalid payment amount")

    # Break switch: the payment company isn't answering.
    # We wait, give up, and report it, just like a real app would.
    if chaos.is_on("payment_gateway_down"):
        time.sleep(3)
        log.error("Payment gateway request failed",
                  extra={"order_id": order_id, "amount": amount,
                         "gateway": "razorpay-sim",
                         "error": "ConnectTimeout: gateway did not respond within 3s"})
        raise HTTPException(status_code=503, detail="Payment service unavailable, please try again")

    payment = Payment(
        id="pay_" + uuid.uuid4().hex[:8],  # a random ID like pay_3f9a1c2b
        order_id=order_id,
        amount=amount,
        status="success",
    )
    session.add(payment)
    log.info("Payment approved",
             extra={"payment_id": payment.id, "order_id": order_id, "amount": amount})
    return payment


@router.get("/payments/{payment_id}")
def get_payment(payment_id: str, session: Session = Depends(get_session)):
    payment = session.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment