# Changelog

## 0.1.0
- Peer-to-peer EV charger sharing: drivers find **live** chargers (optionally near them), request a slot, the hub accepts or declines, the driver pays and gets directions.
- Hubs: Orders page, My chargers, Share a charger, and a Go live bar that checks their location against their chargers.
- Verified accounts: documents, email OTP and reviewer approval; separate reviewer portal with a Users tab (remove or restore accounts).
- Session lifecycle: running sessions, ending a session frees the charger, one open booking per driver.
- Payments: demo provider and Razorpay; refunds on cancellation; unpaid and unanswered requests expire.
- Security: cookie sessions with CSRF header, login attempt limits, encrypted documents, automatic document deletion, S3 storage.
- Postgres or SQLite with Alembic migrations; Docker image and self-hosting guide.
