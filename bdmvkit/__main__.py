"""Command line:

    bdmvkit encode SOURCE CLIP.m2ts [--fps 24000/1001] [--chapters 0,60,120] [--fast]
    bdmvkit build DISC.json OUT_DIR
    bdmvkit plan CHAPTERS [--disc bd25|bd50] [--mode titles|chapters] [--floor 6M]
                 [--audio 192k] [--duration H:MM:SS] [--reserve 0.03]
    bdmvkit contract [--json]

DISC.json: {"titles": [{"clip": "a.m2ts", "fps": "24000/1001",
"chapters": [0, 60], "audio": [["ac3", 2, "en"]], "subtitles": ["ja"],
"end": "menu:main"}], "menus": [{"id": "main", "background": "menu.png",
"buttons": [{"id": "play", "x": 160, "y": 700, "selected": "play.png",
"action": "title:1"}]}], "play_all": true}; paths are relative to the JSON
file. A button may also have "activated" and "normal" pictures, "nav"
({"up": id, ...}), "auto", "audio", "subtitle" and "override"; a menu
"default" (a button id), "fps", "loop", "end", "seconds", "prohibit",
"music" (a sound file) and "loop_point" (its "background" may be a video); a
title "default_audio", "default_subtitle", "prohibit" and "popup" ({"buttons":
[...], "default"}: its pop-up menu, buttons as a menu's). The disc may have
"playlists" ([{"id", "items": [n or [n, first, last]], "order", "end"}]),
"first_play" and "title_key".

CHAPTERS: "H:MM:SS Title" lines, one per session, or JSON ({"sessions":
[{"title", "start", "end", "floor"}], "duration"}); plan prints the plan as
JSON (plan.plan_disc) and exits 1 when a title is below its floor.
"""

import argparse
import json
import os
import sys

from . import __version__
from .contract import contract
from .disc import Disc, MenuButton
from .encode import encode_clip
from .errors import BdmvError
from .plan import plan_disc, read_chapters


def _fps(text):
    num, _, den = str(text).partition("/")
    return int(num), int(den or 1)


def _times(text):
    return [float(t) for t in text.split(",") if t.strip()] if text else [0.0]


def main(argv=None):
    p = argparse.ArgumentParser(prog="bdmvkit", description="Blu-ray (BDMV) authoring.")
    p.add_argument("--version", action="version", version=f"bdmvkit {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("encode", help="encode a video into a Blu-ray clip (ffmpeg + x264)")
    s.add_argument("source")
    s.add_argument("clip", help="the .m2ts to write")
    s.add_argument("--fps", default="24000/1001", help="24000/1001, 25 or 30000/1001")
    s.add_argument("--chapters", help="chapter starts in seconds, e.g. 0,60,120")
    s.add_argument("--fast", action="store_true", help="quick, lower-quality encoding")
    s = sub.add_parser("build", help="write a BDMV folder from encoded clips and menus")
    s.add_argument("disc", help="the disc description (JSON)")
    s.add_argument("out", help="the folder to write BDMV into")
    s.add_argument("--fast", action="store_true", help="quick encoding of the menus")
    s = sub.add_parser("plan", help="plan the bit rates of a disc of sessions from a chapter list")
    s.add_argument("chapters", help="chapter list: H:MM:SS Title lines, or JSON")
    s.add_argument("--disc", default="bd50", choices=["bd25", "bd50"])
    s.add_argument("--mode", default="titles", choices=["titles", "chapters"],
                   help="each session a title (default) or a chapter of one title")
    s.add_argument("--floor", help="the lowest video bit rate a title may have (default 6M)")
    s.add_argument("--audio", default="192k", help="sound bit rate per title (default 192k)")
    s.add_argument("--duration", help="where the last session ends (H:MM:SS or seconds)")
    s.add_argument("--reserve", type=float, default=0.03, help="share of the disc kept free (0.03)")
    s = sub.add_parser("contract", help="print the machine-readable contract (JSON)")
    s.add_argument("--json", action="store_true", help="accepted; the output is always JSON")
    args = p.parse_args(argv)
    if args.command == "contract":
        print(json.dumps(contract(), indent=2))
        return 0
    try:
        if args.command == "plan":
            from .plan import _seconds
            duration = _seconds(args.duration) if args.duration else None
            plan = plan_disc(read_chapters(args.chapters, duration), disc=args.disc, mode=args.mode,
                             floor=args.floor, audio_bps=args.audio, reserve=args.reserve)
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            for w in plan["warnings"]:
                print(f"bdmvkit: note: {w}", file=sys.stderr)
            return 0 if plan["all_above_floor"] and plan["fits"] else 1
        if args.command == "encode":
            encode_clip(args.source, args.clip, fps=_fps(args.fps),
                        chapters=_times(args.chapters), fast=args.fast)
            print(args.clip)
            return 0
        with open(args.disc, encoding="utf-8") as f:
            spec = json.load(f)
        base = os.path.dirname(os.path.abspath(args.disc))
        disc = Disc(spec.get("first_play"), spec.get("title_key"))
        for t in spec.get("titles", []):
            disc.add_title(os.path.join(base, t["clip"]), fps=_fps(t.get("fps", "24000/1001")),
                           chapters=t.get("chapters", [0]),
                           audio=[tuple(a) for a in t.get("audio", [["ac3", 2, "und"]])],
                           subtitles=t.get("subtitles", []), end=t.get("end"),
                           default_audio=t.get("default_audio"),
                           default_subtitle=t.get("default_subtitle"),
                           prohibit=t.get("prohibit", []))
        for p in spec.get("playlists", []):
            disc.add_playlist(p["id"], p["items"], p.get("order", "sequential"), p.get("end"))

        def file(name):
            return os.path.join(base, name) if name else None

        def buttons(spec_buttons):
            return [MenuButton(b["id"], int(b["x"]), int(b["y"]), file(b["selected"]),
                               file(b.get("activated")), file(b.get("normal")), b.get("action"),
                               dict(b.get("nav", {})), bool(b.get("auto")), b.get("audio"),
                               b.get("subtitle"), b.get("override")) for b in spec_buttons]

        for n, t in enumerate(spec.get("titles", []), 1):
            if t.get("popup"):
                disc.add_popup(n, buttons(t["popup"]["buttons"]), t["popup"].get("default"))
        for m in spec.get("menus", []):
            disc.add_menu(m["id"], file(m["background"]), buttons(m["buttons"]),
                          fps=_fps(m.get("fps", "24000/1001")), default=m.get("default"),
                          loop=m.get("loop"), end=m.get("end"), prohibit=m.get("prohibit", []),
                          seconds=m.get("seconds"), music=file(m.get("music")),
                          loop_point=m.get("loop_point"))
        res = disc.write(args.out, play_all=spec.get("play_all", True), fast=args.fast)
    except (BdmvError, OSError, KeyError, ValueError) as e:
        print(f"bdmvkit: {getattr(e, 'message', e)}", file=sys.stderr)
        return 1
    print(f"{args.out}: {res['titles']} title(s), {res['menus']} menu(s), "
          f"chapters {res['chapters']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
