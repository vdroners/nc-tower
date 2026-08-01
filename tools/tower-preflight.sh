#!/usr/bin/env bash
# Control Tower preflight gates (G00 layout, G01 version, G16 attribution, Ops 1.5)
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

check G00 "info.xml" test -f appinfo/info.xml
check G00 "routes.php" test -f appinfo/routes.php
check G00 "Application.php" test -f lib/AppInfo/Application.php
check G00 "main js" test -f js/nc_tower-main.js
check G00 "ops js" test -f js/nc_tower-ops.js
check G00 "ops css" test -f css/nc_tower-ops.css
check G00 "ops template" test -f templates/ops.php
check G00 "tools template" test -f templates/tools.php
check G00 "subnav partial" test -f templates/partials/subnav.php
check G00 "TowerController" test -f lib/Controller/TowerController.php
check G00 "ops plan" test -f docs/plans/control-tower-ops-ui.md

ver=$(grep -oE '<version>[0-9]+\.[0-9]+\.[0-9]+</version>' appinfo/info.xml | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
check G01 "version readable" test -n "$ver"

check G16 "LICENSE" test -f LICENSE
check G16 "CREDITS.md" test -f CREDITS.md
check G16 "CREDITS names Wolfgang" grep -q 'Wolfgang' CREDITS.md
check G16 "README Attribution" grep -qi 'Attribution\|Fork lineage\|zomtec2311/admincockpit' README.md
check G16 "info.xml upstream author" grep -q 'Wolfgang' appinfo/info.xml
check G16 "app id nc_tower" grep -q '<id>nc_tower</id>' appinfo/info.xml
check G16 "name Control Tower" grep -q '<name>Control Tower</name>' appinfo/info.xml

if grep -R "docker.sock" lib/ --include='*.php' | grep -qi mount; then
  echo "FAIL G13 PHP must not mount docker.sock"
  fail=1
else
  echo "PASS G13 no docker.sock mount in PHP"
fi

if grep -R "NoAdminRequired" lib/Controller/PageController.php >/dev/null 2>&1; then
  echo "FAIL G14 PageController still has NoAdminRequired"
  fail=1
else
  echo "PASS G14 PageController admin-gated"
fi

# Routes for Ops 1.5
check G10 "ops page route" grep -q "page#ops" appinfo/routes.php
check G10 "tools page route" grep -q "page#tools" appinfo/routes.php
check G10 "tower gpu route" grep -q "tower#hostGpu" appinfo/routes.php
check G10 "tower fan POST" grep -q "tower#fanSet" appinfo/routes.php
check G10 "tower stack up" grep -q "tower#stackUp" appinfo/routes.php
check G10 "container action POST" grep -q "tower#containerAction" appinfo/routes.php

# Sidecar sock rw documented (compose file)
if grep -q 'docker.sock:/var/run/docker.sock:ro' sidecar/docker-compose.yml; then
  echo "FAIL G15 sidecar sock still :ro (mutators need rw)"
  fail=1
else
  echo "PASS G15 sidecar sock not forced :ro"
fi

# Token warn (non-fatal)
if grep -q 'changeme' sidecar/docker-compose.yml; then
  echo "WARN G17 default sidecar token still changeme — set NC_TOWER_SIDECAR_TOKEN in prod"
fi

exit "$fail"
