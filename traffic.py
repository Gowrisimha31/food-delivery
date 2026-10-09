# traffic.py
# Pretends to be lots of customers using the app.
# Run it in a SECOND terminal while the app is running.
# Press Ctrl + C to stop it.

import random
import time
import httpx

APP_URL = "http://127.0.0.1:8000"

# Roughly how many requests to send per second
REQUESTS_PER_SECOND = 2

# What customers do, and how often (the numbers are relative weights)
ACTIONS = {
    "browse_restaurants": 30,
    "view_menu": 30,
    "place_order": 20,
    "track_order": 15,
    "bad_order": 5,  # customers make mistakes too
}

client = httpx.Client(base_url=APP_URL, timeout=10)
my_order_ids = []      # orders we placed, so we can track them
menu_cache = {}        # restaurant_id -> list of dish ids
stats = {"ok": 0, "client_error": 0, "server_error": 0, "unreachable": 0}


def browse_restaurants():
    return client.get("/restaurants")


def view_menu():
    return client.get(f"/restaurants/{random.randint(1, 3)}/menu")


def place_order():
    restaurant_id = random.randint(1, 3)

    # Look at the menu first (only once per restaurant, then remember it)
    if restaurant_id not in menu_cache:
        menu = client.get(f"/restaurants/{restaurant_id}/menu")
        if menu.status_code != 200:
            return menu  # couldn't load the menu, so report that
        menu_cache[restaurant_id] = [dish["id"] for dish in menu.json()]

    dishes = menu_cache[restaurant_id]
    chosen = random.sample(dishes, k=random.randint(1, len(dishes)))
    order = {
        "restaurant_id": restaurant_id,
        "items": [{"item_id": d, "quantity": random.randint(1, 3)} for d in chosen],
    }
    response = client.post("/orders", json=order)
    if response.status_code == 200:
        my_order_ids.append(response.json()["order_id"])
    return response


def track_order():
    if not my_order_ids:
        return place_order()
    return client.get(f"/orders/{random.choice(my_order_ids)}/track")


def bad_order():
    # Order a dish that doesn't exist
    order = {"restaurant_id": 2, "items": [{"item_id": 999, "quantity": 1}]}
    return client.post("/orders", json=order)


def record(action, response):
    code = response.status_code
    if code < 400:
        stats["ok"] += 1
        mark = "OK  "
    elif code < 500:
        stats["client_error"] += 1
        mark = "4xx "
    else:
        stats["server_error"] += 1
        mark = "5xx!"
    ms = round(response.elapsed.total_seconds() * 1000)
    print(f"{mark} {code}  {action:<20} {ms} ms")


def print_summary():
    total = sum(stats.values())
    print(f"\n--- {total} requests | ok {stats['ok']} | 4xx {stats['client_error']} "
          f"| 5xx {stats['server_error']} | unreachable {stats['unreachable']} ---\n")


def main():
    print(f"Sending about {REQUESTS_PER_SECOND} requests per second to {APP_URL}")
    print("Press Ctrl + C to stop.\n")
    actions = list(ACTIONS.keys())
    weights = list(ACTIONS.values())
    count = 0

    try:
        while True:
            action = random.choices(actions, weights=weights)[0]
            try:
                response = globals()[action]()
                record(action, response)
            except httpx.HTTPError as error:
                # The app didn't answer at all: it's down, or too slow
                stats["unreachable"] += 1
                print(f"DOWN      {action:<20} {type(error).__name__}")

            count += 1
            if count % 20 == 0:
                print_summary()

            # Wait a random amount, so traffic looks natural
            time.sleep(random.uniform(0.5, 1.5) / REQUESTS_PER_SECOND)
    except KeyboardInterrupt:
        print_summary()
        print("Stopped.")


if __name__ == "__main__":
    main()