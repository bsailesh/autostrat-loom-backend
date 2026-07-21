# Deploying to AWS Lightsail (cheapest option, for a POC with no real traffic yet)

This is the low-cost path: one small server, running the API directly with
its existing SQLite database — no RDS, no VPC, no App Runner. Total new
AWS cost is about **$5/month** (often free for your first 3 months on a
new Lightsail bundle). When you eventually get real customers, see the
"Scaling up later" section at the bottom — nothing here is a dead end.

Every step below uses the Lightsail browser console, including a
browser-based SSH terminal — you don't need to install or configure
anything on your own machine to do this.

## What you're building

```
Browser  →  CloudFront + S3 (autostrat.net)          [front end, already live]
                    ↓ fetch() calls
              Lightsail instance (api.autostrat.net)   [new]
                ├─ Caddy (reverse proxy + free HTTPS)
                └─ the API (uvicorn) + SQLite file
```

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

## Step 3 — Attach a static IP

Without this, the instance's public IP changes if it's ever restarted,
which would break your domain.

1. Lightsail → **Networking** tab → **Create static IP**.
2. Attach it to your `loom-api` instance.
3. Note the static IP address — you'll point DNS at it in Step 7.

## Step 4 — Open the firewall for HTTP/HTTPS

1. Click into the `loom-api` instance → **Networking** tab.
2. Under **IPv4 Firewall**, make sure rules exist for:
   - SSH, TCP, 22 (should already be there)
   - HTTP, TCP, 80
   - HTTPS, TCP, 443
   Add any that are missing.

## Step 5 — Connect and run the setup script

1. Click into the `loom-api` instance → **Connect** tab → **Connect using
   SSH** (opens a terminal right in your browser — no local setup needed).
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
   - `ANTHROPIC_API_KEY` — your real key
   - `LOOM_ADMIN_KEYS` — generate one with:
     `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
   - `CORS_ORIGINS=https://autostrat.net,https://www.autostrat.net`
   - `CONTACT_EMAIL_TO=saileshathreya@autostrat.net` (already the default)
   - `SMTP_*` values, once you've set up SES or another provider — fine to
     leave blank for now; the contact form still works and just skips
     sending until these are filled in.

   Save with `Ctrl+O`, then `Enter`, then exit with `Ctrl+X`.

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

## Step 7 — Install Caddy for free automatic HTTPS

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

Caddy won't be able to get a real certificate until DNS actually points at
this server — that's the next step.

## Step 8 — Point api.autostrat.net at the instance

1. AWS Console → **Route 53** → your `autostrat.net` hosted zone.
2. **Create record**: name `api`, type **A**, value = the static IP from
   Step 3.
3. Wait a few minutes for DNS to propagate, then reload Caddy so it
   notices and requests the certificate:
   ```
   sudo systemctl restart caddy
   ```
4. Test it:
   ```
   curl https://api.autostrat.net/health
   ```
   You should get `{"status":"ok"}` over a real HTTPS connection.

## Step 9 — Create your production tenant

From your own machine (or the SSH session — either works):

```
LOOM_BASE_URL=https://api.autostrat.net LOOM_ADMIN_KEY=<the LOOM_ADMIN_KEYS value from your .env> python seed_data.py
```

Save the tenant API key and demo login it prints (or create a real user
for yourself the same way, via `/admin/tenants/{id}/users`).

## Step 10 — Re-deploy the front end

`index.html` already points at `https://api.autostrat.net` automatically
once it's not running on localhost — no edit needed. Just re-upload it the
way you always do:

```
aws s3 cp index.html s3://<your-bucket-name>/index.html
aws cloudfront create-invalidation --distribution-id <your-distribution-id> --paths "/*"
```

## Step 11 — End-to-end test

Visit `https://autostrat.net`, log in with the credentials from Step 9,
and run each of the five agents once. Check the Audit Log tab to confirm
everything's being recorded.

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
