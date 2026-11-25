import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import cv2
import numpy as np


def compute_sha256(filepath: str) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def probe_stream(filepath: str) -> dict:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate,field_order,pix_fmt,codec_name,nb_frames",
        "-of", "json",
        filepath,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        return data.get("streams", [{}])[0]
    except Exception as e:
        return {"error": f"ffprobe unavailable or failed ({type(e).__name__})"}


def analyze_video(
    video_path: str,
    f_prev_idx: int,
    f_target_idx: int,
    f_next_idx: int,
    roi: tuple,
    quiet_pair: tuple,
    out_dir: str,
    provenance: dict,
) -> dict:
    if not os.path.isfile(video_path):
        raise FileNotFoundError("Input video file not found.")

    os.makedirs(out_dir, exist_ok=True)
    safe_filename = os.path.basename(video_path)
    file_hash = compute_sha256(video_path)
    stream_info = probe_stream(video_path)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("Could not open video stream.")

    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()

    total_frames = len(frames)
    if total_frames == 0:
        raise RuntimeError("No frames decoded from video.")

    # Validate indices (1-based frame numbering matching ffmpeg frame_%04d.png)
    for idx in (f_prev_idx, f_target_idx, f_next_idx, quiet_pair[0], quiet_pair[1]):
        if idx < 1 or idx > total_frames:
            raise ValueError(f"Frame index {idx} out of range (1..{total_frames}).")

    # 1. Cadence Audit around target window
    win_start = max(1, f_prev_idx - 4)
    win_end = min(total_frames, f_next_idx + 8)
    cadence_groups = []
    curr_start = win_start
    curr_count = 1
    for i in range(win_start + 1, win_end + 1):
        diff = float(np.mean(np.abs(frames[i - 1].astype(np.float32) - frames[i - 2].astype(np.float32))))
        if diff < 0.05:
            curr_count += 1
        else:
            cadence_groups.append((curr_start, i - 1, curr_count))
            curr_start = i
            curr_count = 1
    cadence_groups.append((curr_start, win_end, curr_count))
    cadence_str = "-".join(str(g[2]) for g in cadence_groups)

    f_prev = frames[f_prev_idx - 1].astype(np.float32)
    f_targ = frames[f_target_idx - 1].astype(np.float32)
    f_next = frames[f_next_idx - 1].astype(np.float32)

    # 2. Linear Cross-Fade Blend Test: Target ≈ alpha * Next + (1 - alpha) * Prev
    diff_pn = f_next - f_prev
    diff_pt = f_targ - f_prev
    denom = float(np.sum(diff_pn ** 2))
    if denom > 0:
        alpha = float(np.sum(diff_pt * diff_pn) / denom)
        reconstructed = alpha * f_next + (1.0 - alpha) * f_prev
        mae_blend = float(np.mean(np.abs(f_targ - reconstructed)))
        ss_res = float(np.sum((f_targ - reconstructed) ** 2))
        ss_tot = float(np.sum((f_targ - np.mean(f_targ)) ** 2))
        r2_blend = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
    else:
        alpha, mae_blend, r2_blend = 0.0, 0.0, 0.0

    # 3. Subpixel Registration (Phase Correlation) & Overlay
    g_prev = np.mean(f_prev, axis=2)
    g_targ = np.mean(f_targ, axis=2)
    h, w = g_prev.shape
    (dx, dy), _ = cv2.phaseCorrelate(g_prev, g_targ)
    M = np.float32([[1, 0, -dx], [0, 1, -dy]])
    g_targ_reg = cv2.warpAffine(g_targ, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    f_targ_reg = cv2.warpAffine(f_targ, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    overlay = cv2.addWeighted(frames[f_prev_idx - 1], 0.5, np.clip(f_targ_reg, 0, 255).astype(np.uint8), 0.5, 0)
    cv2.imwrite(os.path.join(out_dir, "overlay.png"), overlay)

    # 4. Difference Image & 16x16 Macroblock Grid Overlay
    diff_abs = np.abs(f_targ_reg - f_prev)
    diff_boost = np.clip(diff_abs * 4.0, 0, 255).astype(np.uint8)
    cv2.imwrite(os.path.join(out_dir, "diff_4x.png"), diff_boost)

    grid_img = diff_boost.copy()
    for gx in range(0, w, 16):
        cv2.line(grid_img, (gx, 0), (gx, h), (0, 255, 0), 1)
    for gy in range(0, h, 16):
        cv2.line(grid_img, (0, gy), (w, gy), (0, 255, 0), 1)
    cv2.imwrite(os.path.join(out_dir, "diff_16x16_grid.png"), grid_img)

    # 5. Noise-Floor, Matched-Baseline Controls, and Row/Column Profiles
    y1, y2, x1, x2 = roi
    q1 = np.mean(frames[quiet_pair[0] - 1].astype(np.float32), axis=2)
    q2 = np.mean(frames[quiet_pair[1] - 1].astype(np.float32), axis=2)
    noise_mean = float(np.mean(q2[y1:y2, x1:x2] - q1[y1:y2, x1:x2]))
    noise_std = float(np.std(q2[y1:y2, x1:x2] - q1[y1:y2, x1:x2]))

    delta_pt = g_targ_reg - g_prev
    g_next = np.mean(f_next, axis=2)
    delta_tn = g_next - g_targ_reg

    roi_prev_mean = float(np.mean(g_prev[y1:y2, x1:x2]))
    roi_targ_mean = float(np.mean(g_targ_reg[y1:y2, x1:x2]))
    roi_shift = roi_targ_mean - roi_prev_mean

    # Search outside ROI for brightness-matched control patches
    controls = []
    patch_h = max(20, min(60, y2 - y1))
    patch_w = max(20, min(60, x2 - x1))
    for cy in range(10, h - patch_h - 10, 20):
        for cx in range(10, w - patch_w - 10, 20):
            if not (cx + patch_w < x1 or cx > x2 or cy + patch_h < y1 or cy > y2):
                continue
            m_p = float(np.mean(g_prev[cy:cy + patch_h, cx:cx + patch_w]))
            if abs(m_p - roi_prev_mean) <= 2.0:
                m_t = float(np.mean(g_targ_reg[cy:cy + patch_h, cx:cx + patch_w]))
                controls.append((abs(m_p - roi_prev_mean), cy, cx, m_p, m_t, m_t - m_p))
    controls.sort()
    top_controls = controls[:3]

    # Horizontal 8-bin profile across ROI vertical band
    bin_w = max(1, w // 8)
    row_bins = []
    for bx in range(0, w, bin_w):
        bx_end = min(w, bx + bin_w)
        b_prev = float(np.mean(g_prev[y1:y2, bx:bx_end]))
        d_pt = float(np.mean(delta_pt[y1:y2, bx:bx_end]))
        d_tn = float(np.mean(delta_tn[y1:y2, bx:bx_end]))
        sat_next = float(np.mean(g_next[y1:y2, bx:bx_end] >= 254.0) * 100.0)
        row_bins.append((bx, bx_end, b_prev, d_pt, d_tn, sat_next))

    results = {
        "filename": safe_filename,
        "sha256": file_hash,
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "provenance": provenance,
        "stream": stream_info,
        "total_frames": total_frames,
        "frames_analyzed": (f_prev_idx, f_target_idx, f_next_idx),
        "cadence_window": f"{win_start}..{win_end}",
        "cadence_pattern": cadence_str,
        "blend": {"alpha": alpha, "mae": mae_blend, "r2": r2_blend},
        "registration": {"dx": float(dx), "dy": float(dy)},
        "noise_floor": {"pair": quiet_pair, "mean": noise_mean, "std": noise_std},
        "roi": {
            "coords": roi,
            "prev_mean": roi_prev_mean,
            "targ_mean": roi_targ_mean,
            "shift": roi_shift,
        },
        "matched_controls": top_controls,
        "row_bins": row_bins,
    }

    report_md = render_markdown(results)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as rf:
        rf.write(report_md)

    return results


def render_markdown(r: dict) -> str:
    p = r["provenance"]
    s = r["stream"]
    b = r["blend"]
    reg = r["registration"]
    nf = r["noise_floor"]
    roi = r["roi"]
    f_prev, f_targ, f_next = r["frames_analyzed"]

    lines = [
        "# Frame Forensics Measurement Report",
        "",
        "## 1. File Identity & Chain of Custody",
        f"- **File Name:** `{r['filename']}` *(local directory paths scrubbed)*",
        f"- **SHA-256 Hash:** `{r['sha256']}`",
        f"- **Analysis Timestamp:** `{r['generated_utc']}`",
        f"- **Source URL / Platform:** {p.get('source') or '_Not recorded_'}",
        f"- **Original Uploader / Account:** {p.get('uploader') or '_Not recorded_'}",
        f"- **Claimed Event Timestamp:** {p.get('event_time') or '_Not recorded_'}",
        f"- **Local Acquisition Date:** {p.get('download_date') or '_Not recorded_'}",
        "",
        "## 2. Container & Cadence Audit",
        f"- **Resolution / Pixel Format:** `{s.get('width', '?')}x{s.get('height', '?')}`, `{s.get('pix_fmt', '?')}`, field order `{s.get('field_order', '?')}`",
        f"- **Container Frame Rate:** `r_frame_rate={s.get('r_frame_rate', '?')}`, `avg_frame_rate={s.get('avg_frame_rate', '?')}`",
        f"- **Decoded Frame Count:** `{r['total_frames']}` frames",
        f"- **Repeat Cadence (Frames {r['cadence_window']}):** `{r['cadence_pattern']}`",
        "",
        f"## 3. Linear Cross-Fade Blend Test (Frames {f_prev} -> {f_targ} -> {f_next})",
        f"- **Estimated Next-Frame Weight (`alpha`):** `{b['alpha']:.4f}`",
        f"- **Mean Absolute Pixel Error (`0-255` scale):** `{b['mae']:.2f}`",
        f"- **Linear Blend Fit (`R²`):** `{b['r2'] * 100:.2f}%`",
        "",
        f"## 4. Subpixel Alignment & Brightness Controls (Frames {f_prev} -> {f_targ})",
        f"- **Detected Global Shift (`dx, dy`):** `({reg['dx']:+.3f}, {reg['dy']:+.3f})` pixels *(corrected prior to differencing)*",
        f"- **Quiet-Frame Noise Floor (Frames {nf['pair'][0]} -> {nf['pair'][1]}):** `{nf['mean']:+.2f}` units (`std: {nf['std']:.2f}`)",
        f"- **Target ROI (`y={roi['coords'][0]}..{roi['coords'][1]}`, `x={roi['coords'][2]}..{roi['coords'][3]}`):** `{roi['prev_mean']:.2f}` -> `{roi['targ_mean']:.2f}` (`{roi['shift']:+.2f}` units)",
        "",
        "### Brightness-Matched Control Patches (Outside Target ROI)",
    ]
    if r["matched_controls"]:
        for _, cy, cx, m_p, m_t, d_c in r["matched_controls"]:
            lines.append(f"- Patch (`y={cy}`, `x={cx}`): `{m_p:.2f}` -> `{m_t:.2f}` (`{d_c:+.2f}` units)")
    else:
        lines.append("- No external patch matched the ROI baseline within ±2.0 units.")
    lines.extend([
        "",
        f"### Horizontal Row Profile Across ROI Band (`y={roi['coords'][0]}..{roi['coords'][1]}`, unscaled `0-255`)",
        "| Horizontal Bin (`x`) | Frame Prev Baseline | Target − Prev (Reg.) | Next − Target (Reg.) | Next Pixels ≥ 254 |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ])
    for bx, bx_end, b_prev, d_pt, d_tn, sat_next in r["row_bins"]:
        lines.append(f"| `{bx}..{bx_end}` | `{b_prev:.1f}` | `{d_pt:+.1f}` | `{d_tn:+.1f}` | `{sat_next:.1f}%` |")
    lines.extend([
        "",
        "## 5. Measured Findings (Honesty Layer)",
        f"- Target ROI brightness changed by `{roi['shift']:+.2f}` units (`0-255` scale) against a quiet-frame noise floor of `{nf['mean']:+.2f}` units.",
        f"- Linear cross-fade reconstruction scored `R² = {b['r2'] * 100:.2f}%` (`MAE = {b['mae']:.2f}`).",
        "- All numeric observations describe pixel intensity, alignment, and cadence only. Any localized brightness peak is consistent with a localized light event, not proof of a specific physical or political cause.",
        "",
        "## 6. Methodological Limits (What This Tool Does Not Test)",
        "- **Metadata & Container Origin:** Does not verify camera hardware model, GPS coordinates, or original recording timestamp.",
        "- **Upstream Re-Encoding:** Social-media transcodes alter bitrates and color curves before local acquisition.",
        "- **Multi-Source Corroboration:** Does not cross-check external eyewitness angles, satellite imagery, or independent reporting.",
        "- **Narrative & Attribution:** Pixel measurements cannot identify actors, munitions, or intent.",
        "",
        "## 7. Generated Visual Artifacts",
        "- `overlay.png`: 50/50 pixel overlay of registered target frame and prior frame.",
        "- `diff_4x.png`: Unscaled absolute pixel difference amplified 4×.",
        "- `diff_16x16_grid.png`: 4× difference image overlaid with a 16×16 pixel grid.",
    ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Open, repeatable pixel and cadence verification for local video files."
    )
    parser.add_argument("video", help="Path to local video file (e.g., video.mp4)")
    parser.add_argument("--frames", nargs=3, type=int, required=True, metavar=("PREV", "TARGET", "NEXT"),
                        help="Three 1-based frame indices: prior, target, and next frame")
    parser.add_argument("--roi", nargs=4, type=int, default=[240, 280, 320, 400], metavar=("Y1", "Y2", "X1", "X2"),
                        help="Target region of interest (y1 y2 x1 x2). Default: 240 280 320 400")
    parser.add_argument("--quiet", nargs=2, type=int, default=[1, 2], metavar=("Q1", "Q2"),
                        help="Two quiet 1-based frame indices for noise floor. Default: 1 2")
    parser.add_argument("--out", default="proof_pack", help="Output folder name. Default: proof_pack")
    parser.add_argument("--source", default="", help="Provenance: source URL or platform")
    parser.add_argument("--uploader", default="", help="Provenance: original uploader or channel")
    parser.add_argument("--event-time", default="", help="Provenance: claimed date/time of event")
    parser.add_argument("--download-date", default="", help="Provenance: date acquired locally")
    args = parser.parse_args()
    provenance = {
        "source": args.source,
        "uploader": args.uploader,
        "event_time": args.event_time,
        "download_date": args.download_date,
    }
    try:
        results = analyze_video(
            video_path=args.video,
            f_prev_idx=args.frames[0],
            f_target_idx=args.frames[1],
            f_next_idx=args.frames[2],
            roi=tuple(args.roi),
            quiet_pair=tuple(args.quiet),
            out_dir=args.out,
            provenance=provenance,
        )
        print(f"Report generated in '{args.out}/report.md'")
        print(f"SHA-256: {results['sha256']}")
        print(f"Cadence: {results['cadence_pattern']}")
        print(f"Blend R2: {results['blend']['r2'] * 100:.2f}% | MAE: {results['blend']['mae']:.2f}")
        print(f"ROI Shift: {results['roi']['shift']:+.2f} units (Noise floor: {results['noise_floor']['mean']:+.2f})")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
