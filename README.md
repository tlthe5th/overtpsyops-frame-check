# overtpsyops-frame-check

An open-source, command-line tool for testing disputed video frames through repeatable pixel, cadence, and alignment measurements.

Built on a simple principle: **do not judge by appearance alone—measure the pixels, document the chain of custody, and state only what the data actually supports.**

---

## What This Tool Measures

1. **Chain-of-Custody Fingerprint (`SHA-256`):** Records the exact cryptographic hash of the local video file so anyone else can verify they are testing the identical file.
2. **Stream & Repeat-Cadence Audit:** Inspects resolution, field order (`progressive` vs. `interlaced`), and frame-to-frame duplicate patterns (e.g., `3-1-3-3-2-2`) to distinguish variable-frame-rate (VFR) frame duplication from software motion interpolation.
3. **Linear Cross-Fade Blend Test (`α`, `MAE`, `R²`):** Tests whether a disputed frame (`N`) is a mathematical cross-fade of its neighboring frames (`N-1` and `N+1`).
4. **Subpixel Registration & Overlay:** Aligns neighboring frames via phase correlation before differencing, saving a 50/50 overlay (`overlay.png`) to expose or rule out spatial shifts and foreign splices.
5. **Noise-Floor, Matched-Baseline Controls & Row Profiles:** Compares brightness changes in the target region against a quiet-frame noise floor and external patches of matching baseline brightness, alongside a `16×16` macroblock grid (`diff_16x16_grid.png`).

---

## What "Consistent With" Means

Pixel measurements establish **where** light changed, **by how much** (`0–255` scale), and **in what frame sequence**. They do **not** identify who filmed a video, what object produced a flash, or what political narrative surrounds it. Every report separates measured numbers from interpretation and lists explicit methodological limits.

---

## Installation

Requires **Python 3.10+** and **`ffprobe`** (from FFmpeg) installed on your system `PATH`.

```bash
pip install -r requirements.txt
```

## Usage (Local Video Files Only)

This tool accepts local video files only. Record where and when you acquired the file using the provenance flags:

```bash
python forensics.py video.mp4 \
  --frames 57 58 59 \
  --roi 240 280 320 400 \
  --quiet 51 52 \
  --source "Platform / Archive reference" \
  --uploader "@account_name" \
  --event-time "2026-03-03" \
  --download-date "2026-11-24"
```

All outputs are written to `proof_pack/` (`report.md`, `overlay.png`, `diff_4x.png`, and `diff_16x16_grid.png`) with local directory paths automatically scrubbed.

## Running the Built-In Verification Tests

```bash
python -m unittest discover -s tests -v
```

## License

Licensed under the GNU General Public License v3.0 (GPL-3.0).
