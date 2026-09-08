# Deploying to AWS Lightsail (cheapest option, for a POC with no real traffic yet)

This is the low-cost path: one small server, running the API directly with
its existing SQLite database — no RDS, no VPC, no App Runner. Total new
AWS cost is about **$5/month** (often free for your first 3 months on a
new Lightsail bundle). When you eventually get real customers, see the
"Scaling up later" section at the bottom — nothing here is a dead end.

Every step below uses the Lightsail browser console. SSH can be done
through the browser-based terminal with no local setup, but see the note
before Step 5 — key-based SSH from your own machine is more reliable and
recommended.

> **Read `PRODUCTION-READINESS.md` first.** It has the full Phase 6
> checklist, the exact backend environment-variable list, the SQLite
> storage plan, and the frontend production-build steps. This file is the
> AWS click-through; that file is the decisions and the checklist.

## What you're building

```
Browser  →  CloudFront + S3 (app.autostrat.net)       [front end — new bucket/distribution, see Step 11]
                    ↓ fetch() calls
              Lightsail instance (api.autostrat.net)   [new]
                ├─ Caddy (reverse proxy + free HTTPS)
                └─ the API (uvicorn) + SQLite file
```

(`autostrat.net` itself is the separate marketing site, already live on its
own bucket/distribution — not touched by this doc.)

---

## Step 1 — Push the code to GitHub

(If you already did this for a previous App Runner attempt, skip to Step 2.)

1. Create a private GitHub repository (e.g. `autostrat-loom-backend`).
2. From the `autostrat-loom-backend` folder on your own machine:
   ```
   git init
   git add .
   git commit -m "Initial backend"
   git branch -M main
   git remote add origin https://github.com/<your-username>/autostrat-loom-backend.git
   git push -u origin main
   ```
3. Confirm `.env` did **not** get pushed (it's excluded via `.gitignore` —
   only `.env.example` should appear in the repo).

## Step 2 — Create the Lightsail instance

1. AWS Console → **Lightsail** → **Create instance**.
2. Platform: **Linux/Unix**.
3. Blueprint: **OS Only → Ubuntu 24.04 LTS**.
4. Instance plan: the **$5/month** plan (512 MB RAM, 2 vCPUs, 20 GB SSD,
   1 TB data transfer — plenty for a POC). Skip the $3.50 IPv6-only plan
   for now; a public IPv4 address makes DNS simpler.
5. Name it something like `loom-api`.
6. Click **Create instance**. It's ready in under a minute.
7. **Confirm the name took effect** on the Instances list afterwards — it
   can silently default to something like `Ubuntu-1` instead. Also check
   whether the intended name is already in use by another instance; if so,
   pick a different one rather than fighting the collision.

The live backend instance is currently named **`Ubuntu-1`** for this reason
— a pre-existing unrelated instance already held the name `loom-api`. The
rest of this doc refers to "the instance," not a specific name; use
whichever name yours actually ended up with.

## Step 3 — Attach a static IP

Without this, the instance's public IP changes if it's ever restarted,
which would break your domain.

1. Lightsail → **Networking** tab → **Create static IP**.
2. Attach it to your `loom-api` instance.
3. Note the static IP address — you'll point DNS at it in Step 9.

## Step 4 — Open the firewall for HTTP/HTTPS

1. Click into the `loom-api` instance → **Networking** tab.
2. Under **IPv4 Firewall**, make sure rules exist for:
   - SSH, TCP, 22 (should already be there)
   - HTTP, TCP, 80
   - HTTPS, TCP, 443
   Add any that are missing.

## A note on connecting: use key-based SSH, not just the browser terminal

The Lightsail browser SSH terminal is convenient but **unreliable** — it can
freeze and disconnect mid-session. Key-based SSH from your own machine is
recommended instead:

1. Lightsail console → **Account** → **SSH keys** → download the default
   private key.
2. Restrict its permissions: `chmod 400 <key.pem>` (macOS/Linux) or the
   equivalent on Windows.
3. Connect with:
   ```
   ssh -i <key.pem> ubuntu@<static-ip>
   ```

The browser terminal still works as a fallback. If it freezes: close it,
open a fresh session, `cd` back into the project folder, and **re-check
state** (`systemctl status`, `git log`) before re-running anything — work
often completed despite the terminal appearing dead.

## Step 5 — Connect and run the setup script

1. Click into the `loom-api` instance → **Connect** tab → **Connect using
   SSH** (opens a terminal right in your browser), or connect with your own
   key as described above.
2. Download and run the setup script from this project:
   ```
   curl -o setup.sh https://raw.githubusercontent.com/<your-username>/autostrat-loom-backend/main/deploy/lightsail/setup.sh
   chmod +x setup.sh
   ./setup.sh
   ```
   (If you'd rather not fetch it from GitHub, open
   `deploy/lightsail/setup.sh` from this project, copy its contents, and
   paste them into a new file on the instance with `nano setup.sh`.)
3. When prompted, paste your GitHub repo URL to clone the code.
4. Edit the `.env` file it creates:
   ```
   nano ~/autostrat-loom-backend/.env
   ```
   At minimum, set:
   - `ANTHROPIC_API_KEY` — your real key (use a **separate production key**
     with a spending limit set in the Anthropic console — see
     `PRODUCTION-READINESS.md` item 3)
   - `LOOM_ADMIN_KEYS` — generate one with:
     `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
   - `CORS_ORIGINS=https://autostrat.net,https://www.autostrat.net,https://app.autostrat.net`
     (must be an explicit list, never `*`, and every origin — subdomains
     included — must be listed in full: the product frontend is served from
     `https://app.autostrat.net`, and listing the bare domain does **not**
     cover it. The API reads this value once at startup, so
     `sudo systemctl restart loom-api` is required after any change.)
   - `DATABASE_URL=sqlite:////home/ubuntu/autostrat-loom-backend/loom.db`
     (absolute path — four slashes — so it never depends on the working
     directory)
   - `CONTACT_EMAIL_TO=saileshathreya@autostrat.net` (already the default)
   - `SMTP_*` values, once you've set up SES or another provider — fine to
     leave blank for now; the contact form still works and just skips
     sending until these are filled in.

   Save with `Ctrl+O`, then `Enter`, then exit with `Ctrl+X`. In `nano`, a
   line edited in place can silently fail to save the full line — use
   `Ctrl+K` to delete the whole line first, then retype it.

   After saving, verify the file actually has what you set before restarting
   anything:
   ```
   grep CORS_ORIGINS ~/autostrat-loom-backend/.env
   ```

## Step 6 — Install the systemd service (keeps the API running)

Still in the SSH terminal:

```
sudo cp ~/autostrat-loom-backend/deploy/lightsail/loom-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable loom-api
sudo systemctl start loom-api
```

Check it's actually running:

```
sudo systemctl status loom-api
curl http://127.0.0.1:8000/health
```

You should see `{"status":"ok"}`. If not, check the logs:

```
sudo journalctl -u loom-api -n 50 --no-pager
```

This service now starts automatically on every boot, and systemd restarts
it automatically if it ever crashes.

## Step 7 — Add swap (required on the 512 MB plan)

Without swap, the 512 MB plan can run out of memory badly enough to wedge
the whole instance — not just the API, but SSH and the network stack too,
with the OOM killer firing repeatedly while CPU sits idle. Add 2 GB of swap
before doing anything else:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=20' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

Verify with `free -h` — the `Swap` row should show `2.0Gi`. Then check
`/etc/fstab` didn't get a malformed line (`cat /etc/fstab`) — a bad entry
there can prevent the instance from booting.

Also mask `fwupd`, a firmware-update daemon that has nothing to do on a
virtual instance but will otherwise get OOM-killed on a loop:

```bash
sudo systemctl disable --now fwupd-refresh.service fwupd-refresh.timer
sudo systemctl mask fwupd.service
```

`fwupd.service` is a **static** unit — `disable` doesn't work on it, it has
to be **masked**.

Swap makes the box stable, but it doesn't make 512 MB generous. If agent
runs push swap usage into the hundreds of MB, resize the instance.

## Step 8 — Install Caddy for free automatic HTTPS

```
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update -y
sudo apt-get install -y caddy
```

Then install this project's Caddy config (it just proxies to the API and
handles HTTPS certificates automatically):

```
sudo cp ~/autostrat-loom-backend/deploy/lightsail/Caddyfile /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

Caddy ships with a placeholder config (`:80 { ... }` serving
`/usr/share/caddy`) until this copy step runs. If it's missed, or a
terminal session drops mid-step, the site will serve Caddy's default page
instead of the API. Verify with `sudo systemctl status caddy` and a real
request afterwards.

Caddy won't be able to get a real certificate until DNS actually points at
this server — that's the next step.

## Step 9 — Point api.autostrat.net at the instance

DNS for `autostrat.net` is managed at **Cloudflare**, not Route 53.

1. Cloudflare dashboard → the `autostrat.net` zone → **DNS**.
2. **Add record**: type **A**, name `api`, value = the static IP from
   Step 3.
3. **Proxy status must be DNS-only (grey cloud), not proxied (orange
   cloud)** — at least until the certificate is issued. If it's proxied,
   Caddy can't complete the Let's Encrypt HTTP challenge and certificate
   issuance fails.
4. Wait a few minutes for DNS to propagate, then reload Caddy so it
   notices and requests the certificate:
   ```
   sudo systemctl restart caddy
   ```
5. Test it:
   ```
   curl https://api.autostrat.net/health
   ```
   You should get `{"status":"ok"}` over a real HTTPS connection.

## Step 10 — Create your production account

Signup is invite-only (the pre-Phase-6 allowlist gate). In the SSH session:

```
cd ~/autostrat-loom-backend
source venv/bin/activate
python3 manage_allowlist.py add <your-email>
```

Until an email is on the allowlist, `POST /auth/signup` returns 403. Once it
is, sign up normally through the frontend (or with a direct
`POST https://api.autostrat.net/auth/signup`); that creates your tenant with
you as owner and logs you in.

## Step 11 — Create frontend hosting and deploy the front end

The product frontend is the React app in `frontend/`. (The old single-file
dashboard is archived in `legacy/` and is not deployed — see
`legacy/README.md`.) It needs **its own** S3 bucket and CloudFront
distribution — the marketing site already has its own hosting, and reusing
it would overwrite the marketing site.

1. Create a new S3 bucket (this deployment used `autostrat-app`), private,
   with static website hosting **off**.
2. Request or reuse an ACM certificate covering `app.<domain>`. **It must be
   in `us-east-1` regardless of where anything else lives** — CloudFront
   only reads certificates from that region. (This deployment reused an
   existing wildcard `*.autostrat.net` certificate rather than issuing a new
   one.)
3. Create a CloudFront distribution with the bucket as origin, using Origin
   Access Control so the bucket stays private.
4. **Set "Default root object" to `index.html`.** Omitting this breaks the
   bare root URL for a single-page app.
5. Add the alternate domain name `app.<domain>` and attach the certificate.
6. In **Cloudflare**, add a CNAME for `app` pointing at the distribution
   domain.
7. Build with the production API URL baked in, then upload the `dist/`
   output:
   ```
   cd frontend
   cp .env.production.example .env.production      # VITE_API_BASE=https://api.autostrat.net
   npm ci
   npm run build                                   # -> frontend/dist/
   aws s3 sync dist/ s3://<your-bucket-name>/ --delete
   aws cloudfront create-invalidation --distribution-id <your-distribution-id> --paths "/*"
   ```
   The `--delete` flag matters: Vite emits hash-named bundles, so without it
   every old bundle accumulates in the bucket forever.

`dist/` is gitignored — you build it at deploy time, you don't commit it.
If `VITE_API_BASE` is not set at build time the bundle silently falls back
to `localhost:8000`, so don't skip the `.env.production` step.

This deployment's values: bucket `autostrat-app`, distribution
`E2YF1Y0LAQQTFV` (`d33ugba59hfe7o.cloudfront.net`). The marketing site is a
separate bucket `autostrat-temp-site` on distribution `E2ZCVTWM9KA4M8` —
don't confuse the two.

## Step 12 — End-to-end test

Visit `https://app.autostrat.net` (not the marketing site at
`autostrat.net`), sign up / log in with the account from Step 10, configure
the Market Insights scope, start a run, and confirm it leaves the
"configure scope" gate and begins polling.

---

## Keeping it backed up

SQLite's data lives on the instance's disk — it survives reboots, but not
a deleted instance. Take a Lightsail **snapshot** periodically (Lightsail
console → your instance → **Snapshots** tab → **Create snapshot**), or set
up automatic daily snapshots from the same tab. This is your backup, not
Postgres-grade point-in-time recovery, but it's enough for a POC.

## Deploying code changes later

Once you push new commits to GitHub, update the server with:

```
ssh into the instance, then:
cd ~/autostrat-loom-backend
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart loom-api
```

**This deploys the backend only.** Any change under `frontend/` additionally
needs its own deploy — it's easy to merge a UI change, deploy the backend,
and have nothing appear because the frontend was never rebuilt:

```
cd frontend && npm run build
aws s3 sync dist/ s3://autostrat-app/ --delete
aws cloudfront create-invalidation --distribution-id E2YF1Y0LAQQTFV --paths "/*"
```

CloudFront and the browser both cache, so do a hard refresh (Ctrl+Shift+R)
to confirm the new version actually loaded.

Before and after any redeploy that involves new infrastructure (a new
instance, a new distribution), check Cloudflare for stale or duplicate DNS
records pointing at the old one — leftover records cause intermittent,
confusing failures. When an old instance is deleted, release its static IP
too.

## Scaling up later

Nothing here is a dead end — every piece of data access goes through one
`DATABASE_URL` setting (`app/database.py`), so growing out of this setup is
a config change, not a rewrite:

1. **First real customers / need reliability:** create a small RDS
   PostgreSQL instance and point `DATABASE_URL` at it — still running the
   app on this same Lightsail box. No code changes.
2. **Real traffic / need auto-scaling, zero-downtime deploys:** move the
   app itself to AWS App Runner using `DEPLOY.md` in this same project —
   same codebase, same `Dockerfile` already included, pointed at that same
   RDS database.

## Before onboarding real enterprise customers

Same caveats as the App Runner path — a single Lightsail instance with no
managed database is fine for a POC, not for paying enterprise customers.
Before that:
- Move off SQLite to RDS (see above).
- Move secrets (Anthropic key, SMTP password) to AWS Secrets Manager
  instead of a plaintext `.env` file.
- Replace email/password login with SSO if a customer requires it.
- Get a real security review / pen test.
