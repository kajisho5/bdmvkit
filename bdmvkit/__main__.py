"""Command line:

    bdmvkit encode SOURCE CLIP.m2ts [--fps 24000/1001] [--chapters 0,60,120] [--fast]
    bdmvkit build DISC.json OUT_DIR

DISC.json: {"titles": [{"clip": "a.m2ts", "fps": "24000/1001",
"chapters": [0, 60], "audio": [["ac3", 2, "en"]], "subtitles": ["ja"]}],
"play_all": true}; paths are relative to the JSON file.
"""

import argparse
import json
import os
import sys

from . import __version__
from .disc import Disc
from .encode import encode_clip
from .errors import BdmvError


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
    s = sub.add_parser("build", help="write a BDMV folder from encoded clips")
    s.add_argument("disc", help="the disc description (JSON)")
    s.add_argument("out", help="the folder to write BDMV into")
    args = p.parse_args(argv)
    try:
        if args.command == "encode":
            encode_clip(args.source, args.clip, fps=_fps(args.fps),
                        chapters=_times(args.chapters), fast=args.fast)
            print(args.clip)
            return 0
        with open(args.disc, encoding="utf-8") as f:
            spec = json.load(f)
        base = os.path.dirname(os.path.abspath(args.disc))
        disc = Disc()
        for t in spec.get("titles", []):
            disc.add_title(os.path.join(base, t["clip"]), fps=_fps(t.get("fps", "24000/1001")),
                           chapters=t.get("chapters", [0]),
                           audio=[tuple(a) for a in t.get("audio", [["ac3", 2, "und"]])],
                           subtitles=t.get("subtitles", []))
        res = disc.write(args.out, play_all=spec.get("play_all", True))
    except (BdmvError, OSError, KeyError, ValueError) as e:
        print(f"bdmvkit: {getattr(e, 'message', e)}", file=sys.stderr)
        return 1
    print(f"{args.out}: {res['titles']} title(s), chapters {res['chapters']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
