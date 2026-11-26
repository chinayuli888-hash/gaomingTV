"""Build an unsigned Gaoming TV release from the verified 1.6.8 build."""

import argparse
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from zipfile import BadZipFile, ZipFile

from PIL import Image, ImageDraw, ImageFont

from rebuild import compile_helper_smali, publish_apk, signature_entry


BASE_HASH = "f290a5b6ef1861856e8ecf9a51174b2add8b7dfa593725cf0cfdf9f0723b7869"
MANIFEST_HASH = "c5d58199dd1b577adcb23b6522da482008c1fb6c9287eff04104c1eff273fa82"
VERSION_CODES = {"1.6.9": 16, "1.6.10": 17}
APKTOOL_HASH = "dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423"
ICON = "res/drawable-nodpi-v4/ic_launcher.png"
BANNER = "res/drawable-nodpi-v4/tv_banner.png"


def version_manifest(data, version):
    if sha256(data).hexdigest() != MANIFEST_HASH:
        raise ValueError("Unexpected 1.6.8 manifest")
    manifest = bytearray(data)
    pool = 8
    header, size, count, _, _, strings_offset = struct.unpack_from("<H5I", data, pool + 2)
    pool_end = pool + size
    offsets = list(struct.unpack_from(f"<{count}I", data, pool + header))
    strings = bytearray(data[pool + strings_offset:pool_end])

    # The pinned manifest's versionName uses string 21, shared by the raw and typed value.
    version_offset = offsets[21]
    old_length = struct.unpack_from("<H", strings, version_offset)[0]
    old_end = version_offset + 2 + old_length * 2
    encoded = version.encode("utf-16le")
    strings[version_offset:old_end] = struct.pack("<H", len(encoded) // 2) + encoded
    delta = len(encoded) - old_length * 2
    offsets = [offset + delta if offset > version_offset else offset for offset in offsets]
    offsets.append(len(strings))
    label = f"高明TV {version}"
    strings += struct.pack("<H", len(label)) + label.encode("utf-16le") + b"\0\0"
    strings += b"\0" * (-len(strings) % 4)

    header_data = manifest[pool:pool + header]
    new_pool = header_data + struct.pack(f"<{len(offsets)}I", *offsets) + strings
    struct.pack_into("<III", new_pool, 4, len(new_pool), len(offsets), 0)
    struct.pack_into("<I", new_pool, 20, header + 4 * len(offsets))

    # Leave all existing resource IDs in place. Turn only the application label
    # into a literal string so both launcher entries inherit the release name.
    struct.pack_into("<I", manifest, 2568, VERSION_CODES[version])
    struct.pack_into("<IHBBI", manifest, 3676, count, 8, 0, 3, count)
    output = manifest[:pool] + new_pool + manifest[pool_end:]
    struct.pack_into("<I", output, 4, len(output))
    return output


def draw_version(data, size, box, font_size, version):
    with Image.open(BytesIO(data)) as original:
        if original.size != size or original.format != "PNG":
            raise ValueError("Unexpected launcher image")
        icon = original.convert("RGBA")
        mode = original.mode

    scale = 3
    overlay = Image.new("RGBA", (size[0] * scale, size[1] * scale))
    draw = ImageDraw.Draw(overlay)
    x1, y1, x2, y2 = [value * scale for value in box]
    draw.rounded_rectangle((x1, y1, x2, y2), radius=6 * scale, fill="#ffcb67")
    font = ImageFont.load_default(size=font_size * scale)
    left, top, right, bottom = draw.textbbox((0, 0), version, font=font)
    draw.text(((x1 + x2 - left - right) / 2, (y1 + y2 - top - bottom) / 2),
              version, font=font, fill="#14191e")
    icon.alpha_composite(overlay.resize(size, Image.Resampling.LANCZOS))
    output = BytesIO()
    icon.convert(mode).save(output, format="PNG", optimize=True)
    return output.getvalue()


def write_unsigned_apk(source, destination, version, dex):
    with ZipFile(source) as base, ZipFile(destination, "w", compresslevel=6) as output:
        replacements = {
            "AndroidManifest.xml": version_manifest(base.read("AndroidManifest.xml"), version),
            ICON: draw_version(base.read(ICON), (96, 96), (18, 72, 78, 90), 16, version),
            BANNER: draw_version(base.read(BANNER), (320, 180), (96, 119, 170, 144), 21, version),
        }
        if dex is not None:
            replacements["classes.dex"] = dex.read_bytes()
        output.comment = base.comment
        for entry in base.infolist():
            if not signature_entry(entry.filename):
                data = replacements.pop(entry.filename, None)
                output.writestr(entry, base.read(entry) if data is None else data)
        if replacements:
            raise ValueError("Missing release resources")


def updated_dex(args, work, base):
    if sha256(args.apktool_jar.read_bytes()).hexdigest() != APKTOOL_HASH:
        raise ValueError("Expected the official Apktool 3.0.3 JAR")
    if os.name == "nt" and shutil.which("fsutil.exe"):
        subprocess.run(["fsutil.exe", "file", "SetCaseSensitiveInfo", work, "enable"], capture_output=True)
    apktool = (args.java, "-jar", args.apktool_jar)
    framework = work / "framework"
    decoded = work / "decoded"
    subprocess.run([*apktool, "d", "-r", "--no-assets", "-p", framework, "-o", decoded, base], check=True)
    files = compile_helper_smali(work, base, args.android_platform_jar, args.android_build_tools,
                                 framework, apktool, ("GitHubUpdate",))
    # D8 synthesizes listener classes. Replace the complete updater family so the old
    # browser listener cannot survive or be mistaken for a newly numbered lambda.
    package = decoded / "smali/cn/gaoming/tv"
    for old in package.glob("GitHubUpdate*.smali"):
        old.unlink()
    for path in files:
        shutil.copyfile(path, package / path.name)
    subprocess.run([*apktool, "b", "--no-apk", "-p", framework, decoded], check=True)
    return decoded / "build/apk/classes.dex"


def build(args):
    base_apk, tools, output, version = args.base_apk, args.android_build_tools, args.output, args.version
    suffix = ".exe" if os.name == "nt" else ""
    zipalign = tools / f"zipalign{suffix}"
    aapt2 = tools / f"aapt2{suffix}"
    with tempfile.TemporaryDirectory(prefix="gaoming-release-") as temp:
        work = Path(temp)
        base = work / "base.apk"
        data = base_apk.read_bytes()
        if sha256(data).hexdigest() != BASE_HASH:
            raise ValueError("Use the verified 1.6.8 unsigned build from the 1.6.7 rebuild script")
        base.write_bytes(data)
        raw = work / "unsigned.apk"
        aligned = work / "aligned.apk"
        dex = updated_dex(args, work, base) if version == "1.6.10" else None
        write_unsigned_apk(base, raw, version, dex)
        subprocess.run([zipalign, "-P", "16", "4", raw, aligned], check=True)
        subprocess.run([zipalign, "-c", "-P", "16", "4", aligned], check=True)
        metadata = subprocess.check_output([aapt2, "dump", "badging", aligned], encoding="utf-8")
        expected = (f"package: name='cn.gaoming.tv' versionCode='{VERSION_CODES[version]}' versionName='{version}'",
                    f"application: label='高明TV {version}' icon='{ICON}' banner='{BANNER}'",
                    "minSdkVersion:'19'", "targetSdkVersion:'34'")
        if any(value not in metadata for value in expected):
            raise ValueError("Released application metadata does not match")
        publish_apk(aligned, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-apk", type=Path, required=True)
    parser.add_argument("--android-build-tools", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", choices=VERSION_CODES, default="1.6.9")
    parser.add_argument("--apktool-jar", type=Path, help="Official Apktool 3.0.3 JAR for 1.6.10")
    parser.add_argument("--android-platform-jar", type=Path, help="Android API 35 android.jar for 1.6.10")
    parser.add_argument("--java", default="java", help="JDK java executable")
    args = parser.parse_args()
    if args.version == "1.6.10" and (args.apktool_jar is None or args.android_platform_jar is None):
        parser.error("1.6.10 requires --apktool-jar and --android-platform-jar")
    try:
        if args.output.exists():
            raise FileExistsError(f"Output already exists: {args.output}")
        build(args)
    except (BadZipFile, OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Build failed: {error}\n")


if __name__ == "__main__":
    main()
