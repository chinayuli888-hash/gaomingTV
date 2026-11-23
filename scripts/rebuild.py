#!/usr/bin/env python3
"""Rebuild Gaoming TV from a supported, unmodified base APK."""

import argparse
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parents[1]
# The two pinned manifests store the version at the same offsets.
MANIFEST_NAME = slice(850, 860)
MANIFEST_CODE = slice(2232, 2236)


@dataclass(frozen=True)
class Release:
    base_name: str
    base_code: int
    manifest_sha256: str
    name: str
    code: int
    patch: str
    channel_policy: bool = False


RELEASES = {
    "49b015bb950cf540a31d7b94dfeaa047d66f2b09b10400e1c853d35a50d1e87e": Release(
        "1.6.0", 7, "28fb7addb27c5d2fb640b1c5678eda8a06df2274c5c2be2902f719efe6b45dcc",
        "1.6.2", 9, "1.6.2.patch",
    ),
    "8ff5e011e06cba4430fe4c6731262896a8fb1727b6ebac59d5932d9fced4c47f": Release(
        "1.6.1", 8, "990665d8920f969dad0a6fc40be742ed347f217fe5b23cd49aec3402864fa27e",
        "1.6.3", 10, "1.6.3-from-1.6.1.patch", channel_policy=True,
    ),
}


def parse_args(parser):
    parser.add_argument("--base-apk", type=Path, required=True,
                        help="Original Gaoming TV 1.6.0 or 1.6.1 APK with a supported hash")
    parser.add_argument("--apktool-jar", type=Path, required=True,
                        help="Apktool 3.0.3 JAR (requires Java on PATH)")
    parser.add_argument("--android-build-tools", type=Path, required=True,
                        help="Android SDK build-tools 36.0.0 directory on Linux or macOS")
    parser.add_argument("--android-platform-jar", type=Path,
                        help="Android 35 android.jar for 1.6.3 (defaults to the same SDK)")
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


def signature_entry(name):
    directory, _, filename = name.rpartition("/")
    filename = filename.upper()
    return directory == "META-INF" and (
        filename == "MANIFEST.MF" or filename.startswith("SIG-")
        or filename.endswith((".SF", ".RSA", ".DSA", ".EC"))
    )


def package_apk(base_apk, classes_dex, destination, release):
    base_name = release.base_name.encode("utf-16-le")
    release_name = release.name.encode("utf-16-le")
    if len(release_name) != len(base_name):
        raise ValueError("Release name must occupy the same UTF-16LE bytes as the base name")

    with ZipFile(base_apk) as base, ZipFile(destination, "w", compresslevel=6) as output:
        manifest = bytearray(base.read("AndroidManifest.xml"))
        if (sha256(manifest).hexdigest() != release.manifest_sha256
                or manifest[MANIFEST_NAME] != base_name
                or int.from_bytes(manifest[MANIFEST_CODE], "little") != release.base_code):
            raise ValueError(f"Unexpected {release.base_name} manifest version fields")

        manifest[MANIFEST_NAME] = release_name
        manifest[MANIFEST_CODE] = release.code.to_bytes(4, "little")
        replacements = {"AndroidManifest.xml": manifest, "classes.dex": classes_dex.read_bytes()}

        output.comment = base.comment
        for entry in base.infolist():
            if signature_entry(entry.filename):
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


def assemble_channel_policy(args, work, base_apk, decoded, framework, apktool):
    platform = args.android_platform_jar
    if platform is None:
        platform = args.android_build_tools.parent.parent / "platforms/android-35/android.jar"
    if not platform.is_file():
        raise FileNotFoundError(f"Set --android-platform-jar to Android 35 android.jar ({platform})")

    sources = sorted((ROOT / "channel-policy").rglob("*.java"))
    classes = work / "channel-policy-classes"
    classes.mkdir()
    subprocess.run(["java", "-m", "jdk.compiler/com.sun.tools.javac.Main",
                    "-source", "8", "-target", "8", "-Xlint:-options", "-encoding", "UTF-8",
                    "-classpath", platform, "-d", classes, *sources], check=True)

    package = Path("cn/gaoming/tv")
    helpers = sorted((classes / package).glob("ChannelPolicy*.class"))
    helper_dex = work / "channel-policy-dex"
    helper_dex.mkdir()
    subprocess.run([args.android_build_tools / "d8", "--min-api", "19", "--lib", platform,
                    "--classpath", classes, "--output", helper_dex, *helpers], check=True)

    # Give Apktool the base manifest so it can disassemble just the helper DEX.
    helper_apk = work / "channel-policy.apk"
    with ZipFile(base_apk) as base, ZipFile(helper_apk, "w") as out:
        out.writestr("AndroidManifest.xml", base.read("AndroidManifest.xml"))
        out.writestr("resources.arsc", base.read("resources.arsc"))
        out.write(helper_dex / "classes.dex", "classes.dex")
    helper_smali = work / "channel-policy-smali"
    subprocess.run([*apktool, "d", "-r", "--no-assets", "-p", framework, "-o", helper_smali,
                    helper_apk], check=True)
    smali_files = list((helper_smali / "smali").rglob("*.smali"))
    if not smali_files or any(
        path.parent != helper_smali / "smali" / package or not path.stem.startswith("ChannelPolicy")
        for path in smali_files
    ):
        raise ValueError("Unexpected classes in the channel policy DEX")
    for path in smali_files:
        shutil.copyfile(path, decoded / "smali" / package / path.name)


def rebuild(args, work, base_apk, release):
    decoded = work / "decoded"
    framework = work / "framework"
    apktool = ["java", "-jar", args.apktool_jar]
    subprocess.run([*apktool, "d", "-r", "--no-assets", "-p", framework, "-o", decoded,
                    base_apk], check=True)

    git_env = os.environ.copy()
    for variable in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        git_env.pop(variable, None)
    git_env["GIT_CEILING_DIRECTORIES"] = str(work)
    patch = ROOT / "patches" / release.patch
    subprocess.run(["git", "apply", "--whitespace=nowarn", "-p1", patch],
                   cwd=decoded, env=git_env, check=True)
    if release.channel_policy:
        assemble_channel_policy(args, work, base_apk, decoded, framework, apktool)

    subprocess.run([*apktool, "b", "--no-apk", "-p", framework, decoded], check=True)
    unsigned = work / "unsigned.apk"
    package_apk(base_apk, decoded / "build" / "apk" / "classes.dex", unsigned, release)

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
        release = RELEASES.get(sha256(base_bytes).hexdigest())
        if release is None:
            supported = ", ".join(f"{release.base_name} ({digest})" for digest, release in RELEASES.items())
            raise ValueError(f"Base APK does not match a supported SHA-256: {supported}")
        if args.output.exists():
            raise FileExistsError(f"Output already exists: {args.output}")
        with tempfile.TemporaryDirectory(prefix="gaoming-tv-build-") as work:
            work_path = Path(work).resolve()
            base_apk = work_path / "base.apk"
            base_apk.write_bytes(base_bytes)
            rebuild(args, work_path, base_apk, release)
    except (OSError, ValueError, OverflowError, BadZipFile, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Build failed: {error}\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
