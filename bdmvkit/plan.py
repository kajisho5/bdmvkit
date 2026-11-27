"""Bit rates for a proceedings disc: a whole day of sessions (2 to 8 hours)
on one BD-25 or BD-50, each session a title (or a chapter of one title), and
a menu entry for each from its session title.

    plan = plan_disc(read_chapters("sessions.txt", duration=6 * 3600), disc="bd50")
    plan["fits"], [(t["title"], t["video_bps"], t["above_floor"]) for t in plan["titles"]]

The numbers it works from:

* the capacity of a disc: 25.025 GB a layer, 50.050 GB with two (BD-ROM
  physical format white paper, table 2-1), less a reserve (3 % by default)
  for the file system, the navigation files and their backups, the menus,
  and the encoder missing its average;
* the transport stream: a source packet is 192 bytes, a 4-byte header and
  a 188-byte transport packet, which carries at most 184 bytes of a stream
  (BD-ROM AV white paper, 3.1), plus PES headers and tables: MUX_OVERHEAD,
  measured on clips encode.encode_clip makes;
* the limits of a stream: video at most 40 Mbit/s, the transport stream at
  most 48 Mbit/s (BD-ROM AV white paper, 3.1 and 3.3).

Every title gets the same video bit rate: the space the sound leaves,
shared by time. A title can name a quality floor of its own (a session with
video clips in it needs more than one with slides); titles above the
others' share get their floor and the rest share what remains. A title
whose rate is below its floor is reported, with how many discs of that kind
the floors need and where to split the sessions between them.

The planner does not cut or encode anything: it says what to encode
(encode.encode_clip's `bitrate`) and what to build (Disc.add_title's
chapters, menu entries with their actions).
"""

import json
import math
import re

from .errors import BdmvError
from .formats import MAX_VIDEO_BPS, TS_RATE

# bytes a disc holds (BD-ROM physical format white paper, table 2-1)
CAPACITY = {"bd25": 25_025_000_000, "bd50": 50_050_000_000}
RESERVE = 0.03
# size of a clip / (video + sound bits) / 8: 192-byte source packets for
# 184 bytes of stream at most (1.0435), PES headers, PAT/PMT/PCR and the
# encoder's deviation from the average (measured 1.05 to 1.07: docs/PLANNING.md)
MUX_OVERHEAD = 1.08
MAX_TS_BPS = TS_RATE * 8
DEFAULT_FLOOR = {1080: 6_000_000}
# Counts players are known to accept. The public white papers do not give
# the BD-ROM limits on titles and chapter marks; the licensed specification
# does. These are what authoring tools commonly allow; a plan beyond them is
# warned about, not refused.
MAX_TITLES = 999
MAX_CHAPTERS = 999

_TIME = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)\s+[-–—:]?\s*(.*\S)\s*$")


def _seconds(value):
    """Seconds from a number or "H:MM:SS" / "MM:SS" text."""
    if isinstance(value, (int, float)):
        return float(value)
    m = re.fullmatch(r"\s*(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)\s*", str(value))
    if not m:
        try:
            return float(value)
        except (ValueError, TypeError):
            raise BdmvError(f"{value!r} is not a time (seconds, or H:MM:SS)") from None
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def _bps(value):
    """Bits per second from a number or text such as "6M", "192k", "6 Mbit/s"."""
    if isinstance(value, (int, float)):
        return int(value)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kKmM]?)(?:bit/s|bps|b/s)?\s*", str(value))
    if not m:
        raise BdmvError(f"{value!r} is not a bit rate (e.g. 6M, 192k)")
    return int(float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()])


def parse_chapters(text, duration=None):
    """Sessions from a chapter list: either text with one "H:MM:SS Title"
    line per session (a YouTube chapter list, slide-sync-skill's
    --chapters-out), or JSON: a list of {title, start[, end][, floor]}, or an
    object with that list under "sessions", "chapters" or "segments" and
    the recording's "duration". The last session ends at its "end", the
    duration, or `duration`."""
    text = text.lstrip("﻿")
    if text.lstrip().startswith(("[", "{")):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise BdmvError(f"the chapter list is not valid JSON: {e}") from None
        if isinstance(data, dict):
            if duration is None and data.get("duration") is not None:
                duration = _seconds(data["duration"])
            data = next((data[k] for k in ("sessions", "chapters", "segments") if isinstance(data.get(k), list)),
                        None)
        if not isinstance(data, list):
            raise BdmvError("the chapter list has no list of sessions (sessions, chapters or segments)")
        rows = []
        for k, item in enumerate(data, 1):
            if not isinstance(item, dict) or "start" not in item:
                raise BdmvError(f"session {k} of the chapter list has no start")
            rows.append({"title": str(item.get("title") or item.get("name") or f"Session {k}"),
                         "start": _seconds(item["start"]),
                         "end": _seconds(item["end"]) if item.get("end") is not None else None,
                         "floor": _bps(item["floor"]) if item.get("floor") is not None else None})
    else:
        rows = []
        for line in text.splitlines():
            if not line.strip():
                continue
            m = _TIME.match(line)
            if not m:
                raise BdmvError(f"not a chapter line (H:MM:SS Title): {line.strip()!r}")
            start = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            rows.append({"title": m.group(4), "start": start, "end": None, "floor": None})
    if not rows:
        raise BdmvError("the chapter list has no sessions")
    rows.sort(key=lambda r: r["start"])
    for here, nxt in zip(rows, rows[1:]):
        if here["end"] is None:
            here["end"] = nxt["start"]
    if rows[-1]["end"] is None:
        if duration is None:
            raise BdmvError("the last session has no end: give the recording's duration")
        rows[-1]["end"] = float(duration)
    for k, r in enumerate(rows, 1):
        if r["end"] <= r["start"]:
            raise BdmvError(f"session {k} ({r['title']!r}) ends at or before it starts")
    return rows


def read_chapters(path, duration=None):
    with open(path, encoding="utf-8") as f:
        return parse_chapters(f.read(), duration)


def _bytes(video_bps, audio_bps, seconds):
    return (video_bps + audio_bps) * seconds / 8 * MUX_OVERHEAD


def _share(budget_bits, sessions, floors):
    """Video rates: one share for all; a title whose floor is above the
    share gets its floor, and the others share what is left. When the
    floors cannot all be met, every title gets the same share."""
    fixed = set()
    total = sum(s["seconds"] for s in sessions)
    while True:
        free = [k for k in range(len(sessions)) if k not in fixed]
        left = budget_bits - sum(floors[k] * sessions[k]["seconds"] for k in fixed)
        share = left / sum(sessions[k]["seconds"] for k in free)
        over = [k for k in free if floors[k] > share]
        if not over:
            return [floors[k] if k in fixed else share for k in range(len(sessions))]
        if len(over) == len(free):
            return [budget_bits / total] * len(sessions)
        fixed.update(over)


def plan_disc(sessions, disc="bd50", mode="titles", floor=None, audio_bps=192_000, reserve=RESERVE,
              max_video_bps=MAX_VIDEO_BPS):
    """A plan for `sessions` (parse_chapters) on one `disc` ("bd25", "bd50"):
    each session a title (`mode` "titles") or a chapter of one title
    ("chapters"), every title's video bit rate and whether it is above its
    quality floor (`floor`, bit/s, or the session's own), the bytes, the
    menu entries, and warnings."""
    if disc not in CAPACITY:
        raise BdmvError(f"unknown disc {disc!r} (bd25 or bd50)")
    if mode not in ("titles", "chapters"):
        raise BdmvError(f"unknown mode {mode!r} (titles or chapters)")
    if not 0 <= reserve < 0.5:
        raise BdmvError(f"a reserve of {reserve} is outside 0 to 0.5")
    floor = _bps(floor) if floor is not None else DEFAULT_FLOOR[1080]
    audio_bps = _bps(audio_bps)
    sessions = [dict(s, seconds=s["end"] - s["start"]) for s in sessions]
    floors = [s.get("floor") or floor for s in sessions]
    usable = int(CAPACITY[disc] * (1 - reserve))
    total = sum(s["seconds"] for s in sessions)
    peak = min(max_video_bps, MAX_TS_BPS / MUX_OVERHEAD - audio_bps)
    budget = usable * 8 / MUX_OVERHEAD - audio_bps * total
    warnings = []
    if budget <= 0:
        raise BdmvError(f"{total / 3600:.1f} h of sound alone does not fit on a {disc.upper()}")
    if mode == "chapters":
        # one title, one encode: every session at the same rate
        rates = [min(budget / total, peak)] * len(sessions)
    else:
        rates = [min(r, peak) for r in _share(budget, sessions, floors)]

    titles = []
    for k, (s, rate, fl) in enumerate(zip(sessions, rates, floors), 1):
        titles.append({
            "session": k, "title": s["title"], "start": round(s["start"], 3), "end": round(s["end"], 3),
            "seconds": round(s["seconds"], 3), "video_bps": int(rate), "audio_bps": audio_bps,
            "floor_bps": fl, "above_floor": rate >= fl, "bytes": int(_bytes(rate, audio_bps, s["seconds"])),
        })
    below = [t for t in titles if not t["above_floor"]]
    used = sum(t["bytes"] for t in titles)

    if mode == "titles":
        entries = [{"label": t["title"], "action": f"title:{t['session']}"} for t in titles]
        disc_titles = [{"sessions": [t["session"]], "chapters": [0], "video_bps": t["video_bps"]} for t in titles]
        if len(titles) > MAX_TITLES:
            warnings.append(f"{len(titles)} titles: more than the {MAX_TITLES} players are known to accept")
    else:
        first = titles[0]["start"]
        entries = [{"label": t["title"], "action": f"chapter:1:{t['session']}"} for t in titles]
        rate = titles[0]["video_bps"]
        disc_titles = [{"sessions": [t["session"] for t in titles],
                        "chapters": [round(t["start"] - first, 3) for t in titles], "video_bps": rate}]
        if len(titles) > MAX_CHAPTERS:
            warnings.append(f"{len(titles)} chapters: more than the {MAX_CHAPTERS} players are known to accept")

    split = _split(sessions, floors, audio_bps, usable) if below else None
    need = sum(_bytes(fl, audio_bps, s["seconds"]) for s, fl in zip(sessions, floors))
    discs_needed = max(len(split or [()]), math.ceil(need / usable))
    for t in below:
        warnings.append(f"session {t['session']} ({t['title']!r}): {t['video_bps'] / 1e6:.2f} Mbit/s, below its "
                        f"floor of {t['floor_bps'] / 1e6:.2f} Mbit/s")
    if below:
        warnings.append(f"at their floors the sessions need {discs_needed} {disc.upper()} discs")
        for s_, fl in zip(sessions, floors):
            if _bytes(fl, audio_bps, s_["seconds"]) > usable:
                warnings.append(f"{s_['title']!r} alone is larger than a {disc.upper()} at its floor: "
                                "it has to be split into parts")
    return {
        "disc": disc, "mode": mode, "capacity_bytes": CAPACITY[disc], "reserve": reserve,
        "usable_bytes": usable, "planned_bytes": used, "seconds": round(total, 3),
        "fits": used <= usable, "all_above_floor": not below,
        "below_floor": [t["session"] for t in below],
        "titles": titles, "disc_titles": disc_titles, "menu": entries,
        "discs_needed_at_floor": discs_needed,
        "split_at_floor": split,
        "warnings": warnings,
        "assumptions": {"mux_overhead": MUX_OVERHEAD, "max_video_bps": max_video_bps, "max_ts_bps": MAX_TS_BPS},
    }


def _split(sessions, floors, audio_bps, usable):
    """Sessions in order, a new disc whenever the next would not fit at its
    floor: [[1, 2, 3], [4, 5]]."""
    discs, here, size = [], [], 0.0
    for k, (s, fl) in enumerate(zip(sessions, floors), 1):
        b = _bytes(fl, audio_bps, s["seconds"])
        if here and size + b > usable:
            discs.append(here)
            here, size = [], 0.0
        here.append(k)
        size += b
    discs.append(here)
    return discs
