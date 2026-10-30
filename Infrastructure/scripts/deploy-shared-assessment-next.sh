#!/usr/bin/env bash
set -euo pipefail
app=$1
branch=$2
environment=$3
case "$app:$environment:$branch" in
  admin-react-v2:DEV:Development) port=3013 ;;
  corporate-react-v2:DEV:Development) port=3012 ;;
  admin-react-v2:UAT:UAT) port=3013 ;;
  corporate-react-v2:UAT:UAT) port=3014 ;;
  institute-react-v2:UAT:UAT) port=3012 ;;
  *) echo 'Unsupported deployment target'; exit 1 ;;
esac
exec 9>"/tmp/shared-assessment-${app}.lock"
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
export PATH=/home/ubuntu/.nvm/versions/node/v20.20.2/bin:$PATH
source_repo="/home/ubuntu/frontend/$app"
git -C "$source_repo" fetch origin "$branch:refs/remotes/origin/$branch"
revision=$(git -C "$source_repo" rev-parse "origin/$branch")
release="/home/ubuntu/releases/$app/${environment}-${revision:0:12}-$(date -u +%Y%m%dT%H%M%S)"
mkdir -p "$release"
git -C "$release" init -q
git -C "$release" fetch -q "$source_repo" "refs/remotes/origin/$branch"
git -C "$release" checkout -q -b "$branch" FETCH_HEAD
cp "$source_repo/.env.local" "$release/.env.local"
cd "$release"
if [[ -f pnpm-lock.yaml ]]; then
  pnpm install --frozen-lockfile --ignore-scripts
  pnpm run build
else
  npm ci --ignore-scripts --no-audit --no-fund
  npm run build
fi
if [[ "$environment" == UAT ]] && grep -rl 'dev\.pluginlive\.com' .next/static >/dev/null; then
  echo 'Refusing UAT deployment: DEV URL in bundle'; exit 1
fi
old_dir=$(systemctl show "$app.service" -p WorkingDirectory --value)
override="/etc/systemd/system/$app.service.d/zz-shared-assessment.conf"
backup="$release/previous-override.conf"
had_override=false
if sudo test -f "$override"; then sudo cp "$override" "$backup"; had_override=true; fi
rollback() {
  echo 'Deployment verification failed; restoring previous service configuration'
  if $had_override; then sudo cp "$backup" "$override"; else sudo rm -f "$override"; fi
  sudo systemctl daemon-reload
  sudo systemctl restart "$app.service"
}
sudo mkdir -p "$(dirname "$override")"
cat > "$release/service-override.conf" <<EOF
[Service]
WorkingDirectory=$release
ExecStart=
ExecStart=/home/ubuntu/.nvm/versions/node/v20.20.2/bin/node $release/node_modules/next/dist/bin/next start
EOF
sudo systemctl stop "$app.service"
python3 - "$old_dir" <<'PY'
from pathlib import Path
import sys,os,signal
for p in Path('/proc').iterdir():
 if not p.name.isdigit(): continue
 try:
  if os.readlink(p/'cwd')==sys.argv[1] and (p/'cmdline').read_bytes().startswith(b'next-server'):
   os.kill(int(p.name),signal.SIGTERM)
 except (FileNotFoundError,PermissionError,ProcessLookupError): pass
PY
sudo cp "$release/service-override.conf" "$override"
sudo systemctl daemon-reload
trap rollback ERR
sudo systemctl start "$app.service"
for attempt in $(seq 1 30); do
 if curl -fsS "http://127.0.0.1:$port/v2/" >/dev/null; then break; fi
 sleep 1
done
pid=$(systemctl show "$app.service" -p MainPID --value)
sudo ss -ltnp "sport = :$port" | grep -F "pid=$pid,"
python3 - "$port" "$app" <<'PY'
import sys,re,urllib.request
port,app=sys.argv[1:]
paths=['/assessment','/assessment/new?entityId=test&segment=corporate'] if app.startswith('admin') else (['/assessments','/dashboard'] if app.startswith('institute') else ['/assessments','/assessments/new','/dashboard','/roles'])
origin='http://127.0.0.1:'+port
for path in paths:
 html=urllib.request.urlopen(origin+'/v2'+path).read().decode()
 chunks=set(re.findall(r'(?:src|href)="([^" ]+/_next/static/[^" ]+)"',html))
 assert chunks,'No chunks in '+path
 for chunk in chunks: assert urllib.request.urlopen(origin+chunk.replace('&amp;','&')).status==200
 print(path, 'HTTP 200;',len(chunks),'assets verified')
PY
trap - ERR
printf 'DEPLOYED %s %s %s %s\n' "$environment" "$app" "$revision" "$release"
