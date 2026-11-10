# Setup: email (Brevo, free) and payments (Razorpay test mode, free)

Work in the project folder, with the virtual environment active (`source venv/bin/activate`).
Edit `.env` with any text editor, for example `nano .env`. Never commit `.env`.

## Part A: Email with Brevo (free)

### A1. Create the account
1. Open https://www.brevo.com and click **Sign up free**.
2. Confirm your email address.
3. Free plan: check the current daily limit on Brevo's pricing page. It is enough for codes and password resets.

### A2. Verify a sender address
1. In Brevo, open **Senders, Domains and Dedicated IPs** (under the settings menu), then **Senders**.
2. Click **Add a sender**. Enter a name and an email address you can read, such as your Gmail.
3. Open the confirmation email Brevo sends and click the link.
4. Sender status must show **Active** before you continue.

### A3. Create an SMTP key
1. In Brevo, open **SMTP & API** (under the settings menu).
2. Open the **SMTP** tab. Note the **Login** and the **SMTP server** and **Port**. The server is `smtp-relay.brevo.com` and the port is `587`.
3. Click **Generate a new SMTP key**. Name it `evshare`. Copy the key immediately; Brevo shows it only once.

### A4. Put the values in `.env`
Open `.env` and set these lines (replace the example values):
```
EVSHARE_OTP_PROVIDER=smtp
EVSHARE_SMTP_HOST=smtp-relay.brevo.com
EVSHARE_SMTP_PORT=587
EVSHARE_SMTP_USER=your-brevo-login
EVSHARE_SMTP_PASSWORD=your-smtp-key
EVSHARE_SMTP_FROM=the-verified-sender@example.com
```

### A5. Test it
Run: `python -m scripts.test_email your.inbox@example.com`

You should see: `OK: test email sent to ...`
Then check your inbox, and the spam folder if it's not there.

If you see `FAILED`, the message tells you what to check. Paste the full message to me.

## Part B: Payments with Razorpay test mode (free)

Test mode is free and moves no real money. Live payments need Razorpay's business verification, which we will do later.

### B1. Create the account
1. Open https://dashboard.razorpay.com/signup and sign up.
2. Stay in **Test Mode**. The toggle is at the top of the dashboard.

### B2. Copy the test keys
1. Open **Account & Settings** > **API Keys** (Test Mode).
2. Click **Generate Test Key**. Copy the **Key ID** (starts with `rzp_test_`) and the **Key Secret**. The secret is shown only once.

### B3. Put the keys in `.env`
```
EVSHARE_PAYMENT_PROVIDER=razorpay
EVSHARE_RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
EVSHARE_RAZORPAY_KEY_SECRET=your-test-secret
```

### B4. Check the keys
Run: `python -m scripts.check_razorpay`

You should see: `Key mode: TEST` then `OK: Razorpay accepted the keys.`

### B5. Test a payment
Restart the app (`uvicorn app.main:app --reload`), book a slot as a driver, and pay with Razorpay's test card from its documentation (search "Razorpay test cards").

## Part C: Restart and check
Stop the app with Ctrl+C, start it again with `uvicorn app.main:app --reload`, and sign up again to confirm the code email arrives.
