# Briefing: Correct the deployment docs to match reality

`DEPLOY-LIGHTSAIL.md` and `PRODUCTION-READINESS.md` describe a deployment that
differs from the one that actually happened on 4–8 Sept 2026. Someone
following them today would hit the same failures the deployment session hit.

This is a **documentation-only** task. Do not change application code,
configuration, or infrastructure. Every correction below is a fact confirmed
from the live system.

`DEPLOY.md` is the App Runner scale-later path and already carries a banner
saying it is not the current route. **Leave it alone** except where noted in
item 10.

---

## A. Errors to correct in `DEPLOY-LIGHTSAIL.md`

### 1. DNS provider is Cloudflare, not Route 53

**Step 8** says "AWS Console → **Route 53** → your `autostrat.net` hosted zone."
This is wrong. DNS is managed at **Cloudflare**. Rewrite Step 8 to create the
`api` A record in the Cloudflare dashboard pointing at the static IP.

Add a warning: if the record is **proxied** (orange cloud) rather than
DNS-only, Caddy cannot complete the Let's Encrypt HTTP challenge and
certificate issuance fails. It must be **DNS-only** (grey cloud), at least
until the certificate is issued.

### 2. `CORS_ORIGINS` is missing the app subdomain

**Step 5** specifies:

```
CORS_ORIGINS=https://autostrat.net,https://www.autostrat.net
```

This is the single error that cost the most time during deployment — it was
hit twice. The product frontend is served from **`https://app.autostrat.net`**,
and listing the bare domain does **not** cover its subdomains. Correct to:

```
CORS_ORIGINS=https://autostrat.net,https://www.autostrat.net,https://app.autostrat.net
```

Add an explicit warning that every origin must be listed in full, subdomains
included, and that the value is read once at startup so `sudo systemctl
restart loom-api` is required after any change.

Add the verification step that was missing: after editing, confirm with
`grep CORS_ORIGINS ~/autostrat-loom-backend/.env` before restarting. During
deployment a `nano` edit silently failed to save the full line. Note the
`nano` habit: use `Ctrl+K` to delete a whole line before retyping it, rather
than editing in place.

### 3. Instance naming silently defaults

**Step 2 point 5** says "Name it something like `loom-api`." In practice the
instance was created without the name taking effect and ended up as
**`Ubuntu-1`**, while a pre-existing unrelated instance already held the name
`loom-api`. This caused real confusion.

Add a warning to confirm the name **after** creation on the Instances list,
and to check whether the intended name is already in use by another instance.

Record the current reality: the live backend instance is named **`Ubuntu-1`**.

### 4. The 512 MB plan needs swap — it will fall over without it

**Step 2 point 4** recommends the $5/month plan (512 MB RAM) with no further
comment. On 8 Sept 2026 this instance became **completely unreachable** — no
SSH, no HTTPS, while CPU sat idle. Cause: chronic out-of-memory. `journalctl`
showed the OOM killer firing roughly hourly for days, and memory pressure
severe enough to wedge the network stack (`systemd-networkd-wait-online`
timeouts).

Measured state before the fix: **414 MB usable, 0 B swap, ~122 MB available at
idle.**

Add a new step immediately after the systemd service step, titled something
like "Add swap — required on the 512 MB plan":

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=20' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

Verify with `free -h` — the Swap row should show 2.0Gi.

Warn that `/etc/fstab` must be checked with `cat /etc/fstab` after editing; a
malformed line there can prevent the instance booting.

Also add: **mask `fwupd`**, a firmware-update daemon with nothing to do on a
virtual instance, which was the process being OOM-killed hourly:

```bash
sudo systemctl disable --now fwupd-refresh.service fwupd-refresh.timer
sudo systemctl mask fwupd.service
```

Note that `fwupd.service` is a **static** unit — `disable` does not work on it,
it must be **masked**.

State plainly that swap makes the box stable but does not make 512 MB
generous; if agent runs push swap usage into the hundreds of MB, resize the
instance.

### 5. The frontend needs its own bucket and distribution

**Step 10** says `aws s3 sync dist/ s3://<your-bucket-name>/`, implying the
existing marketing-site hosting is reused. That is not what happened, and
reusing it would overwrite the marketing site.

Rewrite Step 10 to cover creating **separate** frontend hosting, in this
order:

1. Create a new S3 bucket (actual: `autostrat-app`), private, no static
   website hosting.
2. Request or reuse an ACM certificate covering `app.<domain>`. **The
   certificate must be in `us-east-1` regardless of where anything else
   lives** — CloudFront only reads certificates from that region. The
   deployment reused an existing wildcard `*.autostrat.net` certificate
   rather than issuing a new one.
3. Create a CloudFront distribution with the bucket as origin, using Origin
   Access Control so the bucket stays private.
4. **Set "Default root object" to `index.html`.** Omitting this breaks the
   bare root URL for a single-page app. This was hit during deployment.
5. Add the alternate domain name `app.<domain>` and attach the certificate.
6. In **Cloudflare**, add a CNAME for `app` pointing at the distribution
   domain.
7. Then `aws s3 sync dist/ s3://<bucket>/ --delete` and create a CloudFront
   invalidation for `/*`.

Record current values: bucket `autostrat-app`, distribution
**`E2YF1Y0LAQQTFV`** (`d33ugba59hfe7o.cloudfront.net`). Marketing site is a
separate bucket `autostrat-temp-site` on distribution **`E2ZCVTWM9KA4M8`**.

Explain why `--delete` matters: Vite emits hash-named bundles, so without it
every old bundle accumulates in the bucket forever.

### 6. The end-to-end test points at the wrong domain

**Step 11** says "Visit `https://autostrat.net`, sign up / log in". That is the
marketing site. The product is at **`https://app.autostrat.net`**. Correct it.

### 7. Browser SSH is unreliable — document key-based SSH instead

The doc's premise is that everything is done through the Lightsail browser SSH
terminal ("you don't need to install or configure anything on your own
machine"). That terminal **froze and disconnected repeatedly** across two
sessions.

Add a short section near Step 5 covering key-based SSH as the recommended
route: download the default key from Lightsail → **Account → SSH keys**,
restrict its permissions, and connect with
`ssh -i <key.pem> ubuntu@<static-ip>`.

Keep the browser terminal documented as a fallback, with the recovery
procedure: if it freezes, close it and open a fresh session, `cd` back into
the project folder, and **re-check state** (`systemctl status`, `git log`)
before re-running anything — work often completed despite the terminal
appearing dead.

### 8. Add a stale-DNS check for redeploys

Add to the "Deploying code changes later" section: before and after any
redeploy that involves new infrastructure, check Cloudflare for **stale or
duplicate records pointing at an old instance**. This caused intermittent,
confusing failures during deployment. Note that an old instance's static IP
should be released when the instance is deleted.

### 9. Frontend redeploy is a separate step from backend deploy

The "Deploying code changes later" section covers only `git pull` + `pip
install` + `systemctl restart` on the server. That deploys the **backend
only**.

This was hit on 8 Sept: a feature was merged and the backend deployed, but the
new UI did not appear because the frontend was never rebuilt. Add an explicit
note that any change under `frontend/` additionally requires:

```bash
cd frontend && npm run build
aws s3 sync dist/ s3://autostrat-app/ --delete
aws cloudfront create-invalidation --distribution-id E2YF1Y0LAQQTFV --paths "/*"
```

Add that a hard refresh (Ctrl+Shift+R) is needed to confirm, since CloudFront
and the browser both cache.

### 10. Note the default Caddy config is a placeholder

**Step 7** copies the project Caddyfile over the default, which is correct, but
add a warning: Caddy ships with a placeholder config (`:80 { ... }` serving
`/usr/share/caddy`), and if this copy step is missed or a terminal session
drops mid-step, the site serves Caddy's default page instead of the API.
Verify with `sudo systemctl status caddy` and a real request afterwards.

---

## B. Errors to correct in `PRODUCTION-READINESS.md`

### 11. `CORS_ORIGINS` — same omission, in two places

Item 1 and the item 3 environment-variable table both give
`https://autostrat.net,https://www.autostrat.net`. Both must include
`https://app.autostrat.net`. See item 2 above.

### 12. The architecture diagram is wrong about the frontend domain

The target-shape diagram shows the frontend at `autostrat.net`. In reality:

- `autostrat.net` — marketing site (bucket `autostrat-temp-site`,
  distribution `E2ZCVTWM9KA4M8`)
- `app.autostrat.net` — the React product (bucket `autostrat-app`,
  distribution `E2YF1Y0LAQQTFV`)
- `api.autostrat.net` — the backend (Lightsail `Ubuntu-1`, `44.253.87.35`)

Correct the diagram and item 4 accordingly.

### 13. Item 5 is out of date on the old demo login

Item 5 discusses the archived `index.html`. Record what actually happened
since: the marketing site's "Log in" links were repointed to
`https://app.autostrat.net`, and the orphaned `/login` and `/login.html`
objects were **deleted from the `autostrat-temp-site` bucket on 8 Sept 2026**.
The distribution has a custom error response that sends unmatched paths to the
homepage.

### 14. The deployment checklist is missing steps

Add to the backend checklist:

- [ ] Add 2 GB swap and set `vm.swappiness=20` — **required on the 512 MB plan**
- [ ] Mask `fwupd.service` and disable the `fwupd-refresh` units
- [ ] Confirm the instance name after creation; it can silently default
- [ ] Verify `CORS_ORIGINS` with `grep` after editing, before restarting
- [ ] Check Cloudflare for stale records pointing at any previous instance

Add to the frontend checklist:

- [ ] ACM certificate for `app.<domain>` exists **in us-east-1**
- [ ] CloudFront "Default root object" set to `index.html`
- [ ] Cloudflare CNAME for `app` points at the distribution
- [ ] `--delete` used on `s3 sync` so old hashed bundles do not accumulate

Add a new "Operational baseline" section recording what a healthy instance
looks like, so a future outage can be compared against it:

- `loom-api` active, ~107 MB resident
- `free -h`: ~414 Mi total, ~116 Mi available, 2.0 Gi swap with ~30 Mi used
- `https://api.autostrat.net/health` returns `{"status":"ok"}`
- `https://api.autostrat.net/` returns `{"detail":"Not Found"}` — this is
  **healthy**, it is FastAPI's 404 for an undefined root route, not an error

---

## C. One correction to `DEPLOY.md`

Its banner already flags it as the non-current path. Make one change: the
`CORS_ORIGINS` value in Step 3's environment-variable block has the same
missing-subdomain problem. Correct it there too so the error is not copied
forward if that path is ever taken.

---

## Constraints

- Documentation only. No code, config, or infrastructure changes.
- Do not invent values. Every identifier in this briefing (bucket names,
  distribution IDs, IP, instance name) is confirmed from the live system; do
  not add others.
- Preserve each document's existing voice and structure. These are corrections
  and insertions, not rewrites.
- Where a correction records something that went wrong, keep it brief and
  factual — the point is that the next person avoids it, not a narrative of
  the incident.

## Definition of done

- [ ] All 14 items above applied
- [ ] No remaining reference to Route 53 in `DEPLOY-LIGHTSAIL.md`
- [ ] `app.autostrat.net` present in every `CORS_ORIGINS` example across all
      three documents
- [ ] Swap and `fwupd` steps present in both the Lightsail walkthrough and the
      readiness checklist
- [ ] Frontend hosting documented as its own bucket and distribution, with the
      us-east-1 certificate and default-root-object requirements
- [ ] Committed, pushed, and merged via PR
