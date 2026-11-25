> **Local PowerShell Setup:** Download/extract the ZIP, then run `python -m pip install -r requirements.txt` and `python server.py` in PowerShell, and open `http://127.0.0.1:8765`.

# overtpsyops-frame-check

An open-source, command-line tool (with an optional local browser interface) for testing disputed video frames through repeatable pixel, cadence, and alignment measurements.

Built on a simple principle: do not judge by appearance alone—measure the pixels, document the chain of custody, and state only what the data actually supports.

## What This Tool Measures

* **Chain-of-Custody Fingerprint (SHA-256):** Records the exact cryptographic hash of the local video file so anyone else can verify they are testing the identical file.
* **Stream & Repeat-Cadence Audit:** Inspects resolution, field order (progressive vs. interlaced), and frame-to-frame duplicate patterns (e.g., `3-1-3-3-2-2`) to distinguish variable-frame-rate (VFR) frame duplication from software motion interpolation.
* **Linear Cross-Fade Blend Test ($\alpha$, MAE, $R^2$):** Tests whether a disputed frame ($N$) is a mathematical cross-fade of its neighboring frames ($N-1$ and $N+1$).
* **Subpixel Registration & Overlay:** Aligns neighboring frames via phase correlation before differencing, saving a 50/50 overlay (`overlay.png`) to expose or rule out spatial shifts and foreign splices.
* **Noise-Floor, Matched-Baseline Controls & Row Profiles:** Compares brightness changes in the target region against a quiet-frame noise floor and external patches of matching baseline brightness, alongside a 16×16 macroblock grid (`diff_16x16_grid.png`).

## What "Consistent With" Means

Pixel measurements establish where light changed, by how much (`0–255` scale), and in what frame sequence. They do not identify who filmed a video, what object produced a flash, or what political narrative surrounds it. Every report separates measured numbers from interpretation and lists explicit methodological limits.

## Installation

Requires Python 3.10+ and `ffprobe` (from FFmpeg) installed on your system PATH.

```powershell
python -m pip install -r requirements.txt
