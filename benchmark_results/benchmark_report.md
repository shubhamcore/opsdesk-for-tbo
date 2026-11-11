# OpsDesk — Measured Benchmark

Generated: 2026-11-09T19:15:30.750857+00:00
Environment: Python 3.13.16 on Linux-6.1.189+-x86_64-with-glibc2.41
Dataset: {'tickets': 49, 'bookings': 12, 'users': 16} · classifier mode: ML

Every figure below was measured in this run against the live API. No values are estimates.

## API latency (7 sequential calls each)

| Operation | n | min ms | median ms | p95 ms | max ms |
| --- | --- | --- | --- | --- | --- |
| GET /api/tickets (queue list) | 7 | 15.49 | 16.58 | 17.45 | 17.45 |
| GET /api/analytics/queue | 7 | 17.58 | 18.1 | 18.59 | 18.59 |
| GET /api/analytics/product-intelligence | 7 | 9.01 | 9.27 | 9.6 | 9.6 |
| GET /api/analytics/bug-suggestions | 7 | 8.92 | 9.1 | 10.1 | 10.1 |
| GET /api/routing/board | 7 | 3.16 | 3.21 | 4.03 | 4.03 |
| GET /api/escalations/queue | 7 | 16.74 | 17.03 | 17.39 | 17.39 |

## Routing comparator

- Calls: 12 · median 3.92 ms · p95 4.49 ms
- Candidates scored per call: 3.0 (total 36)

## Extraction + classification (Stage A/B over live ticket text)

- Calls: 40 · median 2.35 ms · p95 2.61 ms

## Export stream (50,000 rows)

- Rows received by the client (incl. header): 50,001
- Columns: 25
- Client elapsed: 1,297.72 ms · 38,529.93 rows/s
- Server-measured: 1289.12 ms · 38,786.15 rows/s · 16.313 MB · peak 8.848 MB
- Validation: PASS (50,000 rows in file)

## Classifier evaluation (template-disjoint holdout, ai_models/evaluation/metrics.json)

- Train rows: 576 · holdout rows: 288 · split: template-disjoint: every holdout template is unseen during training
- Holdout accuracy: 0.8958 · macro F1: 0.8964
- Dataset: SYNTHETIC (template-generated; no real TBO ticket text was used)

| Intent | Precision | Recall | F1 | Support |
| --- | --- | --- | --- | --- |
| REFUND_DELAY | 0.9677 | 0.8333 | 0.8955 | 36 |
| CANCELLATION_LCD_WAIVER | 0.9231 | 1.0 | 0.96 | 36 |
| VOUCHER_CONFIRMATION_ISSUE | 0.8889 | 0.8889 | 0.8889 | 36 |
| AMENDMENT_NAME_DATE | 0.9211 | 0.9722 | 0.9459 | 36 |
| INVENTORY_RATE_SYNC_BUG | 1.0 | 0.8333 | 0.9091 | 36 |
| SPECIAL_REQUEST | 0.7805 | 0.8889 | 0.8312 | 36 |
| SUPPLIER_OVERBOOKING_RELOCATION | 0.8 | 0.8889 | 0.8421 | 36 |
| BILLING_INVOICE_DISPUTE | 0.9394 | 0.8611 | 0.8986 | 36 |
