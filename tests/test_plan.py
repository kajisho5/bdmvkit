"""Proceedings discs: a day of sessions from a chapter list, planned on a
BD-25 or BD-50 with every title's bit rate against its quality floor; and
a clip encoded at the planned rate measured against the plan."""

import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from bdmvkit import BdmvError, plan_disc
from bdmvkit.__main__ import main
from bdmvkit.formats import MAX_VIDEO_BPS
from bdmvkit.plan import CAPACITY, MUX_OVERHEAD, parse_chapters, read_chapters

DATA = os.path.join(os.path.dirname(__file__), "data")
DAY = os.path.join(DATA, "day_6h.txt")
SIX_HOURS = 6 * 3600


def x264():
    if not shutil.which("ffmpeg"):
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return "libx264" in out


class TestDoneWhen(unittest.TestCase):
    def test_six_hours_plan_within_bd50_with_every_title_above_the_floor(self):
        plan = plan_disc(read_chapters(DAY, duration=SIX_HOURS), disc="bd50")
        self.assertTrue(plan["fits"])
        self.assertTrue(plan["all_above_floor"])
        self.assertEqual(plan["below_floor"], [])
        self.assertEqual(len(plan["titles"]), 12)
        self.assertAlmostEqual(plan["seconds"], SIX_HOURS)
        self.assertLessEqual(plan["planned_bytes"], plan["usable_bytes"])
        self.assertLess(plan["usable_bytes"], CAPACITY["bd50"])
        for t in plan["titles"]:
            self.assertEqual(t["floor_bps"], 6_000_000)        # stated per title
            self.assertGreaterEqual(t["video_bps"], t["floor_bps"])
            self.assertLessEqual(t["video_bps"], MAX_VIDEO_BPS)
        self.assertEqual(plan["warnings"], [])

    def test_a_title_below_its_floor_is_reported_by_name(self):
        sessions = read_chapters(DAY, duration=SIX_HOURS)
        sessions[4]["floor"] = 30_000_000          # the panel has video clips
        plan = plan_disc(sessions, disc="bd25", floor="6M")
        self.assertFalse(plan["all_above_floor"])
        self.assertIn(5, plan["below_floor"])
        notes = " ".join(plan["warnings"])
        self.assertIn("session 5 ('Panel: Devices and follow-up')", notes)
        self.assertIn("below its floor of 30.00 Mbit/s", notes)
        self.assertGreaterEqual(plan["discs_needed_at_floor"], 2)
        split = plan["split_at_floor"]
        self.assertEqual(sum(split, []), list(range(1, 13)))

    def test_too_long_for_a_bd25_at_the_floor_reports_every_title_and_the_discs_needed(self):
        sessions = parse_chapters("0:00:00 Day one\n", duration=8 * 3600)
        plan = plan_disc(sessions, disc="bd25", floor="8M")
        self.assertTrue(plan["fits"])
        self.assertEqual(plan["below_floor"], [1])
        self.assertEqual(plan["discs_needed_at_floor"], 2)


class TestShares(unittest.TestCase):
    def test_a_higher_floor_is_met_and_the_rest_share_what_is_left(self):
        sessions = read_chapters(DAY, duration=SIX_HOURS)
        uniform = plan_disc(sessions, disc="bd50")["titles"][0]["video_bps"]
        sessions[2]["floor"] = 25_000_000
        plan = plan_disc(sessions, disc="bd50")
        rates = [t["video_bps"] for t in plan["titles"]]
        self.assertEqual(rates[2], 25_000_000)
        self.assertTrue(all(r < uniform for k, r in enumerate(rates) if k != 2))
        self.assertTrue(plan["all_above_floor"])
        self.assertLessEqual(plan["planned_bytes"], plan["usable_bytes"])

    def test_a_short_disc_is_capped_at_the_video_limit(self):
        plan = plan_disc(parse_chapters("0:00 Talk\n", duration=600), disc="bd50")
        self.assertEqual(plan["titles"][0]["video_bps"], MAX_VIDEO_BPS)

    def test_bytes_follow_the_overhead(self):
        plan = plan_disc(parse_chapters("0:00 Talk\n", duration=3600), disc="bd25", audio_bps="192k")
        t = plan["titles"][0]
        self.assertEqual(t["bytes"], int((t["video_bps"] + 192_000) * 3600 / 8 * MUX_OVERHEAD))

    def test_chapters_mode_is_one_title_with_a_chapter_per_session(self):
        plan = plan_disc(read_chapters(DAY, duration=SIX_HOURS), disc="bd50", mode="chapters")
        self.assertEqual(len(plan["disc_titles"]), 1)
        self.assertEqual(plan["disc_titles"][0]["chapters"][:3], [0, 900, 3900])
        self.assertEqual(plan["menu"][1], {"label": "Keynote: Heart failure today", "action": "chapter:1:2"})

    def test_menu_entries_come_from_the_session_titles(self):
        plan = plan_disc(read_chapters(DAY, duration=SIX_HOURS), disc="bd50")
        self.assertEqual(plan["menu"][0], {"label": "Opening remarks", "action": "title:1"})
        self.assertEqual([m["label"] for m in plan["menu"]][-1], "Closing")


class TestChapterLists(unittest.TestCase):
    def test_json_with_ends_and_floors(self):
        text = json.dumps({"duration": "2:00:00", "sessions": [
            {"title": "基調講演", "start": "0:00", "floor": "8M"},
            {"title": "シンポジウム", "start": 3600, "end": 7000}]}, ensure_ascii=False)
        rows = parse_chapters(text)
        self.assertEqual([r["title"] for r in rows], ["基調講演", "シンポジウム"])
        self.assertEqual(rows[0]["end"], 3600)
        self.assertEqual(rows[0]["floor"], 8_000_000)
        self.assertEqual(rows[1]["end"], 7000)

    def test_timeline_segments_without_titles(self):
        rows = parse_chapters(json.dumps({"segments": [{"start": 0, "end": 60}, {"start": 60, "end": 90}]}))
        self.assertEqual([r["title"] for r in rows], ["Session 1", "Session 2"])

    def test_errors(self):
        with self.assertRaises(BdmvError):
            parse_chapters("0:00 A\n")                       # no end for the last
        with self.assertRaises(BdmvError):
            parse_chapters("no time here\n", duration=10)
        with self.assertRaises(BdmvError):
            parse_chapters("0:00 A\n0:10 B\n", duration=5)   # ends before it starts
        with self.assertRaises(BdmvError):
            plan_disc(parse_chapters("0:00 A\n", duration=60), disc="bd100")
        with self.assertRaises(BdmvError):
            plan_disc(parse_chapters("0:00 A\n", duration=60), floor="fast")


class TestCommandLine(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["plan", *args])
        return code, out.getvalue(), err.getvalue()

    def test_fits(self):
        code, out, err = self.run_cli(DAY, "--disc", "bd50", "--duration", "6:00:00")
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["all_above_floor"])

    def test_below_the_floor_exits_1_with_a_note(self):
        code, out, err = self.run_cli(DAY, "--disc", "bd25", "--duration", "6:00:00", "--floor", "12M")
        self.assertEqual(code, 1)
        self.assertEqual(len(json.loads(out)["below_floor"]), 12)
        self.assertIn("bdmvkit: note: session 1 ('Opening remarks')", err)


@unittest.skipUnless(x264(), "needs ffmpeg with libx264")
class TestMeasured(unittest.TestCase):
    """A clip encoded at a plan's bit rate is no bigger than the plan says."""

    def test_clip_at_the_planned_rate_fits_its_bytes(self):
        from bdmvkit.encode import encode_clip

        seconds = 10
        plan = plan_disc(parse_chapters("0:00 Day\n", duration=SIX_HOURS), disc="bd25")   # about 8 Mbit/s
        rate = plan["titles"][0]["video_bps"]
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src.mp4")
            subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
                            f"testsrc2=size=1280x720:rate=24000/1001:duration={seconds}", "-f", "lavfi",
                            "-i", f"sine=d={seconds}:r=48000", "-shortest", "-c:v", "libx264", "-crf", "12",
                            "-preset", "ultrafast", src], check=True)
            clip = os.path.join(tmp, "talk.m2ts")
            encode_clip(src, clip, bitrate=rate, fast=True)
            size = os.path.getsize(clip)
        planned = (rate + 192_000) * seconds / 8 * MUX_OVERHEAD
        self.assertLessEqual(size, planned * 1.03)
        self.assertGreater(size, planned * 0.5)


if __name__ == "__main__":
    unittest.main()
