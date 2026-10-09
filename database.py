# database.py
# Connects to the database, creates the tables,
# and fills in the starting restaurants and menus.

import random
import time
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlmodel import SQLModel, Session, create_engine, select
from models import Restaurant, MenuItem
import chaos

# SQLite keeps the whole database in a single file: food.db
DATABASE_URL = "sqlite:///food.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def get_session():
    """Gives each request its own connection to the database."""

    # Break switch: the database is overloaded, so everything is slow
    if chaos.is_on("slow_database"):
        time.sleep(random.uniform(1.5, 3.0))

    # Break switch: all connections are in use. The app waits for a free
    # one, gives up, and crashes with the same error a real app would show.
    if chaos.is_on("db_connections_exhausted"):
        time.sleep(2)
        raise PoolTimeoutError(
            "QueuePool limit of size 5 overflow 10 reached, "
            "connection timed out, timeout 30.00"
        )

    with Session(engine) as session:
        yield session


def create_tables_and_seed():
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # Only add starting data if the database is empty
        if session.exec(select(Restaurant)).first():
            return

        spice = Restaurant(name="Spice Garden", cuisine="North Indian", rating=4.3)
        dosa = Restaurant(name="Dosa Corner", cuisine="South Indian", rating=4.5)
        pizza = Restaurant(name="Pizza Planet", cuisine="Italian", rating=4.1)
        session.add_all([spice, dosa, pizza])
        session.commit()  # saves them, and gives each one an id

        session.add_all([
            MenuItem(restaurant_id=spice.id, name="Paneer Butter Masala", price=240),
            MenuItem(restaurant_id=spice.id, name="Butter Naan", price=50),
            MenuItem(restaurant_id=spice.id, name="Dal Makhani", price=200),
            MenuItem(restaurant_id=dosa.id, name="Masala Dosa", price=90),
            MenuItem(restaurant_id=dosa.id, name="Idli Vada", price=70),
            MenuItem(restaurant_id=dosa.id, name="Filter Coffee", price=40),
            MenuItem(restaurant_id=pizza.id, name="Margherita Pizza", price=299),
            MenuItem(restaurant_id=pizza.id, name="Garlic Bread", price=129),
        ])
        session.commit()