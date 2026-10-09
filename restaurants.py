# restaurants.py
# Everything to do with restaurants and menus.

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from database import get_session
from models import Restaurant, MenuItem

router = APIRouter(tags=["Restaurants"])


@router.get("/restaurants")
def list_restaurants(session: Session = Depends(get_session)):
    return session.exec(select(Restaurant)).all()


@router.get("/restaurants/{restaurant_id}/menu")
def get_menu(restaurant_id: int, session: Session = Depends(get_session)):
    if not session.get(Restaurant, restaurant_id):
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return session.exec(select(MenuItem).where(MenuItem.restaurant_id == restaurant_id)).all()