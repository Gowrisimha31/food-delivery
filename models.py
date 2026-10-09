# models.py
# Describes the tables in our database.
# Each class = one table. Each field = one column.

from typing import Optional
from sqlmodel import SQLModel, Field


class Restaurant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    cuisine: str
    rating: float


class MenuItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    restaurant_id: int = Field(foreign_key="restaurant.id")
    name: str
    price: int


class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    restaurant_id: int = Field(foreign_key="restaurant.id")
    total: int
    payment_id: Optional[str] = None
    placed_at: float  # time the order was placed, in seconds


class OrderLine(SQLModel, table=True):
    # One row per dish in an order, e.g. "2 x Masala Dosa"
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    menu_item_id: int = Field(foreign_key="menuitem.id")
    name: str
    quantity: int
    cost: int


class Payment(SQLModel, table=True):
    id: str = Field(primary_key=True)  # like pay_3f9a1c2b
    order_id: int = Field(foreign_key="order.id")
    amount: int
    status: str