# Runbooks: Food Delivery App

Each runbook describes a known type of incident: how to recognise it, how serious it
usually is, and what to do. The agent reads these when diagnosing a problem.

## RB-01: Payment gateway outage
**Category:** payment_gateway_outage
**Typical severity:** SEV1. No customer can pay, so no one can complete an order.
**Symptoms:** 5xx errors (usually 503) only on POST /orders. Orders are slow (around the
gateway timeout, ~3s) before failing. Logs show "Payment gateway request failed" with
ConnectTimeout errors. Browsing restaurants and menus is unaffected.
**Likely cause:** The external payment provider is down or unreachable.
**Actions:**
1. Check the payment provider's status page.
2. Post a customer-facing notice that payments are temporarily failing.
3. If the provider supports it, switch to a backup payment provider. (requires approval)
4. Do NOT restart our app: the problem is outside our system.

## RB-02: Database slow
**Category:** database_slow
**Typical severity:** SEV2. Everything still works, just slowly.
**Symptoms:** High latency (seconds) on almost every endpoint that reads data, but no or
very few errors. Throughput drops because requests take longer.
**Likely cause:** The database is overloaded: heavy queries, missing indexes, or a
resource limit (CPU, disk) on the database server.
**Actions:**
1. Check database CPU, memory and disk usage.
2. Look for long-running or blocking queries.
3. If one query is to blame, kill it. (requires approval)
4. Consider scaling up the database. (requires approval)

## RB-03: Database connection pool exhausted
**Category:** db_connection_exhaustion
**Typical severity:** SEV1. It spreads to every endpoint that uses the database, so the
whole app is effectively down, even if the error rate still looks low when first detected.
**Symptoms:** 500 errors on almost every endpoint that uses the database. Errors such as
"QueuePool limit of size N overflow M reached, connection timed out". Requests wait
(around the pool timeout) before failing.
**Likely cause:** All database connections are in use: a connection leak, a traffic
spike, or slow queries holding connections too long.
**Actions:**
1. Check the number of open database connections.
2. Look for code that opens connections without closing them (recent changes first).
3. Restart the application to release leaked connections. (requires approval)
4. Increase the pool size only as a temporary measure. (requires approval)

## RB-04: Bad deployment
**Category:** bad_deployment
**Typical severity:** SEV2 when only some requests fail (one restaurant, one feature) and
most customers can still order. SEV1 only if most or all orders are failing.
**Symptoms:** Errors begin shortly after a "Deployment completed" log line. Often only
some requests fail (e.g. one restaurant, one feature), with code errors such as KeyError,
TypeError or AttributeError in the tracebacks.
**Likely cause:** A bug in the newly released code.
**Actions:**
1. Confirm the errors started after the deployment time.
2. Roll back to the previous version. (requires approval)
3. Open a ticket for the developer who made the change, including the traceback.

## RB-05: Memory leak
**Category:** memory_leak
**Typical severity:** SEV2 while the app is only slowing down; SEV1 once it crashes.
**Symptoms:** Memory usage grows steadily over hours. Eventually the app slows down and
crashes with MemoryError or is killed by the system (OOM).
**Likely cause:** Code keeps objects in memory and never releases them.
**Actions:**
1. Check memory usage graphs over the last few hours.
2. Restart the application as a temporary fix. (requires approval)
3. Profile memory usage to find the leak.

## RB-06: Disk full
**Category:** disk_full
**Typical severity:** SEV1. New orders can't be saved.
**Symptoms:** Errors such as "No space left on device". Logs may stop being written.
Database writes fail.
**Likely cause:** Logs, temporary files or database growth filled the disk.
**Actions:**
1. Check disk usage.
2. Delete or archive old log files. (requires approval)
3. Make sure log rotation is enabled.

## RB-07: Application down
**Category:** app_down
**Typical severity:** SEV1. No customer can use the app.
**Symptoms:** Traffic suddenly drops to zero or near zero. Customers cannot connect.
Few or no logs are written, because requests never reach the app.
**Likely cause:** The application process crashed, or the server/network is down.
**Actions:**
1. Check whether the application process is running.
2. Check the server and network.
3. Restart the application. (requires approval)