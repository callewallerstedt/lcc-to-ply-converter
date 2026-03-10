#!/usr/bin/env python3
import argparse
import json
import math
import struct
import zipfile
from pathlib import Path

import numpy as np

SH_C0 = 0.28209479177387814
RSQRT2 = 1.0 / math.sqrt(2.0)
SQRT2 = math.sqrt(2.0)


def unzip_if_needed(input_path: Path, work_dir: Path) -> Path:
    if input_path.is_dir():
        return input_path
    if input_path.suffix.lower() != ".zip":
        raise ValueError(f"Unsupported input: {input_path}")
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / input_path.stem.replace(" ", "_")
    if not out.exists():
        out.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(input_path, "r") as zf:
            zf.extractall(out)
    return out


def find_lcc_bundle(root: Path):
    lcc = list(root.rglob("*.lcc"))
    if not lcc:
        raise FileNotFoundError("No .lcc metadata file found")
    meta_path = lcc[0]
    base = meta_path.parent
    data = base / "data.bin"
    index = base / "index.bin"
    env = base / "environment.bin"
    if not data.exists() or not index.exists():
        raise FileNotFoundError("Missing data.bin or index.bin beside .lcc")
    return meta_path, data, index, (env if env.exists() else None)


def get_attr_range(meta, name):
    for a in meta.get("attributes", []):
        if a.get("name") == name:
            return a["min"], a["max"]
    raise KeyError(f"Missing attribute {name}")


def parse_index(index_path: Path, num_lods: int):
    unit_size = 4 + 16 * num_lods
    b = index_path.read_bytes()
    if len(b) % unit_size != 0:
        raise ValueError("index.bin size mismatch")
    units = len(b) // unit_size
    lod_segments = [[] for _ in range(num_lods)]

    off = 0
    for _ in range(units):
        _cell = struct.unpack_from("<I", b, off)[0]
        off += 4
        for lod in range(num_lods):
            count, data_off, data_size = struct.unpack_from("<IQI", b, off)
            off += 16
            if count > 0 and data_size > 0:
                lod_segments[lod].append((data_off, data_size, count))

    for lod in range(num_lods):
        lod_segments[lod].sort(key=lambda x: x[0])
    return lod_segments


def write_ply_header(f, count: int):
    hdr = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {count}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property float nx\n"
        "property float ny\n"
        "property float nz\n"
        "property float f_dc_0\n"
        "property float f_dc_1\n"
        "property float f_dc_2\n"
        "property float opacity\n"
        "property float scale_0\n"
        "property float scale_1\n"
        "property float scale_2\n"
        "property float rot_0\n"
        "property float rot_1\n"
        "property float rot_2\n"
        "property float rot_3\n"
        "end_header\n"
    )
    f.write(hdr.encode("ascii"))


def decode_chunk(raw: bytes, scale_min, scale_max):
    rec = np.frombuffer(raw, dtype=np.dtype([
        ("pos", "<f4", (3,)),
        ("rgba", "<u4"),
        ("scale_q", "<u2", (3,)),
        ("rot_q", "<u4"),
        ("normal", "<u2", (3,)),
    ]))

    n = rec.shape[0]
    out = np.empty((n, 17), dtype=np.float32)
    out[:, 0:3] = rec["pos"]
    out[:, 3:6] = 0.0

    rgba = rec["rgba"]
    r = ((rgba >> 0) & 0xFF).astype(np.float32) / 255.0
    g = ((rgba >> 8) & 0xFF).astype(np.float32) / 255.0
    b = ((rgba >> 16) & 0xFF).astype(np.float32) / 255.0
    a = ((rgba >> 24) & 0xFF).astype(np.float32) / 255.0

    out[:, 6] = (r - 0.5) / SH_C0
    out[:, 7] = (g - 0.5) / SH_C0
    out[:, 8] = (b - 0.5) / SH_C0

    a = np.clip(a, 1e-6, 1.0 - 1e-6)
    out[:, 9] = np.log(a / (1.0 - a))

    sq = rec["scale_q"].astype(np.float32) / 65535.0
    s_linear = scale_min + sq * (scale_max - scale_min)
    s_linear = np.clip(s_linear, 1e-12, None)
    out[:, 10:13] = np.log(s_linear)

    rq = rec["rot_q"]
    idx = (rq >> 30).astype(np.int32)
    p0 = ((rq >> 0) & 0x3FF).astype(np.float32) / 1023.0
    p1 = ((rq >> 10) & 0x3FF).astype(np.float32) / 1023.0
    p2 = ((rq >> 20) & 0x3FF).astype(np.float32) / 1023.0

    c0 = p0 * SQRT2 - RSQRT2
    c1 = p1 * SQRT2 - RSQRT2
    c2 = p2 * SQRT2 - RSQRT2

    w = np.zeros(n, dtype=np.float32)
    x = np.zeros(n, dtype=np.float32)
    y = np.zeros(n, dtype=np.float32)
    z = np.zeros(n, dtype=np.float32)

    m = idx == 0
    y[m], z[m], w[m] = c0[m], c1[m], c2[m]
    x[m] = np.sqrt(np.clip(1.0 - (y[m] ** 2 + z[m] ** 2 + w[m] ** 2), 0.0, 1.0))

    m = idx == 1
    x[m], z[m], w[m] = c0[m], c1[m], c2[m]
    y[m] = np.sqrt(np.clip(1.0 - (x[m] ** 2 + z[m] ** 2 + w[m] ** 2), 0.0, 1.0))

    m = idx == 2
    x[m], y[m], w[m] = c0[m], c1[m], c2[m]
    z[m] = np.sqrt(np.clip(1.0 - (x[m] ** 2 + y[m] ** 2 + w[m] ** 2), 0.0, 1.0))

    m = idx == 3
    x[m], y[m], z[m] = c0[m], c1[m], c2[m]
    w[m] = np.sqrt(np.clip(1.0 - (x[m] ** 2 + y[m] ** 2 + z[m] ** 2), 0.0, 1.0))

    qn = np.sqrt(w*w + x*x + y*y + z*z)
    qn = np.clip(qn, 1e-12, None)
    out[:, 13] = w / qn
    out[:, 14] = x / qn
    out[:, 15] = y / qn
    out[:, 16] = z / qn

    return out


def convert_lod(data_path: Path, segments, out_path: Path, scale_min, scale_max):
    total = sum(c for _, _, c in segments)
    with out_path.open("wb") as fo:
        write_ply_header(fo, total)
        with data_path.open("rb") as fd:
            for i, (off, size, count) in enumerate(segments, start=1):
                fd.seek(off)
                raw = fd.read(size)
                arr = decode_chunk(raw, scale_min, scale_max)
                if arr.shape[0] != count:
                    raise RuntimeError(f"Segment {i} mismatch")
                arr.astype("<f4", copy=False).tofile(fo)
    return total


def convert_environment(env_path: Path, out_path: Path, scale_min, scale_max):
    raw = env_path.read_bytes()
    if len(raw) % 32 != 0:
        return 0
    with out_path.open("wb") as fo:
        write_ply_header(fo, len(raw) // 32)
        arr = decode_chunk(raw, scale_min, scale_max)
        arr.astype("<f4", copy=False).tofile(fo)
    return len(raw) // 32


def convert_one(input_item: Path, out_dir: Path, lod: int, include_env: bool, work_dir: Path):
    root = unzip_if_needed(input_item, work_dir)
    meta_path, data_path, index_path, env_path = find_lcc_bundle(root)
    meta = json.loads(meta_path.read_text())

    if meta.get("fileType") != "Portable":
        raise NotImplementedError("Only Portable fileType supported in this version")

    num_lods = int(meta["totalLevel"])
    if lod < 0 or lod >= num_lods:
        raise ValueError(f"LOD out of range: 0..{num_lods-1}")

    scale_min, scale_max = get_attr_range(meta, "scale")
    scale_min = np.array(scale_min, dtype=np.float32)
    scale_max = np.array(scale_max, dtype=np.float32)

    segments = parse_index(index_path, num_lods)[lod]
    if not segments:
        raise RuntimeError(f"No data in LOD {lod}")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_main = out_dir / f"lod{lod}.ply"
    count = convert_lod(data_path, segments, out_main, scale_min, scale_max)
    print(f"[OK] {input_item.name} -> {out_main} ({count} splats)")

    if include_env and env_path:
        env_out = out_dir / "environment.ply"
        env_count = convert_environment(env_path, env_out, scale_min, scale_max)
        print(f"[OK] environment -> {env_out} ({env_count} splats)")


def main():
    ap = argparse.ArgumentParser(description="LCC (Xgrids) to PLY converter")
    ap.add_argument("input", nargs="?", help=".zip or extracted folder")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--lod", type=int, default=0)
    ap.add_argument("--include-environment", action="store_true")
    ap.add_argument("--work-dir", default="tmp")
    ap.add_argument("--input-dir", help="Batch mode: convert every .zip and folder in this directory")
    args = ap.parse_args()

    work_dir = Path(args.work_dir)

    if args.input_dir:
        in_dir = Path(args.input_dir)
        out_base = Path(args.out_dir)
        items = []
        for p in sorted(in_dir.iterdir()):
            if p.is_dir() or p.suffix.lower() == ".zip":
                items.append(p)
        if not items:
            raise RuntimeError(f"No folders or zip files in {in_dir}")
        for item in items:
            safe_name = item.stem.replace(" ", "_")
            convert_one(item, out_base / safe_name, args.lod, args.include_environment, work_dir)
        return

    if not args.input:
        raise RuntimeError("Provide input path or use --input-dir")

    convert_one(Path(args.input), Path(args.out_dir), args.lod, args.include_environment, work_dir)


if __name__ == "__main__":
    main()
