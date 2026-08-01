# Control Tower standalone (v1.8)

Checked-in summary of the mega port/adapt program. Canonical Cursor plan lived at `tower_standalone_expand_87dc5c48`.

## Scope

- **In:** Portainer day-ops (allowlisted), custom Webmin module adapt, hybrid Host RO + systemd restart
- **Out:** host shell, filemin, useradmin/firewall editors, Ollama mgr, VPN peer editors, system prune, Alfred action queue

## Architecture

Nextcloud `nc_tower` (admin UI + CSRF) → token → `nc_tower_sidecar` (privileged host agent, docker.sock) → Docker/host CLIs.

## Token rotate

```bash
TOKEN=$(openssl rand -hex 32)
printf 'NC_TOWER_SIDECAR_TOKEN=%s\n' "$TOKEN" > /media/4TB/nc-tower/sidecar/.env
chmod 600 /media/4TB/nc-tower/sidecar/.env
docker exec -u www-data cloud_app php /var/www/html/occ config:system:set nc_tower_sidecar_token --value="$TOKEN"
cd /media/4TB/nc-tower && make sidecar-up
```

## Verify

```bash
cd /media/4TB/nc-tower && make ship RESTART=1
curl -fsS -H "X-Ops-Token: $(grep TOKEN sidecar/.env | cut -d= -f2)" http://127.0.0.1:18765/health
curl -fsS -H "X-Ops-Token: $(grep TOKEN sidecar/.env | cut -d= -f2)" http://127.0.0.1:18765/host/summary | head -c 200
docker inspect cloud_app --format '{{json .Mounts}}' | grep -q docker.sock && echo FAIL_sock || echo PASS_no_sock
```

See [CAPABILITY_MATRIX.md](../CAPABILITY_MATRIX.md) for full disposition tables.
