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


class TestFrameForensics(unittest.TestCase):
    def test_linear_crossfade_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            vid_path = os.path.join(tmp, "blend.mp4")
            out_dir = os.path.join(tmp, "out")

            f1 = np.full((120, 160, 3), 60, dtype=np.uint8)
            f3 = np.full((120, 160, 3), 200, dtype=np.uint8)
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
            self.assertAlmostEqual(res["blend"]["alpha"], 0.35, delta=0.03)
            self.assertGreater(res["blend"]["r2"], 0.98)
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "report.md")))

    def test_localized_brightening_above_matched_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            vid_path = os.path.join(tmp, "local_event.mp4")
            out_dir = os.path.join(tmp, "out")

            base = np.full((160, 240, 3), 80, dtype=np.uint8)
            # Global +20 exposure lift plus localized +50 spot at center (y=60..100, x=100..140)
            event = np.full((160, 240, 3), 100, dtype=np.uint8)
            event[60:100, 100:140] = 150
            whiteout = np.full((160, 240, 3), 250, dtype=np.uint8)

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
            self.assertGreater(res["roi"]["shift"], 60.0)
            self.assertTrue(len(res["matched_controls"]) > 0)
            self.assertAlmostEqual(res["matched_controls"][0][5], 20.0, delta=2.5)


if __name__ == "__main__":
    unittest.main()
