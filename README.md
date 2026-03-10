# LCC to PLY Converter

Convert LCC bundles to Gaussian-splat style PLY files.

## What you need
For each scene, you need:
- `*.lcc` (metadata)
- `data.bin`
- `index.bin`
- optional: `environment.bin`

You can provide either:
- a `.zip` containing those files, or
- an extracted folder containing those files.

## Quick Windows usage (double-click)
1. Install Python 3.10+ (with `python` in PATH).
2. Put your `.zip` files or extracted LCC folders in `input/`.
3. Double-click `convert_all.bat`.
4. Outputs appear in `output/<input-name>/lod0.ply`.

## CLI usage
Single input:
```bash
python lcc_to_ply.py "RITA CELL.zip" --out-dir output_rita --lod 0 --include-environment
```

Batch input folder:
```bash
python lcc_to_ply.py --input-dir input --out-dir output --lod 0 --include-environment
```

## Quality notes
- This version supports `fileType = Portable`.
- Portable LCC does not include full SH payload, so this is the highest quality possible from available data, but not perfectly lossless vs original source floats.

## Output fields in PLY
- `x,y,z`
- `nx,ny,nz` (set to 0)
- `f_dc_0,f_dc_1,f_dc_2`
- `opacity`
- `scale_0,scale_1,scale_2`
- `rot_0,rot_1,rot_2,rot_3`
