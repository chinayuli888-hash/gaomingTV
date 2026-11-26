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
server=''
: > "$scratch/created-devices.txt"
cleanup() {
  while IFS= read -r created; do
    xcrun simctl shutdown "$created" >/dev/null 2>&1 || true
    xcrun simctl delete "$created" >/dev/null 2>&1 || true
  done < "$scratch/created-devices.txt"
  if [[ -n "$server" ]]; then kill "$server" 2>/dev/null || true; fi
}
trap cleanup EXIT

project=(-project "$ios_dir/GaomingTV.xcodeproj" -scheme GaomingTV)
xcodebuild -version
# The device build checks release code and resources without developer credentials.
xcodebuild "${project[@]}" -configuration Release -destination 'generic/platform=iOS' \
  -derivedDataPath "$scratch/device-build" CODE_SIGNING_ALLOWED=NO build > "$output/release-build_$save_date.log" 2>&1 || {
    tail -n 120 "$output/release-build_$save_date.log"; exit 1;
  }
app_plist="$scratch/device-build/Build/Products/Release-iphoneos/GaomingTV.app/Info.plist"
if /usr/libexec/PlistBuddy -c 'Print :NSAppTransportSecurity:NSAllowsLocalNetworking' "$app_plist" >/dev/null 2>&1; then
  echo "Unexpected debug networking exception in Release"; exit 1
fi

simctl_json="$output/simulator-inventory_$save_date.json"
list_simulators() {
  xcrun simctl list -j > "$simctl_json"
  xcrun simctl list devices available | tee "$output/available-devices_$save_date.txt"
  xcrun simctl list runtimes
}

# Separate runtimes from devices: clean runners may have zero named devices.
list_simulators
sdk_version=$(xcrun --sdk iphonesimulator --show-sdk-version)
plan_devices() {
  python3 - "$simctl_json" "$sdk_version" "$(uname -m)" <<'PY'
import json
from pathlib import Path
import re
import sys

data = json.loads(Path(sys.argv[1]).read_text())
sdk_major = int(sys.argv[2].split(".")[0])
arch = sys.argv[3]
types = {item["identifier"]: item for item in data["devicetypes"]}
def version(value):
    return tuple(map(int, value.split(".")))

candidates = []
for runtime in data["runtimes"]:
    if not runtime["identifier"].startswith("com.apple.CoreSimulator.SimRuntime.iOS-") or not runtime["isAvailable"]:
        continue
    v = version(runtime["version"])
    if v[0] < 16 or v[0] > sdk_major or (runtime.get("supportedArchitectures") and arch not in runtime["supportedArchitectures"]):
        continue
    candidates.append((v, runtime))
if not candidates:
    sys.exit(3)

for _, runtime in sorted(candidates, key=lambda item: item[0], reverse=True):
    v = version(runtime["version"]) + (0, 0)
    encoded = (v[0] << 16) | (v[1] << 8) | v[2]
    supported = runtime.get("supportedDeviceTypes")
    if supported:
        ids = [item["identifier"] if isinstance(item, dict) else item for item in supported]
    else:
        ids = [key for key, item in types.items()
               if int(item.get("minRuntimeVersion", 0)) <= encoded <= int(item.get("maxRuntimeVersion", 0xffffffff))]
    selected = []
    for family in ("iPhone", "iPad"):
        choices = []
        for key in ids:
            info = types.get(key, {})
            name = info.get("name", "")
            if not name.startswith(family) or (info.get("supportedArchitectures") and arch not in info["supportedArchitectures"]):
                continue
            preferred = bool(re.fullmatch(r"iPhone \d+ Pro", name) if family == "iPhone"
                             else "11-inch" in name and "Air" in name)
            choices.append((preferred, info.get("minRuntimeVersion", 0), name, key))
        if choices:
            _, _, name, key = max(choices)
            selected.append(f"{family}|{key}|{name}|{runtime['version']}|{runtime['identifier']}")
    if len(selected) == 2:
        print("\n".join(selected))
        sys.exit(0)
sys.exit("Available iOS runtime has no compatible iPhone/iPad pair. See simulator-inventory JSON.")
PY
}

plan_status=0
plan_devices > "$scratch/plan.txt" || plan_status=$?
if [[ $plan_status == 3 && ${IOS_PREVIEW_DOWNLOAD_RUNTIME:-0} == 1 ]]; then
  xcodebuild -downloadPlatform iOS 2>&1 | tee "$output/runtime-download_$save_date.log"
  list_simulators
  plan_status=0
  plan_devices > "$scratch/plan.txt" || plan_status=$?
fi
if [[ $plan_status != 0 ]]; then
  echo "No compatible simulator pair (planner exit $plan_status). See $simctl_json." >&2
  exit "$plan_status"
fi
while IFS='|' read -r family type model runtime runtime_id; do
  created=$(xcrun simctl create "GaomingTV-$family-$$" "$type" "$runtime_id")
  echo "$created" >> "$scratch/created-devices.txt"
  echo "$family|$created|$model|$runtime" >> "$scratch/devices.txt"
done < "$scratch/plan.txt"
cp "$scratch/devices.txt" "$output/simulator-destinations_$save_date.txt"

python3 -u "$ci_dir/serve_fixtures.py" > "$scratch/server.log" 2>&1 &
server=$!
for _ in {1..20}; do
  if ! kill -0 "$server" 2>/dev/null; then cat "$scratch/server.log"; exit 1; fi
  if curl -fsS http://127.0.0.1:8765/catalog.m3u >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8765/catalog.m3u | grep -q 'Test A'

completed=0
while IFS='|' read -r family device model runtime <&3; do
  echo "Testing $family: $model (iOS $runtime, $device)"
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
