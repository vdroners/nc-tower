# Control Tower Phase 1

## Goals

1. GitHub fork of Admin Cockpit → `vdroners/nc-tower`, rebranded **Control Tower** (`nc_tower`)
2. CREDITS + README attribution (AGPL)
3. Harden: admin-only pages, CSRF on notify*
4. Deploy to `cloud_app` custom_apps
5. Read-only sidecar: health, host summary, containers, stacks, ops inbox
6. Tools deep-links API
7. Preflight gates G00/G01/G08–G10/G13/G14/G16

## Verify

```bash
cd /media/4TB/nc-tower
make ship RESTART=1
docker exec cloud_app grep '<version>' /var/www/html/custom_apps/nc_tower/appinfo/info.xml
curl -fsS -H 'X-Ops-Token: changeme' http://127.0.0.1:18765/health
docker inspect cloud_app --format '{{json .Mounts}}' | grep -q docker.sock && echo FAIL || echo PASS_no_sock
```

## Out of scope (Phase 1)

- Stack start/stop, console, Webmin OS editors
- GitHub push without operator OK
- Replacing Portainer/Webmin
