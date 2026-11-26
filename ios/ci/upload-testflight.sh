#!/usr/bin/env bash
# Upload an iOS build to App Store Connect for TestFlight processing.
set +x
set -euo pipefail
umask 077

if [[ ${1:-} == --help ]]; then
  echo 'Run on macOS: APPLE_TEAM_ID=… ASC_KEY_ID=… ASC_ISSUER_ID=… ASC_KEY_PATH=/secure/team-key.p8 bash ios/ci/upload-testflight.sh'
  echo 'GAOMING_BUILD_NUMBER defaults to 1. Use a new build number for revised uploads.'
  exit 0
fi
[[ $# -eq 0 ]] || { echo 'Unexpected arguments. Run with --help.' >&2; exit 2; }
: "${APPLE_TEAM_ID:?Set the Apple Developer Team ID.}"
: "${ASC_KEY_ID:?Set the App Store Connect team key ID.}"
: "${ASC_ISSUER_ID:?Set the App Store Connect team key issuer ID.}"
: "${ASC_KEY_PATH:?Set the path to the team API private key outside the repository.}"
build=${GAOMING_BUILD_NUMBER:-1}
version=0.1.0
bundle=cn.gaoming.tv.ios
[[ $APPLE_TEAM_ID =~ ^[A-Z0-9]{10}$ && $build =~ ^[1-9][0-9]*$ ]] || {
  echo 'Expected a ten-character Team ID and a positive integer build number.' >&2; exit 2;
}
[[ -f "$ASC_KEY_PATH" && -r "$ASC_KEY_PATH" ]] || { echo 'The API key file is not readable.' >&2; exit 2; }
[[ $(uname -s) == Darwin ]] || { echo 'A macOS host with Xcode is required.' >&2; exit 2; }
root="$(cd "$(dirname "$0")/../.." && pwd -P)"
xcode_major=$(xcodebuild -version | awk '/^Xcode / {split($2,v,"."); print v[1]}')
sdk=$(xcrun --sdk iphoneos --show-sdk-version)
[[ $xcode_major -ge 26 && ${sdk%%.*} -ge 26 ]] || {
  echo 'Select Xcode 26 or later with the iOS 26 SDK or later.' >&2; exit 2;
}

# Look up the existing app with a short-lived ES256 token; the key and token stay off stdout.
ruby - "$root" "$bundle" <<'RUBY'
require "base64"
require "json"
require "net/http"
require "openssl"
require "uri"

root, bundle = ARGV
key_path = File.realpath(ENV.fetch("ASC_KEY_PATH"))
abort "Place the API private key outside the project." if key_path.start_with?(root + "/")
encode = ->(s) { Base64.urlsafe_encode64(s, padding: false) }
now = Time.now.to_i
header = {alg: "ES256", kid: ENV.fetch("ASC_KEY_ID"), typ: "JWT"}
claims = {iss: ENV.fetch("ASC_ISSUER_ID"), iat: now, exp: now + 300, aud: "appstoreconnect-v1"}
payload = [header, claims].map { |part| encode.call(JSON.generate(part)) }.join(".")
key = OpenSSL::PKey.read(File.binread(key_path))
signature = OpenSSL::ASN1.decode(key.sign("SHA256", payload)).value.map do |number|
  number.value.to_s(2).rjust(32, "\x00".b)
end.join
uri = URI("https://api.appstoreconnect.apple.com/v1/apps")
uri.query = URI.encode_www_form("filter[bundleId]" => bundle, "fields[apps]" => "bundleId")
request = Net::HTTP::Get.new(uri)
request["Authorization"] = "Bearer #{payload}.#{encode.call(signature)}"
response = Net::HTTP.start(uri.host, uri.port, use_ssl: true, open_timeout: 15, read_timeout: 25) { |http| http.request(request) }
abort "App Store Connect app lookup failed (HTTP #{response.code}). Check the team key and its access." unless response.is_a?(Net::HTTPSuccess)
records = JSON.parse(response.body).fetch("data")
abort "Create an iOS App Store Connect record for #{bundle}, or grant access to the existing record." unless records.any? { |app| app.dig("attributes", "bundleId") == bundle }
RUBY

base="$root/build/testflight"
mkdir -p "$base"
work=$(mktemp -d "$base/run-XXXXXX")
archive="$work/GaomingTV_${version}_$(date +%F).xcarchive"
echo "Archiving $bundle $version ($build) to $archive"
auth=(-allowProvisioningUpdates -authenticationKeyPath "$ASC_KEY_PATH"
      -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID")
xcodebuild -project "$root/ios/GaomingTV.xcodeproj" -scheme GaomingTV -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$archive" "${auth[@]}" \
  DEVELOPMENT_TEAM="$APPLE_TEAM_ID" CURRENT_PROJECT_VERSION="$build" archive

app="$archive/Products/Applications/GaomingTV.app"
plist="$app/Info.plist"
property() { /usr/libexec/PlistBuddy -c "Print :$1" "$plist"; }
[[ $(property CFBundleIdentifier) == "$bundle" && $(property CFBundleShortVersionString) == "$version" &&
   $(property CFBundleVersion) == "$build" ]] || { echo 'Archived app identity/version mismatch.' >&2; exit 1; }
codesign --verify --strict "$app"
codesign --display --verbose=4 "$app" 2>&1 | grep -Fx "TeamIdentifier=$APPLE_TEAM_ID" >/dev/null || {
  echo 'Archived app signing team differs from APPLE_TEAM_ID.' >&2; exit 1;
}

options="$work/ExportOptions.plist"
cat > "$options" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>upload</string>
  <key>teamID</key><string>$APPLE_TEAM_ID</string>
  <key>signingStyle</key><string>automatic</string>
  <key>manageAppVersionAndBuildNumber</key><false/>
</dict></plist>
PLIST
plutil -lint "$options"
xcodebuild -exportArchive -archivePath "$archive" -exportOptionsPlist "$options" \
  -exportPath "$work/export" "${auth[@]}"
echo "Upload completed for $bundle $version ($build). Check processing and tester availability in App Store Connect."
