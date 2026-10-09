# main.py
# The front door of the app. It plugs all the parts together,
# and logs every request that comes in.

import time
import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from database import create_tables_and_seed
from logger import log, request_id_var
import restaurants
import orders
import payments
import delivery
import chaos


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the app starts up
    create_tables_and_seed()
    log.info("App started")
    yield
    log.info("App shutting down")


app = FastAPI(title="Food Delivery App", lifespan=lifespan)

app.include_router(restaurants.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(delivery.router)
app.include_router(chaos.router)


@app.middleware("http")
async def log_every_request(request: Request, call_next):
    # Don't log the break switches themselves. The AI must not see them.
    if request.url.path.startswith("/chaos"):
        return await call_next(request)

    # Give this request a short unique ID, like a3f9c2e1
    request_id = uuid.uuid4().hex[:8]
    request_id_var.set(request_id)
    start = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        # Something crashed that our code didn't expect.
        # Log the full error, and send the customer a clean message.
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        log.exception(
            "Unhandled error",
            extra={"method": request.method, "path": request.url.path,
                   "status": 500, "duration_ms": duration_ms},
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    status = response.status_code

    # Pick how serious this log line is, based on the status code
    if status >= 500:
        level = logging.ERROR
    elif status >= 400:
        level = logging.WARNING
    else:
        level = logging.INFO

    log.log(
        level,
        f"{request.method} {request.url.path} -> {status}",
        extra={"method": request.method, "path": request.url.path,
               "status": status, "duration_ms": duration_ms},
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/")
def home():
    return {"message": "Food delivery app is running"}