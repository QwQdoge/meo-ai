# Local Meo AI Cloud + Cloudflare Tunnel

This is the cheapest first deployment for Meo AI: the Cloud/Relay process runs on the Legion, while Cloudflare Tunnel publishes `https://ai.meoarch.org` without opening an inbound router port.

## Security model

- The Meo AI Cloud container is non-root and read-only apart from `/tmp`.
- Supabase service-role credentials live only in the local `.env` file and are never copied into the image.
- Cloudflare tunnel credentials live only under `cloudflared/` and are ignored by Git.
- The Cloud service is not published with a Docker host port. Only the `cloudflared` container can reach it on the private Compose network.
- Browser CORS is an exact allowlist; production should include only trusted Meo web origins.

## 1. Install prerequisites on Arch

```bash
sudo pacman -S --needed docker docker-compose cloudflared
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and back in once after adding yourself to the `docker` group, or use `sudo docker ...` until then.

## 2. Prepare the Meo Cloud environment

```bash
cd ~/Projects/meo-ai/meo/cloud/deploy/local
cp .env.example .env
chmod 600 .env
```

Edit `.env` and set:

- `MEO_SUPABASE_URL`
- `MEO_SUPABASE_PUBLISHABLE_KEY`
- `MEO_SUPABASE_SERVICE_ROLE_KEY`

Keep these production values:

```text
MEO_ACCOUNT_URL=https://account.meoarch.org
MEO_ALLOWED_WEB_ORIGINS=https://account.meoarch.org
PORT=8080
```

Never commit `.env`.

## 3. Create the Cloudflare Tunnel

The domain must already use Cloudflare DNS.

```bash
cloudflared tunnel login
cloudflared tunnel create meo-ai
cloudflared tunnel list
```

The create command prints a tunnel UUID and a credentials JSON path, normally under `~/.cloudflared/`.

Create the public DNS route:

```bash
cloudflared tunnel route dns meo-ai ai.meoarch.org
```

Cloudflare documents this command as creating a CNAME to `<TUNNEL_UUID>.cfargotunnel.com`.

## 4. Put the tunnel credentials beside Compose

Replace `<UUID>` below with the UUID printed by `cloudflared tunnel create meo-ai`:

```bash
mkdir -p cloudflared
cp cloudflared/config.example.yml cloudflared/config.yml
cp ~/.cloudflared/<UUID>.json cloudflared/<UUID>.json
chmod 600 cloudflared/<UUID>.json
```

Edit `cloudflared/config.yml` and replace both placeholder UUIDs with the real UUID.

Do not copy `cert.pem` into this directory. The running tunnel needs only the tunnel credentials JSON; the account certificate is used by the management CLI.

## 5. Validate before exposing it

Build and start only the Cloud service first:

```bash
docker compose build meo-ai-cloud
docker compose up -d meo-ai-cloud
docker compose ps
```

The service intentionally has no published host port. Validate its internal health endpoint without exposing one:

```bash
docker compose exec -T meo-ai-cloud \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read().decode())"
```

Expected response:

```json
{"ok":true,"service":"meo-ai-cloud"}
```

## 6. Start the tunnel

```bash
docker compose up -d

docker compose ps
docker compose logs --tail=100 cloudflared
```

Then verify from another network or browser:

```bash
curl -fsS https://ai.meoarch.org/health
```

Expected response:

```json
{"ok":true,"service":"meo-ai-cloud"}
```

## 7. Deploy the Account connect-device page

The account repository already points to `https://ai.meoarch.org` by default. Run its verification workflow first, then the protected production deployment:

```bash
gh workflow run verify.yml -R QwQdoge/MeoArch-account
gh run watch -R QwQdoge/MeoArch-account
```

After verification succeeds:

```bash
gh workflow run deploy.yml \
  -R QwQdoge/MeoArch-account \
  -f confirm_production=DEPLOY

gh run watch -R QwQdoge/MeoArch-account
```

That production workflow runs Flutter analyze/tests and Edge Function checks before deploying to Cloudflare Pages.

## 8. Connect the Legion

After installing the packaged Meo AI device bridge:

```bash
meo-connect-device
```

Normal UX:

```text
browser opens Meo Account
→ show this computer
→ Allow
→ re-auth only if required
→ narrow device token stored in KWallet
→ non-secret agentd config written locally
→ meo-agentd user service starts
```

Check it with:

```bash
systemctl --user status meo-agentd.service
journalctl --user -u meo-agentd.service -n 100 --no-pager
```

## Operations

Update to new code:

```bash
git pull --ff-only
docker compose build --pull meo-ai-cloud
docker compose up -d
```

Stop the public endpoint:

```bash
docker compose down
```

The DNS record may remain; while the tunnel is offline Cloudflare will not reach the origin.

## Later migration to a VPS or managed container host

The application itself does not depend on Cloudflare Tunnel. Move the same `meo/cloud/Dockerfile` to a managed host, inject the same environment variables, terminate HTTPS there, and point `ai.meoarch.org` at the new service. Device and browser protocols do not change.
