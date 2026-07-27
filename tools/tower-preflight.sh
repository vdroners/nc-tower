#!/usr/bin/env bash
# Control Tower preflight gates (G00 layout, G01 version, G16 attribution)
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
check G00 "TowerController" test -f lib/Controller/TowerController.php

ver=$(grep -oE '<version>[0-9]+\.[0-9]+\.[0-9]+</version>' appinfo/info.xml | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
check G01 "version readable" test -n "$ver"

check G16 "LICENSE" test -f LICENSE
check G16 "CREDITS.md" test -f CREDITS.md
check G16 "CREDITS names Wolfgang" grep -q 'Wolfgang' CREDITS.md
check G16 "README Attribution" grep -qi 'Attribution\|Fork lineage\|zomtec2311/admincockpit' README.md
check G16 "info.xml upstream author" grep -q 'Wolfgang' appinfo/info.xml
check G16 "app id nc_tower" grep -q '<id>nc_tower</id>' appinfo/info.xml
check G16 "name Control Tower" grep -q '<name>Control Tower</name>' appinfo/info.xml

# Hard rule: no docker.sock reference in PHP for mounting guidance
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

exit "$fail"
