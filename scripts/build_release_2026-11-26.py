"""Build the unsigned Gaoming TV 1.6.9 release from the verified 1.6.8 build."""

import argparse
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from zipfile import BadZipFile, ZipFile

from PIL import Image, ImageDraw, ImageFont

from rebuild import publish_apk, signature_entry


BASE_HASH = "f290a5b6ef1861856e8ecf9a51174b2add8b7dfa593725cf0cfdf9f0723b7869"
MANIFEST_HASH = "c5d58199dd1b577adcb23b6522da482008c1fb6c9287eff04104c1eff273fa82"
VERSION = "1.6.9"
VERSION_CODE = 16
LABEL = f"高明TV {VERSION}"
ICON = "res/drawable-nodpi-v4/ic_launcher.png"
BANNER = "res/drawable-nodpi-v4/tv_banner.png"


def version_manifest(data):
    if sha256(data).hexdigest() != MANIFEST_HASH:
        raise ValueError("Unexpected 1.6.8 manifest")
    manifest = bytearray(data)
    pool = 8
    header, size, count, _, _, strings_offset = struct.unpack_from("<H5I", data, pool + 2)
    pool_end = pool + size
    offsets = list(struct.unpack_from(f"<{count}I", data, pool + header))
    strings = bytearray(data[pool + strings_offset:pool_end])

    # The pinned manifest's versionName uses string 21, shared by the raw and typed value.
    version_offset = offsets[21] + 2
    encoded_version = VERSION.encode("utf-16le")
    strings[version_offset:version_offset + len(encoded_version)] = encoded_version
    offsets.append(len(strings))
    strings += struct.pack("<H", len(LABEL)) + LABEL.encode("utf-16le") + b"\0\0"
    strings += b"\0" * (-len(strings) % 4)

    header_data = manifest[pool:pool + header]
    new_pool = header_data + struct.pack(f"<{len(offsets)}I", *offsets) + strings
    struct.pack_into("<III", new_pool, 4, len(new_pool), len(offsets), 0)
    struct.pack_into("<I", new_pool, 20, header + 4 * len(offsets))

    # Leave all existing resource IDs in place. Turn only the application label
    # into a literal string so both launcher entries inherit the release name.
    struct.pack_into("<I", manifest, 2568, VERSION_CODE)
    struct.pack_into("<IHBBI", manifest, 3676, count, 8, 0, 3, count)
    output = manifest[:pool] + new_pool + manifest[pool_end:]
    struct.pack_into("<I", output, 4, len(output))
    return output


def draw_version(data, size, box, font_size):
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
    left, top, right, bottom = draw.textbbox((0, 0), VERSION, font=font)
    draw.text(((x1 + x2 - left - right) / 2, (y1 + y2 - top - bottom) / 2),
              VERSION, font=font, fill="#14191e")
    icon.alpha_composite(overlay.resize(size, Image.Resampling.LANCZOS))
    output = BytesIO()
    icon.convert(mode).save(output, format="PNG", optimize=True)
    return output.getvalue()


def write_unsigned_apk(source, destination):
    with ZipFile(source) as base, ZipFile(destination, "w", compresslevel=6) as output:
        replacements = {
            "AndroidManifest.xml": version_manifest(base.read("AndroidManifest.xml")),
            ICON: draw_version(base.read(ICON), (96, 96), (18, 72, 78, 90), 16),
            BANNER: draw_version(base.read(BANNER), (320, 180), (96, 119, 170, 144), 21),
        }
        output.comment = base.comment
        for entry in base.infolist():
            if not signature_entry(entry.filename):
                data = replacements.pop(entry.filename, None)
                output.writestr(entry, base.read(entry) if data is None else data)
        if replacements:
            raise ValueError("Missing release resources")


def build(base_apk, tools, output):
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
        write_unsigned_apk(base, raw)
        subprocess.run([zipalign, "-P", "16", "4", raw, aligned], check=True)
        subprocess.run([zipalign, "-c", "-P", "16", "4", aligned], check=True)
        metadata = subprocess.check_output([aapt2, "dump", "badging", aligned], encoding="utf-8")
        expected = (f"package: name='cn.gaoming.tv' versionCode='{VERSION_CODE}' versionName='{VERSION}'",
                    f"application: label='{LABEL}' icon='{ICON}' banner='{BANNER}'",
                    "minSdkVersion:'19'", "targetSdkVersion:'34'")
        if any(value not in metadata for value in expected):
            raise ValueError("Released application metadata does not match")
        publish_apk(aligned, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-apk", type=Path, required=True)
    parser.add_argument("--android-build-tools", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(f"Output already exists: {args.output}")
        build(args.base_apk, args.android_build_tools, args.output)
    except (BadZipFile, OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Build failed: {error}\n")


if __name__ == "__main__":
    main()
