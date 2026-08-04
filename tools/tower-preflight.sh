#!/usr/bin/env bash
# NC Tower preflight gates
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
fail=0

check() {
  local id="$1" msg="$2"
  shift 2
  if "$@"; then
    echo "PASS $id $msg"
  else
    echo "FAIL $id $msg"
    fail=1
  fi
}

note_fail() {
  echo "FAIL $1 $2"
  fail=1
}

# --- G00 tree ---------------------------------------------------------------
check G00 "info.xml" test -f appinfo/info.xml
check G00 "routes.php" test -f appinfo/routes.php
check G00 "Application.php" test -f lib/AppInfo/Application.php
check G00 "TowerController" test -f lib/Controller/TowerController.php
check G00 "standalone plan" test -f docs/plans/control-tower-standalone.md
check G00 "vue rebuild plan" test -f docs/plans/control-tower-vue-rebuild.md
check G00 "capability matrix" test -f docs/CAPABILITY_MATRIX.md
check G00 "sidecar .env present" test -f sidecar/.env
check G00 "sidecar .env gitignored" grep -q 'sidecar/.env' .gitignore

ver=$(grep -oE '<version>[0-9]+\.[0-9]+\.[0-9]+</version>' appinfo/info.xml | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
check G01 "version readable" test -n "$ver"

# --- G16 attribution --------------------------------------------------------
check G16 "LICENSE" test -f LICENSE
check G16 "CREDITS.md" test -f CREDITS.md
check G16 "CREDITS names Wolfgang" grep -q 'Wolfgang' CREDITS.md
check G16 "README Attribution" grep -qi 'Attribution\|Fork lineage\|Heritage\|CREDITS.md' README.md
check G16 "info.xml sole author Sarge" grep -q '>Sarge</author>' appinfo/info.xml
if grep -q 'Wolfgang' appinfo/info.xml; then
  note_fail G16 "info.xml still lists Wolfgang as author (heritage belongs in CREDITS.md)"
else
  echo "PASS G16 info.xml no Wolfgang author"
fi
check G16 "app id nc_tower" grep -q '<id>nc_tower</id>' appinfo/info.xml
check G16 "name NC Tower" grep -q '<name>NC Tower</name>' appinfo/info.xml

# --- G30 PHP syntax (1.14.0 provenance scrub left unterminated /** headers) ---
g30_lint() {
  find lib appinfo templates -name '*.php' -print0 2>/dev/null \
    | xargs -0 -n1 php -l 2>&1 | grep -v 'No syntax errors' || true
}
if command -v php >/dev/null 2>&1; then
  bad=$(g30_lint)
  if [[ -n "$bad" ]]; then
    note_fail G30 "php -l failures"
    printf '%s\n' "$bad" | sed 's/^/    /'
  else
    echo "PASS G30 all PHP files lint clean"
  fi
elif [[ -n "$(docker ps -q -f name=cloud_app 2>/dev/null)" ]]; then
  img=$(docker inspect -f '{{.Image}}' cloud_app)
  bad=$(docker run --rm -v "$ROOT:/src:ro" --workdir /src --entrypoint sh "$img" -c \
    'find lib appinfo templates -name "*.php" -print0 | xargs -0 -n1 php -l 2>&1' \
    | grep -v 'No syntax errors' || true)
  if [[ -n "$bad" ]]; then
    note_fail G30 "php -l failures"
    printf '%s\n' "$bad" | sed 's/^/    /'
  else
    echo "PASS G30 all PHP files lint clean"
  fi
else
  echo "SKIP G30 php -l (no php-cli / cloud_app)"
fi

# --- G10 routes -------------------------------------------------------------
for route in "page#ops" "page#host" "page#tools" "tower#hostGpu" "tower#fanSet" \
             "tower#stackAction" "tower#containerExec" "tower#backupRun" "tower#dockerDf"; do
  check G10 "route $route" grep -q "$route" appinfo/routes.php
done

# --- G13/G14 security invariants -------------------------------------------
if grep -R "docker.sock" lib/ --include='*.php' | grep -qi mount; then
  note_fail G13 "PHP must not mount docker.sock"
else
  echo "PASS G13 no docker.sock mount in PHP"
fi

if grep -q 'docker.sock:/var/run/docker.sock:ro' sidecar/docker-compose.yml; then
  note_fail G15 "sidecar sock still :ro (mutators need rw)"
else
  echo "PASS G15 sidecar sock not forced :ro"
fi

for f in sidecar/docker-compose.yml lib/Controller/TowerController.php; do
  if grep -q "changeme" "$f"; then
    note_fail G17 "$f must not default token to changeme"
  else
    echo "PASS G17 no changeme default in $f"
  fi
done

# The browser must never send the sidecar header; naming the config key in
# operator help text is fine, shipping the value or the header is not.
if grep -rn 'X-Ops-Token' src/ >/dev/null 2>&1; then
  note_fail G17 "front-end source must never send X-Ops-Token"
else
  echo "PASS G17 front end never sends X-Ops-Token"
fi

tok=$(grep -E '^NC_TOWER_SIDECAR_TOKEN=' sidecar/.env | cut -d= -f2- || true)
if [[ -z "$tok" || "$tok" == "changeme" ]]; then
  note_fail G17 "sidecar/.env token missing or changeme"
else
  echo "PASS G17 sidecar/.env has non-changeme token"
  if [[ -f js/nc_tower-app.js ]] && grep -qF "$tok" js/nc_tower-app.js; then
    note_fail G17 "built bundle contains the literal sidecar token"
  else
    echo "PASS G17 built bundle does not contain the token value"
  fi
fi

if grep -q prune appinfo/routes.php; then
  note_fail G18 "system prune route present"
else
  echo "PASS G18 no system prune in routes"
fi
if grep -qE 'host-shell|tower#shell' appinfo/routes.php; then
  note_fail G18 "host-shell route present"
else
  echo "PASS G18 no host-shell route"
fi

# --- G19 build --------------------------------------------------------------
check G19 "package.json" test -f package.json
check G19 "webpack config" test -f webpack.config.js
check G19 "src entry" test -f src/main.js
check G19 "widget entry" test -f src/widget.js
check G19 "vue-demi prebuild hook" grep -q 'fix-vue-demi' package.json
check G19 "app bundle built" test -f js/nc_tower-app.js
check G19 "widget bundle built" test -f js/nc_tower-widget.js
# A stub or failed build still leaves a file behind; require real content.
if [[ -f js/nc_tower-app.js ]] && [[ $(stat -c%s js/nc_tower-app.js) -gt 200000 ]]; then
  echo "PASS G19 app bundle is a real build"
else
  note_fail G19 "app bundle missing or suspiciously small"
fi
for tpl in index ops host tools apps system user; do
  check G19 "template $tpl mounts bundle" grep -q "nc_tower-app" "templates/$tpl.php"
  check G19 "template $tpl has mount point" grep -q 'id="nc_tower"' "templates/$tpl.php"
done

# --- G23 template references ------------------------------------------------
# webpack compiles a template that reads an undeclared name; the failure only
# appears as a render-time TypeError in the browser. Assert the surface.
if [[ -d node_modules ]]; then
  if node scripts/check-template-refs.mjs >/dev/null 2>&1; then
    echo "PASS G23 every name used in a template is declared"
  else
    note_fail G23 "undefined template reference (run npm run check:refs)"
    node scripts/check-template-refs.mjs 2>&1 | sed 's/^/    /'
  fi
else
  echo "SKIP G23 template refs (node_modules not installed)"
fi

# --- G26 house style --------------------------------------------------------
# The estate convention is an inline-SVG registry per app (GcsIcon, NcPrintIcon)
# and nc-<app>- class prefixes. NC Tower used Unicode glyphs and a bare
# tower- prefix until 1.10.0.
check G26 "icon component present" test -f src/components/NcTowerIcon.vue
if grep -rlP '[\x{25B4}\x{25B8}\x{25B2}\x{25BC}\x{25CE}\x{21BB}]' src/ --include=*.vue 2>/dev/null | grep -qv NcTowerIcon.vue; then
  note_fail G26 "Unicode glyph used as an icon (use NcTowerIcon)"
  grep -rlP '[\x{25B4}\x{25B8}\x{25B2}\x{25BC}\x{25CE}\x{21BB}]' src/ --include=*.vue | grep -v NcTowerIcon.vue | sed 's/^/    /'
else
  echo "PASS G26 no Unicode glyphs standing in for icons"
fi
if grep -rE '(="|\x27|\.|--)tower-' src/ --include=*.vue >/dev/null 2>&1; then
  note_fail G26 "class prefix must be nc-tower-, not tower-"
else
  echo "PASS G26 classes use the nc-tower- prefix"
fi
check G26 "app icon rebranded off upstream" grep -q 'NC Tower' img/app.svg
check G26 "chart component present" test -f src/components/TowerChart.vue
check G26 "sparkline component present" test -f src/components/Sparkline.vue
check G26 "job panel present" test -f src/components/JobPanel.vue
check G26 "vitest configured" test -f vitest.config.cjs
check G26 "triage rules covered by tests" test -f src/__tests__/health.spec.js

# --- G21 admin gating -------------------------------------------------------
# Admin gating is by omission: Nextcloud requires admin unless a controller
# method opts out. One stray attribute anywhere would expose host mutators,
# so assert across every controller, not just PageController.
if grep -rn '^\s*#\[NoAdminRequired\]' lib/Controller/ >/dev/null 2>&1; then
  note_fail G21 "active #[NoAdminRequired] found in lib/Controller"
  grep -rn '^\s*#\[NoAdminRequired\]' lib/Controller/ | sed 's/^/    /'
else
  echo "PASS G21 no active NoAdminRequired in any controller"
fi

# --- G22 dead weight --------------------------------------------------------
dead=0
for f in js/nc_tower-main.js js/nc_tower-apps.js js/nc_tower-system.js js/nc_tower-user.js js/nc_tower-ops.js; do
  if [[ -f "$f" ]]; then
    note_fail G22 "prebuilt bundle still present: $f"
    dead=1
  fi
done
[[ $dead -eq 0 ]] && echo "PASS G22 prebuilt Admin Cockpit bundles removed"

# --- G20 payload shape ------------------------------------------------------
# The 1.8.1 defects all passed every route gate: the routes existed and the
# files were deployed, but the field names the UI reads had drifted. Assert
# the contract itself.
SIDECAR_URL="${NC_TOWER_SIDECAR_URL:-http://127.0.0.1:18765}"
if [[ -z "$tok" ]]; then
  echo "SKIP G20 payload shape (no sidecar token)"
elif ! curl -fsS -m 5 -H "X-Ops-Token: $tok" "$SIDECAR_URL/health" >/dev/null 2>&1; then
  echo "SKIP G20 payload shape (sidecar unreachable at $SIDECAR_URL)"
else
  payload_gate() {
    local id="$1" path="$2" script="$3"
    local body
    if ! body=$(curl -fsS -m 90 -H "X-Ops-Token: $tok" "$SIDECAR_URL$path" 2>/dev/null); then
      note_fail "$id" "could not fetch $path"
      return
    fi
    if printf '%s' "$body" | python3 -c "$script"; then
      echo "PASS $id $path"
    else
      note_fail "$id" "$path payload shape"
    fi
  }

  payload_gate G20 /host/proc '
import sys, json
d = json.load(sys.stdin)
rows = d.get("processes") or []
sys.exit(0 if rows and all("pid" in r and "command" in r and "cpu" in r for r in rows) else 1)
'
  payload_gate G20 /host/packages '
import sys, json
d = json.load(sys.stdin)
rows = d.get("packages") or []
sys.exit(0 if all("new_version" in r or "raw" in r for r in rows) else 1)
'
  # 1.9.2: healthcheck probes drowned every real lifecycle event.
  payload_gate G20 '/docker/events?since=6h' '
import sys, json
d = json.load(sys.stdin)
rows = d.get("events") or []
if not rows:
    sys.exit(0)
sys.exit(1 if all(str(r.get("Action","")).startswith("exec_") for r in rows) else 0)
'
  payload_gate G20 /host/updates '
import sys, json
d = json.load(sys.stdin)
need = ("packages", "restarts_docker", "reboot_required", "count")
sys.exit(0 if all(k in d for k in need) else 1)
'
  payload_gate G20 /host/history '
import sys, json
d = json.load(sys.stdin)
rows = d.get("samples") or []
if not rows:
    sys.exit(0)
sys.exit(0 if all("ts" in r and "mem_pct" in r for r in rows) else 1)
'
  payload_gate G20 /services/probe '
import sys, json
d = json.load(sys.stdin)
rows = d.get("services") or []
if not rows:
    sys.exit(1)
if not all("reachable" in r and "http" in r for r in rows):
    sys.exit(1)
# A service answering 404 is reachable. Guacamole and MediaMTX do exactly that
# while being healthy, and a naive check would report both as down.
bad = [r for r in rows if r.get("http") and not r["reachable"]]
sys.exit(1 if bad else 0)
'
  payload_gate G20 /jobs '
import sys, json
d = json.load(sys.stdin)
sys.exit(0 if isinstance(d.get("jobs"), list) else 1)
'
  payload_gate G20 /host/smart '
import sys, json
d = json.load(sys.stdin)
if d.get("unavailable"):
    sys.exit(0)
disks = d.get("disks") or []
# A powered-on drive reporting single-digit hours means the attribute parser
# grabbed the next row ID again (the 1.8.1 defect).
bad = [x for x in disks if x.get("power_on_hours") is not None and 0 < x["power_on_hours"] < 100]
nas_ok = all("ok" in n for n in (d.get("nas_mounts") or []))
sys.exit(0 if not bad and nas_ok else 1)
'
  # --- G31 host inventory payload shape (1.15.0) ---
  payload_gate G31 /host/hardware '
import sys, json
d = json.load(sys.stdin)
sys.exit(0 if d.get("ok") and isinstance(d.get("dmi"), dict) and isinstance(d.get("cpu"), dict) else 1)
'
  payload_gate G31 /host/storage '
import sys, json
d = json.load(sys.stdin)
sys.exit(0 if d.get("ok") and isinstance(d.get("raid"), dict) and "lsblk" in d else 1)
'
  payload_gate G31 /host/posture '
import sys, json
d = json.load(sys.stdin)
sys.exit(0 if d.get("ok") and "ntp" in d and isinstance(d.get("certs"), list) else 1)
'
fi

# --- G32 NC admin routes registered (1.15.0) ---
if grep -q "ncAdmin#log" appinfo/routes.php \
  && grep -q "ncAdmin#setupChecks" appinfo/routes.php \
  && grep -q "ncAdmin#jobs" appinfo/routes.php \
  && test -f lib/Controller/NcAdminController.php; then
  echo "PASS G32 NC admin routes + controller present"
else
  note_fail G32 "ncadmin routes / NcAdminController missing"
fi

exit "$fail"
