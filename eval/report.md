# Incident Agent: Evaluation Report

**Rounds:** 30  (25 with a fault, 5 with no fault)

## 1. Detection

| Metric | Result |
|---|---|
| Faults detected | 25/25 (100%) |
| False alarms (no-fault rounds) | 1/5 |
| Mean time to detect (MTTD) | 15.5s |
| Median / slowest | 15.0s / 45.5s |

**Time to detect by scenario**

| Scenario | Detected | Mean time |
|---|---|---|
| bad_deploy | 5/5 | 25.2s |
| db_connections_exhausted | 5/5 | 10.0s |
| payment_gateway_down | 5/5 | 15.1s |
| slow_database | 5/5 | 10.0s |
| trap_rollback_then_gateway | 5/5 | 17.1s |

## 2. Diagnosis accuracy

| | Rules | AI |
|---|---|---|
| Correct category | 25/25 (100%) | 25/25 (100%) |
| Correct severity | 25/25 (100%) | 25/25 (100%) |

- **AI answered** 25/25 cases (0 fell back to rules because the AI was unavailable; those are excluded from the AI column).
- **Mean AI diagnosis time:** 6.3s

**Accuracy by scenario**

| Scenario | Rules | AI |
|---|---|---|
| bad_deploy | 5/5 | 5/5 |
| db_connections_exhausted | 5/5 | 5/5 |
| payment_gateway_down | 5/5 | 5/5 |
| slow_database | 5/5 | 5/5 |
| trap_rollback_then_gateway | 5/5 | 5/5 |

## 3. Mistakes (for error analysis)

**AI mistakes**

- none

**Rules mistakes**

- none

**Detection mistakes**

- Case 20: false alarm with no fault
