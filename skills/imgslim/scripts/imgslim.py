#!/usr/bin/env python3
"""imgslim — placement-aware, perceptual-quality image compression for project assets.

Subcommands:
  deps                       check required CLI tools
  analyze [paths...]         inventory images, flag oversized ones based on their placement
  compress <files...>        compress/convert with perceptual quality search

Design:
  - Perceptual search: for lossy encodes, binary-search the quality setting for the
    lowest value whose DSSIM score vs the original stays under the preset target
    (this is what makes iLoveIMG-style compression beat fixed-quality tools).
  - Never-larger guarantee: if the result is not smaller than the original, the
    original is kept untouched.
  - Conversion never deletes the source file; the caller updates references first.
"""

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------- tool lookup

BREW_PREFIXES = ["/opt/homebrew", "/usr/local"]


def find_tool(name, keg=None):
    # Keg-only formulas (mozjpeg) are checked before PATH: /opt/homebrew/bin/cjpeg
    # is usually libjpeg-turbo's, which compresses noticeably worse than mozjpeg's.
    if keg:
        for prefix in BREW_PREFIXES:
            cand = os.path.join(prefix, "opt", keg, "bin", name)
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    p = shutil.which(name)
    if p:
        return p
    for prefix in BREW_PREFIXES:
        cand = os.path.join(prefix, "bin", name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


TOOLS = {
    "pngquant": lambda: find_tool("pngquant"),
    "oxipng":   lambda: find_tool("oxipng"),
    "cwebp":    lambda: find_tool("cwebp"),
    "dwebp":    lambda: find_tool("dwebp"),
    "cjpeg":    lambda: find_tool("cjpeg", keg="mozjpeg"),
    "jpegtran": lambda: find_tool("jpegtran", keg="mozjpeg"),
    "dssim":    lambda: find_tool("dssim"),
    "sips":     lambda: find_tool("sips") if sys.platform == "darwin" else None,
    "magick":   lambda: find_tool("magick"),
}
_tool_cache = {}


def tool(name):
    if name not in _tool_cache:
        _tool_cache[name] = TOOLS[name]()
    return _tool_cache[name]


def need(name):
    p = tool(name)
    if not p:
        die(f"required tool '{name}' not found — run: {INSTALL_HINT}")
    return p


if sys.platform == "darwin":
    INSTALL_HINT = "brew install pngquant oxipng webp mozjpeg dssim"
elif sys.platform.startswith("linux"):
    INSTALL_HINT = ("sudo apt install pngquant webp imagemagick && "
                    "cargo install oxipng dssim  # mozjpeg: build from "
                    "github.com/mozilla/mozjpeg or use distro libjpeg-turbo's cjpeg")
else:
    INSTALL_HINT = ("scoop install pngquant libwebp mozjpeg imagemagick  # dssim/oxipng: "
                    "download releases from github.com/kornelski/dssim and shssoichiro/oxipng")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# Decode/resize backend: sips on macOS (built in), ImageMagick elsewhere.

def decode_image(src, out):
    """Convert src to the format implied by out's extension."""
    if src.lower().endswith(".webp") and tool("dwebp") and out.lower().endswith(".png"):
        r = run([tool("dwebp"), src, "-o", out])
    elif tool("sips"):
        fmt = os.path.splitext(out)[1][1:].replace("jpg", "jpeg")
        r = run([tool("sips"), "-s", "format", fmt, src, "--out", out])
    elif tool("magick"):
        r = run([tool("magick"), src, out])
    else:
        die("no decoder found — need sips (macOS) or ImageMagick 'magick'; " + INSTALL_HINT)
    if r.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(f"decode failed: {r.stderr.strip()}")
    return out


def resize_image(path, max_dim=None, exact=None):
    if tool("sips"):
        cmd = [tool("sips"), "-z", str(exact[1]), str(exact[0]), path] if exact \
            else [tool("sips"), "-Z", str(max_dim), path]
    elif tool("magick"):
        geom = f"{exact[0]}x{exact[1]}!" if exact else f"{max_dim}x{max_dim}>"
        cmd = [tool("magick"), path, "-resize", geom, path]
    else:
        die("no resizer found — need sips (macOS) or ImageMagick 'magick'; " + INSTALL_HINT)
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"resize failed: {r.stderr.strip()}")


def die(msg):
    print(f"imgslim: error: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------- dimension parsing

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def read_dimensions(path):
    """Return (width, height, format) parsing file headers directly, or None."""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", head[16:24])
                return w, h, "png"
            if head[:3] == b"GIF":
                w, h = struct.unpack("<HH", head[6:10])
                return w, h, "gif"
            if head[:2] == b"BM":
                w, h = struct.unpack("<ii", head[18:26])
                return w, abs(h), "bmp"
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
                f.seek(0)
                d = f.read(64)
                fmt = d[12:16]
                if fmt == b"VP8X":
                    w = int.from_bytes(d[24:27], "little") + 1
                    h = int.from_bytes(d[27:30], "little") + 1
                elif fmt == b"VP8L":
                    bits = int.from_bytes(d[21:25], "little")
                    w = (bits & 0x3FFF) + 1
                    h = ((bits >> 14) & 0x3FFF) + 1
                elif fmt == b"VP8 ":
                    w = int.from_bytes(d[26:28], "little") & 0x3FFF
                    h = int.from_bytes(d[28:30], "little") & 0x3FFF
                else:
                    return None
                return w, h, "webp"
            if head[:2] == b"\xff\xd8":
                f.seek(2)
                while True:
                    b = f.read(1)
                    if not b:
                        return None
                    if b != b"\xff":
                        continue
                    while b == b"\xff":
                        b = f.read(1)
                    marker = b[0]
                    if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                        f.read(3)
                        h, w = struct.unpack(">HH", f.read(4))
                        return w, h, "jpeg"
                    if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                        continue
                    (seglen,) = struct.unpack(">H", f.read(2))
                    f.seek(seglen - 2, 1)
    except (OSError, struct.error, IndexError):
        return None
    return None


def png_has_alpha(path):
    try:
        with open(path, "rb") as f:
            head = f.read(26)
        return head[:8] == b"\x89PNG\r\n\x1a\n" and head[25] in (4, 6)
    except OSError:
        return False


def webp_is_lossy(path):
    """Walk the RIFF chunks (VP8X containers put the bitstream after
    metadata chunks) and report whether the image data is lossy VP8."""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
            if head[:4] != b"RIFF" or head[8:12] != b"WEBP":
                return False
            while True:
                hdr = f.read(8)
                if len(hdr) < 8:
                    return False
                tag = hdr[:4]
                size = int.from_bytes(hdr[4:8], "little")
                if tag == b"VP8 ":
                    return True
                if tag == b"VP8L":
                    return False
                f.seek(size + (size & 1), 1)
    except OSError:
        return False


# ------------------------------------------------------- placement size rules

ANDROID_DENSITY = {"ldpi": 0.75, "mdpi": 1.0, "hdpi": 1.5,
                   "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}


def expected_size(path):
    """Infer the expected pixel size of an image from where it lives.

    Returns (max_w, max_h, rule_description) or None when no rule applies.
    """
    norm = path.replace(os.sep, "/")
    base = os.path.basename(norm)

    # iOS asset catalogs: Contents.json states the exact size.
    if ".appiconset/" in norm or ".imageset/" in norm:
        cj = os.path.join(os.path.dirname(path), "Contents.json")
        try:
            with open(cj) as f:
                data = json.load(f)
            for img in data.get("images", []):
                if img.get("filename") == base and img.get("size"):
                    w, h = (float(x) for x in img["size"].split("x"))
                    scale = float(img.get("scale", "1x").rstrip("x"))
                    return int(w * scale), int(h * scale), \
                        f"iOS asset catalog: {img['size']} @{img.get('scale', '1x')}"
        except (OSError, ValueError, KeyError):
            pass
        return None

    # Android density buckets.
    m = re.search(r"/(?:mipmap|drawable)-[^/]*?(ldpi|mdpi|hdpi|xhdpi|xxhdpi|xxxhdpi)[^/]*/", norm)
    if m:
        factor = ANDROID_DENSITY[m.group(1)]
        if base.startswith("ic_launcher_foreground"):
            dp = 108
        elif base.startswith("ic_launcher"):
            dp = 48
        elif base.startswith("ic_stat_") or base.startswith("ic_notification"):
            dp = 24
        else:
            dp = None
        if dp:
            px = round(dp * factor)
            return px, px, f"Android {m.group(1)} {dp}dp icon"

    # Well-known web assets.
    if base.startswith("apple-touch-icon"):
        return 180, 180, "apple-touch-icon (180px)"
    if re.match(r"og[-_]?image|social[-_]?card", base):
        return 1200, 630, "Open Graph image (1200x630)"

    # A NxN / NxM in the filename states intent (favicon-32x32.png, hero_800x600.jpg).
    m = re.search(r"(?<!\d)(\d{2,4})x(\d{2,4})(?!\d)", base)
    if m:
        return int(m.group(1)), int(m.group(2)), f"size in filename ({m.group(0)})"

    return None


SKIP_DIRS = {".git", "node_modules", "build", "dist", "out", "DerivedData",
             "Pods", ".next", ".gradle", "vendor", "target", ".venv", "venv"}


def iter_images(paths):
    for p in paths:
        if os.path.isfile(p):
            if os.path.splitext(p)[1].lower() in IMAGE_EXTS:
                yield p
        else:
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for f in sorted(files):
                    if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                        yield os.path.join(root, f)


# ------------------------------------------------------------------- analyze

def cmd_analyze(args):
    rows = []
    for path in iter_images(args.paths or ["."]):
        dims = read_dimensions(path)
        if not dims:
            continue
        w, h, fmt = dims
        size = os.path.getsize(path)
        flags = []
        exp = expected_size(path)
        if exp:
            ew, eh, rule = exp
            if w > ew or h > eh:
                flags.append(f"OVERSIZED: {w}x{h}, expected <= {ew}x{eh} ({rule})")
        rows.append({"path": path, "format": fmt, "width": w, "height": h,
                     "bytes": size, "flags": flags})

    rows.sort(key=lambda r: -r["bytes"])
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    total = sum(r["bytes"] for r in rows)
    print(f"{len(rows)} images, {human(total)} total\n")
    for r in rows:
        line = f"{human(r['bytes']):>9}  {r['format']:<4} {r['width']}x{r['height']:<6} {r['path']}"
        print(line)
        for fl in r["flags"]:
            print(f"           ⚠ {fl}")


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


# ------------------------------------------------------------------ compress

PRESETS = {
    "high":     {"dssim": 0.0010, "png_q": "80-98", "fixed_q": 88},
    "balanced": {"dssim": 0.0028, "png_q": "65-90", "fixed_q": 80},
    "small":    {"dssim": 0.0065, "png_q": "40-75", "fixed_q": 70},
    "lossless": {},
}


class Workspace:
    """Per-file temp dir with cached decodes of the (possibly resized) source."""

    def __init__(self, src, max_dim, resize):
        self.tmp = tempfile.mkdtemp(prefix="imgslim-")
        self.src = src
        self._png = None
        self._bmp = None
        work = os.path.join(self.tmp, "work" + os.path.splitext(src)[1].lower())
        shutil.copyfile(src, work)
        dims = read_dimensions(src)
        if resize:
            resize_image(work, exact=resize)
        elif max_dim and dims and max(dims[0], dims[1]) > max_dim:
            resize_image(work, max_dim=max_dim)
        self.work = work

    def png(self):
        if not self._png:
            self._png = self._decode(self.work, "png")
        return self._png

    def cjpeg_input(self):
        """(path, extra cjpeg flags). cjpeg can't read PNG/BMP-v4; feed it TGA
        (sips) or PPM (magick)."""
        if not self._bmp:
            if tool("sips"):
                self._bmp = (self._decode(self.work, "tga"), ["-targa"])
            else:
                self._bmp = (self._decode(self.work, "ppm"), [])
        return self._bmp

    def _decode(self, src, fmt):
        if src.lower().endswith("." + fmt):
            return src
        return decode_image(src, os.path.join(self.tmp, f"decoded.{fmt}"))

    def to_png(self, candidate):
        """Decode an encoded candidate back to PNG for metric comparison."""
        return decode_image(candidate, candidate + ".png")

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def dssim_score(orig_png, cand_png):
    r = run([need("dssim"), orig_png, cand_png])
    if r.returncode != 0:
        raise RuntimeError(f"dssim failed: {r.stderr.strip()}")
    return float(r.stdout.split()[0])


def quality_search(ws, encode, target, lo=30, hi=95):
    """Find the lowest quality q in [lo, hi] with DSSIM <= target.

    encode(q) -> path of candidate. Returns (q, path) of best candidate, or the
    hi-quality encode if even that misses the target (guard rail).
    """
    if not tool("dssim"):
        return None  # caller falls back to fixed quality
    orig = ws.png()
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = encode(mid)
        score = dssim_score(orig, ws.to_png(cand))
        if score <= target:
            best = (mid, cand)
            hi = mid - 1
        else:
            lo = mid + 1
    if best is None:
        q = 95
        return q, encode(q)
    return best


def encode_png(ws, preset, outdir):
    out = os.path.join(outdir, "out.png")
    src = ws.png()
    lossy_ok = False
    if preset != "lossless" and tool("pngquant"):
        # pngquant's internal quality gate misses banding in subtle dark
        # gradients (flat-color icons with soft shadows), so its output must
        # also pass the same DSSIM gate the other codecs use; escalate the
        # quality floor once, then give up and go lossless.
        target = PRESETS[preset]["dssim"]
        for qrange in (PRESETS[preset]["png_q"], "95-100"):
            r = run([tool("pngquant"), "--quality", qrange, "--speed", "1",
                     "--strip", "--force", "--output", out, src])
            if r.returncode == 99:  # even the range's min quality not reachable
                break
            if r.returncode != 0:
                raise RuntimeError(f"pngquant failed: {r.stderr.strip()}")
            if not tool("dssim") or dssim_score(src, out) <= target:
                lossy_ok = True
                break
    if not lossy_ok:
        shutil.copyfile(src, out)
    if tool("oxipng"):
        run([tool("oxipng"), "-o", "2", "--strip", "safe", "-q", out])
    return out


def encode_jpeg(ws, preset, outdir):
    cjpeg = need("cjpeg")
    src_is_jpeg = ws.work.lower().endswith((".jpg", ".jpeg"))
    if preset == "lossless":
        if not src_is_jpeg:
            raise RuntimeError("lossless preset cannot convert to JPEG")
        out = os.path.join(outdir, "out.jpg")
        r = run([need("jpegtran"), "-copy", "none", "-optimize", "-progressive",
                 "-outfile", out, ws.work])
        if r.returncode != 0:
            raise RuntimeError(f"jpegtran failed: {r.stderr.strip()}")
        return out
    src, flags = ws.cjpeg_input()

    def enc(q):
        cand = os.path.join(outdir, f"q{q}.jpg")
        sample = "1x1" if q >= 90 else "2x2"
        r = run([cjpeg, "-quality", str(q), "-optimize", "-progressive",
                 "-sample", sample, *flags, "-outfile", cand, src])
        if r.returncode != 0:
            raise RuntimeError(f"cjpeg failed: {r.stderr.strip()}")
        return cand

    found = quality_search(ws, enc, PRESETS[preset]["dssim"])
    return found[1] if found else enc(PRESETS[preset]["fixed_q"])


def encode_webp(ws, preset, outdir):
    cwebp = need("cwebp")
    src = ws.png()
    candidates = []

    if preset == "lossless" or not png_has_photo_content(ws):
        lossless = os.path.join(outdir, "lossless.webp")
        r = run([cwebp, "-lossless", "-z", "9", "-quiet", src, "-o", lossless])
        if r.returncode == 0:
            candidates.append(lossless)
    if preset != "lossless":
        def enc(q):
            cand = os.path.join(outdir, f"q{q}.webp")
            r = run([cwebp, "-q", str(q), "-m", "6", "-quiet", src, "-o", cand])
            if r.returncode != 0:
                raise RuntimeError(f"cwebp failed: {r.stderr.strip()}")
            return cand
        found = quality_search(ws, enc, PRESETS[preset]["dssim"])
        candidates.append(found[1] if found else enc(PRESETS[preset]["fixed_q"]))
    if not candidates:
        raise RuntimeError("webp encode produced no candidates")
    return min(candidates, key=os.path.getsize)


def png_has_photo_content(ws):
    """Heuristic: large PNGs are usually photos/screenshots -> lossy wins;
    small ones are icons/logos where lossless webp often wins. Both are tried
    when this returns False, so the heuristic only saves time, never quality."""
    dims = read_dimensions(ws.work)
    return bool(dims) and dims[0] * dims[1] > 512 * 512


ENCODERS = {"png": encode_png, "jpeg": encode_jpeg, "webp": encode_webp}
EXT = {"png": ".png", "jpeg": ".jpg", "webp": ".webp"}


def cmd_compress(args):
    preset = args.preset
    results = []
    for src in args.files:
        if not os.path.isfile(src):
            results.append({"path": src, "status": "error", "error": "not found"})
            continue
        orig_bytes = os.path.getsize(src)
        src_fmt = (read_dimensions(src) or (0, 0, None))[2]
        if src_fmt is None:
            results.append({"path": src, "status": "skipped", "error": "unrecognized format"})
            continue
        target_fmt = src_fmt if args.format == "keep" else args.format
        if target_fmt not in ENCODERS:
            results.append({"path": src, "status": "skipped",
                            "error": f"no encoder for {target_fmt}"})
            continue
        converting = target_fmt != src_fmt

        # Re-encoding an already-lossy webp stacks generation loss for little
        # gain (these files were optimized at export time) — visible banding on
        # flat-color UI assets long before metrics look alarming. Leave them be.
        if src_fmt == "webp" and target_fmt == "webp" and preset != "lossless" \
                and not args.force and not (args.max_dim or args.resize) \
                and webp_is_lossy(src):
            results.append({"path": src, "status": "kept",
                            "orig": orig_bytes, "new": orig_bytes,
                            "note": "already lossy webp; use --force to re-encode"})
            continue

        resize = None
        if args.resize:
            resize = tuple(int(x) for x in args.resize.lower().split("x"))
        ws = None
        try:
            ws = Workspace(src, args.max_dim, resize)
            out = ENCODERS[target_fmt](ws, preset, ws.tmp)
            new_bytes = os.path.getsize(out)
            resized = ws.work != src and (args.max_dim or resize) and \
                read_dimensions(ws.work)[:2] != read_dimensions(src)[:2]

            # Same-format lossy re-encodes accumulate generation loss; below 5%
            # savings that trade isn't worth it, so keep the original untouched.
            lossy = preset != "lossless" and target_fmt != "png"
            min_gain = 0.05 if lossy else 0.0
            if not converting and not resized and \
                    new_bytes >= orig_bytes * (1 - min_gain):
                results.append({"path": src, "status": "kept",
                                "orig": orig_bytes, "new": orig_bytes})
                continue

            dest = dest_path(src, target_fmt, converting, args)
            if not args.dry_run:
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                shutil.copyfile(out, dest + ".imgslim-tmp")
                os.replace(dest + ".imgslim-tmp", dest)
            results.append({"path": src, "dest": dest, "status": "done",
                            "orig": orig_bytes, "new": new_bytes,
                            "converted": converting,
                            "dims": "x".join(map(str, read_dimensions(ws.work)[:2]))})
        except RuntimeError as e:
            results.append({"path": src, "status": "error", "error": str(e)})
        finally:
            if ws:
                ws.cleanup()

    report(results, args)


def dest_path(src, target_fmt, converting, args):
    stem, _ = os.path.splitext(os.path.basename(src))
    if args.output_dir:
        return os.path.join(args.output_dir, stem + EXT[target_fmt])
    if converting:
        return os.path.join(os.path.dirname(src), stem + EXT[target_fmt])
    if args.in_place:
        return src
    return os.path.join(os.path.dirname(src), stem + ".min" + EXT[target_fmt])


def report(results, args):
    if args.json:
        print(json.dumps(results, indent=2))
        return
    done = [r for r in results if r["status"] == "done"]
    for r in results:
        if r["status"] == "done":
            pct = (1 - r["new"] / r["orig"]) * 100 if r["orig"] else 0
            extra = " -> " + r["dest"] if r.get("converted") or args.output_dir else ""
            note = " (dry run)" if args.dry_run else ""
            print(f"{r['path']}: {human(r['orig'])} -> {human(r['new'])} "
                  f"(-{pct:.1f}%, {r['dims']}){extra}{note}")
        elif r["status"] == "kept":
            print(f"{r['path']}: {r.get('note', 'already optimal')} — kept original")
        else:
            print(f"{r['path']}: {r['status'].upper()} - {r.get('error', '')}")
    if done:
        o = sum(r["orig"] for r in done)
        n = sum(r["new"] for r in done)
        print(f"\nTotal: {human(o)} -> {human(n)} (saved {human(o - n)}, "
              f"-{(1 - n / o) * 100:.1f}%)")
    if any(r["status"] == "error" for r in results):
        sys.exit(2)


# ---------------------------------------------------------------------- deps

def cmd_deps(_args):
    optional = {"dwebp", "jpegtran", "oxipng"}
    missing = []
    for name in TOOLS:
        p = tool(name)
        note = " (optional)" if name in optional and not p else ""
        print(f"{name:<9} {('OK  ' + p) if p else 'MISSING' + note}")
        if not p and name not in optional | {"sips", "magick"}:
            missing.append(name)
    if not (tool("sips") or tool("magick")):
        missing.append("imagemagick")
        print("\nneed at least one decode/resize backend: sips (macOS) or ImageMagick")
    if missing:
        print(f"\ninstall: {INSTALL_HINT}")
        sys.exit(1)


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(prog="imgslim", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("deps", help="check required CLI tools")
    d.set_defaults(func=cmd_deps)

    a = sub.add_parser("analyze", help="inventory images and flag oversized ones")
    a.add_argument("paths", nargs="*", default=["."])
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_analyze)

    c = sub.add_parser("compress", help="compress/convert images")
    c.add_argument("files", nargs="+")
    c.add_argument("--preset", choices=list(PRESETS), default="high")
    c.add_argument("--format", choices=["keep", "png", "jpeg", "webp"], default="keep")
    c.add_argument("--max-dim", type=int, help="downscale so max(w,h) <= N before encoding")
    c.add_argument("--resize", help="exact WxH resize before encoding (e.g. 48x48)")
    c.add_argument("--in-place", action="store_true",
                   help="overwrite the source file (same-format only)")
    c.add_argument("--output-dir", help="write results into this directory")
    c.add_argument("--force", action="store_true",
                   help="allow lossy re-encode of already-lossy webp sources")
    c.add_argument("--dry-run", action="store_true", help="report sizes, write nothing")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_compress)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
