# Phase 9 Deployment Runbook

This folder contains the production deployment assets for Phase 9.

## Files

- `nginx/supportlegal.conf` — Nginx reverse proxy example with TLS and SSE-safe routing.
- `setup_ec2.sh` — EC2 bootstrap script for Docker, Compose, Nginx, and Certbot.
- `scripts/backup_legal_data.sh` — Backup script for SQLite and Qdrant volumes.
- `scripts/restore_legal_data.sh` — Restore script for SQLite and Qdrant volumes.

## Deploy order

1. Provision an Ubuntu 22.04 EC2 instance.
2. Install Docker, Docker Compose, Nginx, and Certbot.
3. Copy the repository to the instance and create a private `.env` file.
4. Start the backend stack with `docker compose up -d`.
5. Apply the Nginx configuration and issue a certificate with Certbot.
6. Deploy the frontend to Vercel and set `NEXT_PUBLIC_API_BASE_URL` to the public API domain.

## Rollback

- Frontend: revert the Vercel deployment to the previous successful build.
- Backend: `docker compose down`, restore the previous `.env`, and restart the stack.
- Nginx: restore the prior config file and reload the service.

## Backup and restore

### Backup

Run the backup script from the repository root:

```bash
./scripts/backup_legal_data.sh
```

The script creates timestamped SQLite and Qdrant archives in `./backups/` by default.

### Restore

```bash
./scripts/restore_legal_data.sh ./backups/<timestamp>
```

Restore should only be run while the stack is stopped.

## Secret rotation

1. Generate new API keys in the provider dashboards.
2. Update the secret store or EC2 `.env` file.
3. Redeploy the backend stack.
4. Rotate the Vercel environment variable if the frontend origin changes.

### OpenRouter note

If `CLASSIFIER_PROVIDER` or `GENERATION_PROVIDER` is set to `openrouter`, make sure `OPENROUTER_API_KEY` is present in the backend `.env` file or secret store. Optional settings: `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL`, `OPENROUTER_APP_URL`, and `OPENROUTER_APP_TITLE`.

## Quick incident checks

- `docker compose ps`
- `curl http://127.0.0.1:8000/health`
- `curl -I https://api.domain.com/api/v1/health`
- Check `/var/log/nginx/error.log`
- Check container restart counts

