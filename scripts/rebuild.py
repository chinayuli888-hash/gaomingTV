#!/usr/bin/env python3
"""Rebuild Gaoming TV 1.6.2 from the supplied 1.6.0 APK."""

import argparse
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import BadZipFile, ZipFile


BASE_SHA256 = "49b015bb950cf540a31d7b94dfeaa047d66f2b09b10400e1c853d35a50d1e87e"
MANIFEST_SHA256 = "28fb7addb27c5d2fb640b1c5678eda8a06df2274c5c2be2902f719efe6b45dcc"
BASE_NAME = "1.6.0"
BASE_CODE = 7
RELEASE_NAME = "1.6.2"
RELEASE_CODE = 9
# These byte ranges apply to the pinned binary Android manifest.
MANIFEST_NAME = slice(850, 860)
MANIFEST_CODE = slice(2232, 2236)
OLD_SIGNATURE_ENTRIES = {
    "META-INF/MANIFEST.MF",
    "META-INF/GAOMING-.RSA",
    "META-INF/GAOMING-.SF",
}
PATCH = Path(__file__).resolve().parents[1] / "patches" / "1.6.2.patch"


def parse_args(parser):
    parser.add_argument("--base-apk", type=Path, required=True,
                        help="Original Gaoming TV 1.6.0 APK with the pinned release hash")
    parser.add_argument("--apktool-jar", type=Path, required=True,
                        help="Apktool 3.0.3 JAR (requires Java on PATH)")
    parser.add_argument("--android-build-tools", type=Path, required=True,
                        help="Android SDK build-tools 36.0.0 directory on Linux or macOS")
    parser.add_argument("--output", type=Path, required=True,
                        help="New APK output path (aligned unsigned APK by default)")
    parser.add_argument("--keystore", type=Path,
                        help="Optional private keystore for signing the APK")
    parser.add_argument("--key-alias", help="Signing key alias in the keystore")
    parser.add_argument("--keystore-password-file", type=Path,
                        help="File containing the keystore password on its first line")
    parser.add_argument("--key-password-file", type=Path,
                        help="Separate key password file, if the key uses a different password")

    args = parser.parse_args()
    if args.keystore:
        if not args.key_alias or not args.keystore_password_file:
            parser.error("--keystore requires --key-alias and --keystore-password-file")
    elif args.key_alias or args.keystore_password_file or args.key_password_file:
        parser.error("signing options require --keystore")

    for option, value in vars(args).items():
        if isinstance(value, Path):
            expanded = value.expanduser()
            setattr(args, option, expanded.absolute() if option == "output" else expanded.resolve())
    return args


def package_apk(base_apk, classes_dex, destination):
    base_name = BASE_NAME.encode("utf-16-le")
    release_name = RELEASE_NAME.encode("utf-16-le")
    if len(release_name) != len(base_name):
        raise ValueError("Release name must occupy the same UTF-16LE bytes as the base name")

    with ZipFile(base_apk) as base, ZipFile(destination, "w", compresslevel=6) as output:
        manifest = bytearray(base.read("AndroidManifest.xml"))
        if (sha256(manifest).hexdigest() != MANIFEST_SHA256
                or manifest[MANIFEST_NAME] != base_name
                or int.from_bytes(manifest[MANIFEST_CODE], "little") != BASE_CODE):
            raise ValueError(f"Unexpected {BASE_NAME} manifest version fields")

        manifest[MANIFEST_NAME] = release_name
        manifest[MANIFEST_CODE] = RELEASE_CODE.to_bytes(4, "little")
        replacements = {"AndroidManifest.xml": manifest, "classes.dex": classes_dex.read_bytes()}

        output.comment = base.comment
        for entry in base.infolist():
            if entry.filename in OLD_SIGNATURE_ENTRIES:
                continue
            data = replacements.get(entry.filename)
            if data is None:
                data = base.read(entry)
            output.writestr(entry, data)


def publish_apk(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        staged_apk = Path(staging) / "built.apk"
        shutil.copyfile(source, staged_apk)
        # Publishing only the completed copy protects against partial output and clobbering.
        os.link(staged_apk, destination)


def rebuild(args, work, base_apk):
    decoded = work / "decoded"
    framework = work / "framework"
    apktool = ["java", "-jar", args.apktool_jar]
    subprocess.run([*apktool, "d", "-r", "--no-assets", "-p", framework, "-o", decoded,
                    base_apk], check=True)

    git_env = os.environ.copy()
    for variable in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        git_env.pop(variable, None)
    git_env["GIT_CEILING_DIRECTORIES"] = str(work)
    subprocess.run(["git", "apply", "--whitespace=nowarn", "-p1", PATCH],
                   cwd=decoded, env=git_env, check=True)

    subprocess.run([*apktool, "b", "--no-apk", "-p", framework, decoded], check=True)
    unsigned = work / "unsigned.apk"
    package_apk(base_apk, decoded / "build" / "apk" / "classes.dex", unsigned)

    zipalign = args.android_build_tools / "zipalign"
    apksigner = args.android_build_tools / "apksigner"
    aligned = work / "aligned.apk"
    subprocess.run([zipalign, "-P", "16", "4", unsigned, aligned], check=True)

    result = aligned
    if args.keystore:
        result = work / "signed.apk"
        sign = [apksigner, "sign", "--ks", args.keystore, "--ks-key-alias", args.key_alias,
                "--ks-pass", f"file:{args.keystore_password_file}",
                "--v1-signing-enabled", "true", "--v2-signing-enabled", "true",
                "--v3-signing-enabled", "true", "--v4-signing-enabled", "false"]
        if args.key_password_file:
            sign.extend(["--key-pass", f"file:{args.key_password_file}"])
        subprocess.run([*sign, "--out", result, aligned], check=True)
        subprocess.run([apksigner, "verify", "--verbose", result], check=True)

    subprocess.run([zipalign, "-c", "-P", "16", "4", result], check=True)
    publish_apk(result, args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    args = parse_args(parser)
    try:
        base_bytes = args.base_apk.read_bytes()
        if sha256(base_bytes).hexdigest() != BASE_SHA256:
            raise ValueError(f"Base APK does not match expected SHA-256 {BASE_SHA256}")
        if args.output.exists():
            raise FileExistsError(f"Output already exists: {args.output}")
        with tempfile.TemporaryDirectory(prefix="gaoming-tv-build-") as work:
            work_path = Path(work).resolve()
            base_apk = work_path / "base.apk"
            base_apk.write_bytes(base_bytes)
            rebuild(args, work_path, base_apk)
    except (OSError, ValueError, OverflowError, BadZipFile, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Build failed: {error}\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
