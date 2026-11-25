import os
import tempfile
import unittest
import cv2
import numpy as np
from forensics import analyze_video


def write_synthetic_video(path: str, frames: list, fps: int = 30):
    h, w, _ = frames[0].shape
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    for f in frames:
        writer.write(f)
    writer.release()


def make_patterned_frame(h: int, w: int, base_val: int) -> np.ndarray:
    """Create a deterministic patterned frame so phase correlation has spatial features."""
    y_idx, x_idx = np.indices((h, w))
    # Subtle repeating block/checkerboard texture (+/- 8 around base_val)
    pattern = (((x_idx // 16) + (y_idx // 16)) % 2) * 16 - 8
    frame = np.clip(base_val + pattern, 0, 255).astype(np.float32)
    return np.repeat(frame[:, :, np.newaxis], 3, axis=2).astype(np.uint8)


class TestFrameForensics(unittest.TestCase):
    def test_linear_crossfade_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            vid_path = os.path.join(tmp, "blend.mp4")
            out_dir = os.path.join(tmp, "out")

            f1 = make_patterned_frame(120, 160, 60)
            f3 = make_patterned_frame(120, 160, 200)
            # Exact 35% linear cross-fade
            f2 = np.round(0.35 * f3.astype(float) + 0.65 * f1.astype(float)).astype(np.uint8)

            write_synthetic_video(vid_path, [f1, f1, f2, f3, f3])
            res = analyze_video(
                video_path=vid_path,
                f_prev_idx=2,
                f_target_idx=3,
                f_next_idx=4,
                roi=(40, 80, 60, 100),
                quiet_pair=(1, 2),
                out_dir=out_dir,
                provenance={"source": "synthetic_unit_test"},
            )
            self.assertAlmostEqual(res["blend"]["alpha"], 0.35, delta=0.05)
            self.assertGreater(res["blend"]["r2"], 0.95)
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "report.md")))

    def test_localized_brightening_above_matched_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            vid_path = os.path.join(tmp, "local_event.mp4")
            out_dir = os.path.join(tmp, "out")

            base = make_patterned_frame(160, 240, 80)
            # Global +20 exposure lift plus localized +50 spot at center (y=60..100, x=100..140)
            event = np.clip(base.astype(np.int16) + 20, 0, 255).astype(np.uint8)
            event[60:100, 100:140] = np.clip(event[60:100, 100:140].astype(np.int16) + 50, 0, 255).astype(np.uint8)
            whiteout = make_patterned_frame(160, 240, 250)

            write_synthetic_video(vid_path, [base, base, event, whiteout])
            res = analyze_video(
                video_path=vid_path,
                f_prev_idx=2,
                f_target_idx=3,
                f_next_idx=4,
                roi=(60, 100, 100, 140),
                quiet_pair=(1, 2),
                out_dir=out_dir,
                provenance={},
            )
            self.assertAlmostEqual(res["noise_floor"]["mean"], 0.0, delta=0.5)
            self.assertGreater(res["roi"]["shift"], 40.0)
            self.assertTrue(len(res["matched_controls"]) > 0)
            self.assertAlmostEqual(res["matched_controls"][0][5], 20.0, delta=4.0)


if __name__ == "__main__":
    unittest.main()
