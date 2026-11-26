"""Build an unsigned 1.6.8 verification candidate from the exact 1.6.7 test APK."""
import argparse
import difflib
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import subprocess
import tempfile
from zipfile import ZipFile


BASE_SHA = "215b7a5d3d8d1188524d35fc547ee41fe4260fff4ffdfb4a95ba873a2aa2c605"
APKTOOL_SHA = "dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423"
MANIFEST_SHA = "11685a0269de4e374a7366b7d301aacdfe653da46edcd6c96e9b22c01f52d4ef"
SIGNATURE_ENTRY = re.compile(r"^META-INF/(MANIFEST\.MF|SIG-[^/]+|[^/]+\.(SF|RSA|DSA|EC))$", re.I)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(*args, capture=False):
    return subprocess.run([str(x) for x in args], check=True, capture_output=capture)


def make_manifest(data):
    # These binary offsets are valid only for the exact manifest pinned above.
    if sha(data) != MANIFEST_SHA:
        raise ValueError("Unexpected base manifest SHA-256")
    xml = bytearray(data)
    xml[862:872] = "1.6.8".encode("utf-16le")
    struct.pack_into("<I", xml, 2520, 15)

    # Append two strings to the UTF-16 pool. Existing string IDs and the resource map
    # stay intact, including all local icon, banner, theme and label references.
    pool_offset = 8
    header_size = 28
    strings_offset = 236
    old_end = pool_offset + struct.unpack_from("<I", xml, pool_offset + 4)[0]
    strings = xml[pool_offset + strings_offset:old_end]
    indexes = list(struct.unpack_from("<52I", xml, pool_offset + header_size))
    for name in ("queries", "com.tv.qx"):
        indexes.append(len(strings))
        strings.extend(struct.pack("<H", len(name)) + name.encode("utf-16le") + b"\x00\x00")
    strings.extend(b"\x00" * (-len(strings) % 4))
    header = bytearray(xml[pool_offset:pool_offset + header_size])
    pool = header + struct.pack("<54I", *indexes) + strings
    struct.pack_into("<I", pool, 4, len(pool))
    struct.pack_into("<I", pool, 8, len(indexes))
    struct.pack_into("<I", pool, 20, header_size + 4 * len(indexes))

    body = xml[old_end:]
    offset = 0
    while offset < len(body):
        kind, _, size = struct.unpack_from("<HHI", body, offset)
        if kind == 0x0102 and struct.unpack_from("<I", body, offset + 20)[0] == 38:
            break  # <application>
        offset += size
    if offset >= len(body):
        raise ValueError("Missing application element")
    line = struct.unpack_from("<I", body, offset + 8)[0]
    no_index = 0xFFFFFFFF

    def node(kind, contents):
        return struct.pack("<HHIII", kind, 16, len(contents) + 16, line, no_index) + contents

    def start(name, attrs=b""):
        contents = struct.pack("<IIHHHHHH", no_index, name, 20, 20, len(attrs) // 20, 0, 0, 0)
        return node(0x0102, contents + attrs)

    def end(name):
        return node(0x0103, struct.pack("<II", no_index, name))

    # Namespace / attribute / typed string indices for android:name="com.tv.qx".
    attr = struct.pack("<IIIHBBI", 42, 3, no_index, 8, 0, 3, 53)
    queries = start(52) + start(45, attr) + end(45) + end(52)
    result = bytearray(xml[:8]) + pool + body[:offset] + queries + body[offset:]
    struct.pack_into("<I", result, 4, len(result))
    return result


def apply_terminal_hook(decoded, source_root):
    # Apktool uses a .1 suffix for case-colliding Smali paths on a case-insensitive FS.
    model = re.compile(r"^\.class [^\n]* Lo0/N;$", re.M)
    targets = [p for p in (decoded / "smali/o0").glob("*.smali")
               if model.search(p.read_text(encoding="utf-8")[:200])]
    if len(targets) != 1:
        raise ValueError("Expected exactly one Lo0/N; class")
    target = targets[0]
    text = target.read_text(encoding="utf-8")
    anchor = "    invoke-virtual {v1, p1, v3, v2}, Lcn/gaoming/tv/MainActivity;->l(Ljava/lang/String;ZZ)V\n"
    remainder = "\n    :cond_5\n    :goto_0\n    return-void"
    if text.count(anchor + remainder) != 1:
        raise ValueError("Unexpected terminal 1.6.7 playback error handler")
    patch = (source_root / "patches/1.6.8-cctv13.patch").read_text(encoding="utf-8")
    # These are the historical patch's added instructions. The bytecode assembler
    # renumbered its exit label in the released 1.6.7 DEX (:cond_4 -> :cond_5).
    if sha(patch.encode("utf-8")) != "a9b97d98c1d00fdbb2fb27e3b576f4c85b41dd973f57f38ba493d99b8805eba5":
        raise ValueError("Unexpected historical CCTV-13 hook patch")
    additions = [line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")]
    hook = "\n" + "\n".join(additions)
    target.write_text(text.replace(anchor + remainder, anchor + hook + remainder), encoding="utf-8")


def add_fallback_class(args, work, decoded, framework, apktool):
    java = args.java
    platform = args.android_platform_jar
    sdk = args.android_build_tools
    classes = work / "classes"
    classes.mkdir()
    stub_package = args.source_root / "channel-policy/stubs/o0"
    helper = args.source_root / "channel-policy/src/cn/gaoming/tv/Cctv13Fallback.java"
    run(java, "-m", "jdk.compiler/com.sun.tools.javac.Main", "-source", "8", "-target", "8",
        "-Xlint:-options", "-encoding", "UTF-8", "-classpath", platform, "-d", classes,
        stub_package / "a.java", stub_package / "c.java", helper)
    dex = work / "helper-dex"
    dex.mkdir()
    helper_classes = sorted((classes / "cn/gaoming/tv").glob("Cctv13Fallback*.class"))
    run(java, "-cp", sdk / "lib/d8.jar", "com.android.tools.r8.D8", "--min-api", "19", "--lib",
        platform, "--classpath", classes, "--output", dex, *helper_classes)
    helper_apk = work / "helper.apk"
    with ZipFile(args.base_apk) as base, ZipFile(helper_apk, "w") as out:
        for entry in ("AndroidManifest.xml", "resources.arsc"):
            out.writestr(entry, base.read(entry))
        out.write(dex / "classes.dex", "classes.dex")
    helper_smali = work / "helper-smali"
    run(*apktool, "d", "-r", "--no-assets", "-p", framework, "-o", helper_smali, helper_apk)
    new_classes = list((helper_smali / "smali").rglob("*.smali"))
    expected = {"Cctv13Fallback.smali"} | {
        "Cctv13Fallback$$ExternalSyntheticLambda%d.smali" % i for i in range(3)
    }
    if {p.name for p in new_classes} != expected:
        raise ValueError("Unexpected CCTV fallback classes from D8")
    for path in new_classes:
        shutil.copyfile(path, decoded / "smali/cn/gaoming/tv" / path.name)


def build(args, work):
    java = args.java
    sdk = args.android_build_tools
    exe = ".exe" if os.name == "nt" else ""
    apktool = (java, "-jar", args.apktool_jar)
    if sha(args.apktool_jar.read_bytes()) != APKTOOL_SHA:
        raise ValueError("Unexpected Apktool 3.0.3 SHA-256")
    # Native SDK tools on Windows can fail to open a non-ASCII absolute input path.
    base = work / "base-167.apk"
    shutil.copyfile(args.base_apk, base)
    if sha(base.read_bytes()) != BASE_SHA:
        raise ValueError("Input is not the pinned 1.6.7 test APK")
    args.base_apk = base

    framework = work / "framework"
    decoded = work / "decoded"
    run(*apktool, "d", "-r", "--no-assets", "-p", framework, "-o", decoded, args.base_apk)
    apply_terminal_hook(decoded, args.source_root)

    add_fallback_class(args, work, decoded, framework, apktool)
    run(*apktool, "b", "--no-apk", "-p", framework, decoded)
    raw = work / "unsigned.apk"
    with ZipFile(args.base_apk) as base, ZipFile(raw, "w", compresslevel=6) as dest:
        dest.comment = base.comment
        for info in base.infolist():
            name = info.filename
            if SIGNATURE_ENTRY.fullmatch(name):
                continue
            data = base.read(info)
            if name == "AndroidManifest.xml":
                data = make_manifest(data)
            elif name == "classes.dex":
                data = (decoded / "build/apk/classes.dex").read_bytes()
            dest.writestr(info, data)
    aligned = work / "aligned.apk"
    run(sdk / ("zipalign" + exe), "-P", "16", "4", raw, aligned)
    run(sdk / ("zipalign" + exe), "-c", "-P", "16", "4", aligned)
    aapt2 = sdk / ("aapt2" + exe)
    def tree(apk):
        return run(aapt2, "dump", "xmltree", apk, "--file", "AndroidManifest.xml", capture=True).stdout.decode("utf-8").splitlines()
    delta = list(difflib.unified_diff(tree(args.base_apk), tree(aligned), n=0))
    expected_added = [s for s in delta if s.startswith("+") and not s.startswith("+++")]
    expected_removed = [s for s in delta if s.startswith("-") and not s.startswith("---")]
    if (len(expected_added) != 5 or len(expected_removed) != 2 or
            not all(any(token in line for line in expected_added) for token in
                    ('=15', '"1.6.8"', 'E: queries', 'E: package', '"com.tv.qx"'))):
        raise ValueError("Unexpected compiled manifest changes")
    return aligned


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("base-apk", "apktool-jar", "android-build-tools", "android-platform-jar",
                 "output"):
        parser.add_argument("--" + flag, required=True, type=Path)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Repository root containing patches/ and channel-policy/")
    parser.add_argument("--java", default="java", help="JDK java executable")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gaoming168-") as tmp, tempfile.TemporaryDirectory(dir=args.output.parent) as sibling:
        if os.name == "nt":
            # Limit the NTFS case-sensitive attribute to the new temporary tree.
            # Apktool also preserves colliding classes by suffix if fsutil is unavailable.
            fsutil = shutil.which("fsutil.exe")
            if fsutil:
                subprocess.run([fsutil, "file", "SetCaseSensitiveInfo", tmp, "enable"], capture_output=True)
        built = build(args, Path(tmp))
        staged = Path(sibling) / "complete.apk"
        shutil.copyfile(built, staged)
        os.link(staged, args.output)
    print(sha(args.output.read_bytes()), args.output)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"Build failed: {error}")