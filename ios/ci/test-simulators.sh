#!/usr/bin/env bash
# Run on a Mac with Xcode 16+ and iPhone/iPad simulator runtimes installed.
set -euo pipefail

ci_dir="$(cd "$(dirname "$0")" && pwd)"
ios_dir="$(dirname "$ci_dir")"
save_date="$(date +%F)"
output="${1:-$ios_dir/../build/ios-simulator-$save_date}"
mkdir -p "$output"
output="$(cd "$output" && pwd)"
scratch="$(mktemp -d)"
device=''
server=''
cleanup() {
  if [[ -n "$device" ]]; then xcrun simctl shutdown "$device" >/dev/null 2>&1 || true; fi
  if [[ -n "$server" ]]; then kill "$server" 2>/dev/null || true; fi
}
trap cleanup EXIT

project=(-project "$ios_dir/GaomingTV.xcodeproj" -scheme GaomingTV)
xcodebuild -version
xcodebuild "${project[@]}" -showdestinations > "$scratch/destinations.txt"
python3 - "$scratch/destinations.txt" > "$scratch/devices.txt" <<'PY'
from pathlib import Path
import re
import sys

text = Path(sys.argv[1]).read_text()
eligible = text.split("Ineligible destinations")[0]
for family in ("iPhone", "iPad"):
    matches = []
    for record in re.findall(r"\{([^}]+)\}", eligible):
        fields = dict(field.strip().split(":", 1) for field in record.split(",") if ":" in field)
        name, uid = fields.get("name", ""), fields.get("id", "")
        if fields.get("platform") == "iOS Simulator" and name.startswith(family) and re.fullmatch(r"[a-fA-F\d-]{36}", uid):
            version = tuple(int(v) for v in re.findall(r"\d+", fields.get("OS", "")))
            preferred = bool(re.fullmatch(r"iPhone \d+ Pro", name) if family == "iPhone"
                             else "11-inch" in name and "Air" in name)
            matches.append((version, preferred, name, uid))
    if not matches:
        raise SystemExit(f"No eligible {family} simulator\n{text}")
    version, _, name, uid = max(matches)
    print(f"{family}|{uid}|{name}|{'.'.join(map(str, version))}")
PY
cp "$scratch/devices.txt" "$output/simulator-destinations_$save_date.txt"

python3 -u "$ci_dir/serve_fixtures.py" > "$scratch/server.log" 2>&1 &
server=$!
for _ in {1..20}; do
  if ! kill -0 "$server" 2>/dev/null; then cat "$scratch/server.log"; exit 1; fi
  if curl -fsS http://127.0.0.1:8765/catalog.m3u >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8765/catalog.m3u | grep -q 'Test A'

# The device build checks release code and resources without developer credentials.
xcodebuild "${project[@]}" -configuration Release -destination 'generic/platform=iOS' \
  -derivedDataPath "$scratch/device-build" CODE_SIGNING_ALLOWED=NO build > "$output/release-build_$save_date.log" 2>&1 || {
    tail -n 120 "$output/release-build_$save_date.log"; exit 1;
  }
app_plist="$scratch/device-build/Build/Products/Release-iphoneos/GaomingTV.app/Info.plist"
if /usr/libexec/PlistBuddy -c 'Print :NSAppTransportSecurity:NSAllowsLocalNetworking' "$app_plist" >/dev/null 2>&1; then
  echo "Unexpected debug networking exception in Release"; exit 1
fi

completed=0
while IFS='|' read -r family device model runtime <&3; do
  echo "Testing $family: $model (iOS $runtime, $device)"
  xcrun simctl boot "$device" || xcrun simctl bootstatus "$device" -b
  xcrun simctl bootstatus "$device" -b
  result="$output/${family}_$save_date.xcresult"
  start=$(wc -l < "$scratch/server.log")
  xcodebuild "${project[@]}" -configuration Debug -destination "platform=iOS Simulator,id=$device" \
    -derivedDataPath "$scratch/simulator-build" -parallel-testing-enabled NO \
    -resultBundlePath "$result" test | tee "$output/${family}_$save_date.log"
  # Verify each model really fetched the failed route and both distinct media fragments.
  tail -n "+$((start + 1))" "$scratch/server.log" > "$output/${family}_HLS_$save_date.log"
  for pattern in 'missing.m3u8.* 404 ' 'A/video-0.m4s.* 20[06] ' 'B/video-0.m4s.* 20[06] '; do
    if ! grep -Eq "$pattern" "$output/${family}_HLS_$save_date.log"; then
      echo "Missing expected HTTP request: $pattern"; cat "$output/${family}_HLS_$save_date.log"; exit 1
    fi
  done
  attachments="$output/${family}_screenshots_$save_date"
  xcrun xcresulttool export attachments --path "$result" --output-path "$attachments"
  python3 - "$attachments" <<'PY'
from pathlib import Path
import sys

folder = Path(sys.argv[1])
png = b"\x89PNG\r\n\x1a\n"
screenshots = [p for p in folder.rglob("*") if p.is_file() and p.read_bytes()[:8] == png]
if len(screenshots) < 4:
    raise SystemExit(f"Expected at least four PNG attachments, found {len(screenshots)}")
PY
  xcrun simctl shutdown "$device"
  device=''
  completed=$((completed + 1))
done 3< "$scratch/devices.txt"
[[ $completed -eq 2 ]]
