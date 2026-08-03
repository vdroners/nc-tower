# Control Tower — privacy / sidecar disclosure

Control Tower (`nc_tower`) is a Nextcloud admin app. By itself it only uses
Nextcloud session credentials and public OCP APIs (user/group/app enablement,
system info that PHP can read inside the Nextcloud container).

## Optional host sidecar

Host health, Docker day-ops, SMART/GPU, and package updates require a separate
**nc_tower_sidecar** process (see `sidecar/`). That agent is:

- **Not required** to enable the Nextcloud app or use Apps / Users / System tabs
  that talk only to Nextcloud.
- **Privileged when deployed** (Docker socket, host PID namespace, allowlisted
  host commands). The shared token is host-root equivalent.
- Configured by the administrator (`sidecar_url` in Settings → Control Tower,
  token in Nextcloud `config.php` / sidecar `.env`). Defaults do not point at
  any vendor lab IP.

Data the sidecar can access is whatever the operator mounts and allowlists
(compose directories, disk paths, container name patterns). Empty allowlists
mean no mutate actions.

## Deep links

External console URLs (Portainer, Webmin, monitoring UIs, …) are admin
settings with empty defaults. The app does not phone home and does not collect
telemetry beyond what Nextcloud already logs.
