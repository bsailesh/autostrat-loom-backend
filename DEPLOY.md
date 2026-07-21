# Deploying AutoStrat Loom to AWS

This walks through deploying the **backend** for the first time, and
re-deploying the **front end** you already have live on S3 + CloudFront.
Every step uses the AWS Console (click-through), since that's the most
forgiving way to do this without coding experience. A few steps have an
optional CLI command as a faster alternative if you're comfortable with a
terminal.

## Architecture, in one paragraph

The front end stays exactly where it is (S3 + CloudFront). The backend runs
on **AWS App Runner** — a fully managed service that builds and runs your
API directly from source code, with HTTPS and scaling handled for you, so
there's no server to patch or container registry to manage by hand. The
database moves from the local SQLite file to **Amazon RDS for PostgreSQL**,
because App Runner's storage doesn't persist between deploys — a real
database is required, not optional, once you're not running this on your
own machine. Everything is wired together with environment variables you
set in the App Runner console.

```
Browser  →  CloudFront + S3 (autostrat.net)         [front end, already live]
                    ↓ fetch() calls
              App Runner (api.autostrat.net)          [new]
                    ↓
              RDS PostgreSQL (private, in a VPC)       [new]
```

## Cost estimate

US East, mid-2026 pricing — confirm current rates at
aws.amazon.com/apprunner/pricing and aws.amazon.com/rds/pricing before
relying on this.

| Piece | Estimate |
|---|---|
| App Runner (1 vCPU / 2 GB, light pilot traffic) | ~$10–25/month |
| RDS db.t4g.micro PostgreSQL, Single-AZ, 20 GB gp3 | ~$15–20/month |
| Route 53 record on your existing hosted zone | negligible |
| **New infrastructure total** | **roughly $25–45/month** |

This is on top of whatever your S3/CloudFront front-end hosting already
costs, and separate from Anthropic API usage, which is billed based on
actual agent calls.

---

## Step 1 — Push the code to GitHub

App Runner deploys straight from a GitHub repo, so it needs to live there
first (a **private** repo is fine and recommended).

1. Create a new private repository on GitHub (e.g. `autostrat-loom-backend`).
2. In the `autostrat-loom-backend` folder on your machine:
   ```
   git init
   git add .
   git commit -m "Initial backend"
   git branch -M main
   git remote add origin https://github.com/<your-username>/autostrat-loom-backend.git
   git push -u origin main
   ```
3. Double-check `.env` was **not** pushed (it's excluded via `.gitignore`).
   Only `.env.example` should appear in the repo — never your real API key.

## Step 2 — Create the RDS PostgreSQL database

1. AWS Console → **RDS** → **Create database**.
2. Choose **Standard create**.
3. Engine: **PostgreSQL** (latest available version).
4. Templates: **Dev/Test** (or Free Tier if your account is eligible).
5. DB instance class: **db.t4g.micro** (burstable, cheapest general-purpose
   option — fine for a pilot).
6. Storage: **20 GB gp3** is enough to start; it auto-scales if needed.
7. Under **Settings**: set a DB instance identifier (e.g. `loom-db`) and a
   master username. For the password, choose **"Manage master credentials
   in AWS Secrets Manager"** — this avoids you ever having to type or store
   the password yourself; you'll retrieve it from Secrets Manager in Step 3.
8. Under **Connectivity**:
   - VPC: leave as default, or your existing VPC if you have one.
   - Public access: **No** — this database should never be reachable
     directly from the internet.
   - VPC security group: create a new one, name it `loom-db-sg`.
9. Under **Additional configuration**: set initial database name to `loom`.
10. Click **Create database**. It takes 5–10 minutes to become available.
11. Once it's "Available," open it and note the **endpoint** (a hostname
    like `loom-db.xxxxx.us-east-1.rds.amazonaws.com`) — you'll need it in
    Step 3. Get the password from **Secrets Manager** (Console → Secrets
    Manager → find the secret RDS created → "Retrieve secret value").

## Step 3 — Create the App Runner service

1. AWS Console → **App Runner** → **Create service**.
2. Source: **Source code repository**. Click **Add new** under GitHub
   connection, authorize AWS to access your GitHub account, and select the
   `autostrat-loom-backend` repo and `main` branch.
3. Deployment trigger: **Automatic** — every future `git push` redeploys.
4. Build settings: choose **"Use a configuration file"** — App Runner will
   find and use the `apprunner.yaml` already in the repo, so you don't need
   to fill in build/start commands by hand.
5. Service settings:
   - Service name: `loom-api`
   - Port: `8000`
   - vCPU / memory: **1 vCPU / 2 GB** is a reasonable starting point.
6. **Environment variables** — add each of these (values from your `.env`
   plus the RDS details from Step 2):
   ```
   ANTHROPIC_API_KEY   = <your real key>
   LOOM_MODEL           = claude-sonnet-5
   DATABASE_URL          = postgresql://<master username>:<password>@<RDS endpoint>:5432/loom
   LOOM_ADMIN_KEYS         = <generate a long random string — this is your admin key>
   SESSION_TTL_HOURS        = 24
   CONTACT_EMAIL_TO          = saileshathreya@autostrat.net
   SMTP_HOST                  = <your SES SMTP endpoint, once set up>
   SMTP_PORT                   = 587
   SMTP_USER                    = <SES SMTP username>
   SMTP_PASSWORD                 = <SES SMTP password>
   SMTP_FROM                      = no-reply@autostrat.net
   CORS_ORIGINS                    = https://autostrat.net,https://www.autostrat.net
   ```
   For anything sensitive here (the Anthropic key, DB password, SMTP
   password), App Runner also supports referencing a Secrets Manager secret
   instead of pasting the raw value — look for "Add secret" next to the
   environment variables list if you want that extra layer now rather than
   later.
7. **Networking** (this is the one non-obvious part): App Runner needs a
   path into the VPC where your private RDS database lives.
   - Under **Networking → Outgoing network traffic**, choose **Custom VPC**.
   - Create a new **VPC connector**: select the same VPC as your RDS
     instance, and its private subnets.
   - For the connector's security group, either reuse `loom-db-sg` or
     create a new one — then go back to the RDS instance's security group
     and add an **inbound rule**: type PostgreSQL (port 5432), source = the
     VPC connector's security group. This is what actually lets App Runner
     reach the database.
8. Click **Create & deploy**. The first build takes a few minutes — watch
   the build/deploy logs in the console for errors.

## Step 4 — Verify it's live

App Runner gives you a default URL like
`https://xxxxxxxxxx.us-east-1.awsapprunner.com`. Test it:

```
curl https://xxxxxxxxxx.us-east-1.awsapprunner.com/health
```

You should get `{"status":"ok"}`. If you get a database connection error
instead, double check the `DATABASE_URL` value and the security group rule
from Step 3.7.

## Step 5 — Point api.autostrat.net at it

1. In the App Runner service → **Custom domains** → **Link domain**.
2. Enter `api.autostrat.net`. App Runner will show you a CNAME record (and
   a couple of certificate-validation CNAME records) to add.
3. Go to **Route 53** → your `autostrat.net` hosted zone → **Create
   record** → add each CNAME record exactly as App Runner shows it.
4. Wait for validation (usually 15–30 minutes). Once done,
   `https://api.autostrat.net/health` should work directly, with a
   valid HTTPS certificate App Runner manages for you automatically.

## Step 6 — Create your production tenant

Run the seed script against production instead of local (or do this any
time you onboard a new customer — it's the same command):

```
LOOM_BASE_URL=https://api.autostrat.net LOOM_ADMIN_KEY=<the LOOM_ADMIN_KEYS value you set in Step 3> python seed_data.py
```

Save the tenant API key and demo login it prints — or better, once this is
real, create a proper user for yourself via the same `/admin/tenants/{id}/users`
endpoint instead of using the demo credentials.

## Step 7 — Re-deploy the front end

`index.html` in this delivery already points at `https://api.autostrat.net`
automatically when it's not running on localhost, so no edit is needed —
just re-upload it the same way you deployed it originally:

```
aws s3 cp index.html s3://<your-bucket-name>/index.html
aws cloudfront create-invalidation --distribution-id <your-distribution-id> --paths "/*"
```

(If you'd rather do this through the console: S3 → your bucket → upload
`index.html`, overwriting the existing one, then CloudFront → your
distribution → Invalidations → create one for `/*` so cached copies clear.)

## Step 8 — End-to-end test

Visit `https://autostrat.net`, click **Log In**, sign in with the
production credentials from Step 6, and run each of the five agents once
from the dashboard. Check the **Audit Log** tab — every action you just
took should be listed there.

---

## Before onboarding real enterprise customers

This gets you to a real, working, HTTPS-everywhere deployment — but a few
things are still worth doing before customer data touches it:

- **Secrets Manager for everything sensitive**, not just the DB password —
  move `ANTHROPIC_API_KEY` and SMTP credentials there too.
- **SSO (SAML/OIDC)** in place of email/password login, once you have a
  real enterprise buyer asking for it — `app/auth.py` is the only place
  that needs to change.
- **RDS Multi-AZ** for automatic failover, once uptime matters beyond a
  pilot.
- **CloudWatch alarms** on App Runner (5xx rate, latency) and an AWS Budget
  alert so cost surprises show up immediately, not at the end of the month.
- **A real security review / pen test** before any paying enterprise
  customer's data goes anywhere near this. Nothing above substitutes for
  that.
