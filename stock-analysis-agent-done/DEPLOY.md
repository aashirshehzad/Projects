# Deploying stock-analysis-agent (Docker → AWS EC2 free tier)

The app is a single `uvicorn app.main:app` process. It needs three env vars —
`GEMINI_API_KEY` (required), `TAVILY_API_KEY`, `SEC_EDGAR_USER_AGENT` — supplied
at runtime from a `.env` file that is never baked into the image.

`/analyze` against the full 11-ticker basket takes 40–90 s and briefly spikes
RAM past 1 GB. On the free-tier `t3.micro` (1 GB) send **1–3 tickers per run**
and keep the 2 GB swap file (below).

---

## 1. Build & test locally (Docker Desktop)

From the repo root:

```bash
# .env must exist here with real keys (it is git-ignored)
docker compose up --build
```

Then check:

```bash
curl http://localhost:8000/health
```

Open <http://localhost:8000> — the dashboard should load. Try a 1–2 ticker
analysis from the watchlist. `Ctrl+C` to stop; `docker compose down` to remove.

Rebuild after code changes: `docker compose up --build`.

---

## 2. Launch the EC2 instance

AWS console → **EC2 → Launch instance**:

- **AMI:** Ubuntu Server 24.04 LTS (or Amazon Linux 2023)
- **Type:** `t3.micro` — must say *Free tier eligible*
- **Key pair:** create one, download the `.pem`
- **Storage:** 20 GB gp3 (free tier allows up to 30)
- **Security group** inbound rules:
  - SSH `22` — source **My IP**
  - Custom TCP `8000` — source `0.0.0.0/0` (or **My IP** to keep it private)

After it boots, note the **Public IPv4 address**.

---

## 3. First-boot setup on the box

```bash
ssh -i /path/to/key.pem ubuntu@PUBLIC_IP
```

### Swap first (1 GB RAM needs it)

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Log out and back in so the group takes effect.

---

## 4. Get the code and secrets onto the box

**Option A — git (repo must be pushed to GitHub):**

```bash
git clone https://github.com/<you>/<repo>.git
cd <repo>/stock-analysis-agent   # if it lives in a monorepo subdir
```

**Option B — copy from your laptop:**

```bash
# run this on your laptop, not the box
scp -i /path/to/key.pem -r /d/Projects/stock-analysis-agent ubuntu@PUBLIC_IP:~/
```

Create `.env` on the box (never committed):

```bash
cat > .env <<'EOF'
GEMINI_API_KEY=your-real-key
TAVILY_API_KEY=your-real-key
SEC_EDGAR_USER_AGENT=your-email@example.com stock-analysis-agent
EOF
chmod 600 .env
```

---

## 5. Run it

Add a `docker-compose.override.yml` next to `docker-compose.yml` on the box —
Compose merges it automatically, it's git-ignored, and the deploy workflow's
`git reset --hard` leaves it alone (unlike edits to the tracked compose file):

```bash
cat > docker-compose.override.yml <<'EOF'
services:
  web:
    mem_limit: 950m
    mem_reservation: 384m
EOF
```

Then:

```bash
docker compose up -d --build
docker compose logs -f          # watch startup
curl http://localhost:8000/health
```

The dashboard is now at `http://PUBLIC_IP:8000`.

`restart: unless-stopped` brings it back after a reboot or a crash.

---

## 6. Guardrails

- **Billing alarm:** Billing console → *Budgets* or a CloudWatch alarm at **$1**.
  Free tier is 750 h/month of `t3.micro` for the first 12 months only.
- **CPU credits:** a `t3.micro` in the default *unlimited* mode can incur small
  charges if you peg the CPU for long stretches. A few short `/analyze` runs are
  fine; switch the instance to *standard* credit mode if you want a hard cap.
- **Anyone with `http://PUBLIC_IP:8000` can spend your Gemini/Tavily quota.**
  Restrict the `:8000` rule to your IP, or put Caddy in front with basic auth.

---

## 7. Later: HTTPS with a domain

Add Caddy as a second compose service (automatic Let's Encrypt certs):

```yaml
  caddy:
    image: caddy:2
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    restart: unless-stopped
volumes:
  caddy_data:
```

`Caddyfile`:

```
your-domain.com {
    reverse_proxy web:8000
}
```

Point the domain's A record at the EC2 public IP, open `443`/`80` in the
security group, `docker compose up -d`. Certs issue automatically.

---

## 8. CI/CD — push to GitHub, box redeploys itself

`.github/workflows/deploy-stock-analysis-agent.yml` runs on every push to
`main` that touches `stock-analysis-agent/**`. It targets a **self-hosted
runner installed on the EC2 box**, which polls GitHub over an outbound
connection — so no inbound SSH rule and no SSH key in GitHub secrets. The job
just runs, on the box:

```
git fetch --prune origin && git reset --hard origin/main
docker compose up -d --build && docker image prune -f
```

then polls `/health` and fails (dumping logs) if it doesn't come up.

### One-time: install the runner on the box

GitHub repo → **Settings → Actions → Runners → New self-hosted runner** →
Linux / x64. Copy the commands it shows (they embed a short-lived token) — they
look like:

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
curl -o actions-runner-linux-x64.tar.gz -L https://github.com/actions/runner/releases/download/vX.Y.Z/actions-runner-linux-x64-X.Y.Z.tar.gz
tar xzf actions-runner-linux-x64.tar.gz
./config.sh --url https://github.com/aashirshehzad/Projects --token <TOKEN> --labels stock-ec2 --unattended
```

The `--labels stock-ec2` must match `runs-on: [self-hosted, stock-ec2]` in the
workflow. Then install it as a service so it survives reboots and logout:

```bash
sudo ./svc.sh install ubuntu
sudo ./svc.sh start
sudo ./svc.sh status
```

### Notes

- The runner runs as `ubuntu`, which is in the `docker` group, so `docker
  compose` works without sudo.
- The workflow deploys `/home/ubuntu/Projects/stock-analysis-agent` (the clone
  from §4) in place; it does **not** use `actions/checkout`, so `.env` and
  `docker-compose.override.yml` there are left untouched.
- Private repo: `git fetch` on the box needs stored credentials. The §4 HTTPS
  clone prompts once; run `git config --global credential.helper store` and do
  one manual `git pull` (paste a PAT as the password) so it's cached for the
  runner.
- Trigger a redeploy by hand anytime from the repo's **Actions** tab →
  *Deploy stock-analysis-agent* → **Run workflow**.
- Watch a deploy: **Actions** tab, or `sudo journalctl -u 'actions.runner.*' -f`
  on the box.
