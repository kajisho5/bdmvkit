"""Encoding a video into a Blu-ray clip (.m2ts) with ffmpeg and x264.

The picture is fitted into the 1920 x 1080 frame (letter- or pillarboxed),
encoded as H.264 High at level 4.1 with x264's Blu-ray settings (at most a
second between key frames, key frames at the chapters), and muxed with its
sound and any PGS subtitle streams into a BDAV transport stream with the
PIDs the playlists name. 25 and 29.97 fps become progressive frames in an
interlaced (1080i) stream, as the format has no 1080p at those rates.
"""

import dataclasses
import os
import shutil
import subprocess

from .errors import BdmvError
from .formats import (AUDIO_PID, FORMATS, HEIGHT, IG_PID, MAX_VIDEO_BPS, PG_PID, PMT_PID,
                      VBV_BUFFER, VIDEO_PID, WIDTH)


def video_args(fps, max_bps=MAX_VIDEO_BPS, fast=False, keys=()):
    """x264 options for a Blu-ray video stream at `fps` ((num, den)); `keys`:
    times (s) to make key frames, e.g. the chapters."""
    if fps not in FORMATS:
        raise BdmvError(f"{fps[0]}/{fps[1]} fps has no Blu-ray format "
                        f"(use one of {', '.join(f'{a}/{b}' for a, b in FORMATS)})")
    gop = round(fps[0] / fps[1])            # at most one second between key frames
    x264 = (f"bluray-compat=1:slices=4:aud=1:nal-hrd=vbr:keyint={gop}:min-keyint=1:"
            "force-cfr=1")
    if FORMATS[fps][0] == 4:
        x264 += ":fake-interlaced=1:pic-struct=1"
    args = ["-c:v", "libx264", "-preset", "ultrafast" if fast else "medium",
            "-crf", "24" if fast else "19", "-profile:v", "high", "-level", "4.1",
            "-maxrate", str(max_bps), "-bufsize", str(VBV_BUFFER), "-x264-params", x264,
            "-r", f"{fps[0]}/{fps[1]}", "-pix_fmt", "yuv420p", "-aspect", "16:9",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-forced-idr", "1"]
    if keys:
        args += ["-force_key_frames", ",".join(f"{t:.6f}" for t in sorted(keys))]
    return args


def audio_args(codec="ac3", channels=2, k=0, bitrate=None):
    """Options for audio output stream k: "ac3", "lpcm" (16-bit stereo) or
    "copy" (as it is, e.g. AC-3 or DTS)."""
    if codec == "copy":
        return [f"-c:a:{k}", "copy"]
    if codec == "lpcm":
        return [f"-c:a:{k}", "pcm_bluray", f"-sample_fmt:a:{k}", "s16", f"-ar:a:{k}", "48000",
                f"-ac:a:{k}", "2"]
    if codec != "ac3":
        raise BdmvError(f"unknown audio codec {codec!r} (ac3, lpcm or copy)")
    bitrate = bitrate or (448000 if channels > 2 else 192000)
    return [f"-c:a:{k}", "ac3", f"-b:a:{k}", str(bitrate), f"-ar:a:{k}", "48000",
            f"-ac:a:{k}", str(channels)]


def fit_filter(fps):
    """The picture fitted into the HD frame, square pixels, at `fps`."""
    return (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps[0]}/{fps[1]}")


@dataclasses.dataclass
class AudioTrack:
    """A sound track of a clip: the audio stream `stream` of `source` (None:
    the video file itself), encoded as `codec` ("ac3", "lpcm" or "copy")."""
    source: str = None
    codec: str = "ac3"
    channels: int = 2
    stream: int = 0
    bitrate: int = None


def encode_clip(source, out, fps=(24000, 1001), chapters=(), audio="ac3", channels=2,
                sups=(), max_bps=MAX_VIDEO_BPS, fast=False, ffmpeg=None):
    """Encode `source` (any video ffmpeg reads) into the Blu-ray clip `out`.
    `audio`: a codec ("ac3", "lpcm", "copy") for one track of the first audio
    stream of `source`, or a list of AudioTracks, one track each (track k
    gets the PID AUDIO_PID + k, as Disc.add_title's `audio` numbers them). A
    file without sound gives silence, and encoded sound shorter than the
    picture is made up with silence; the clip ends with the picture.
    `chapters`: times (s) that become key frames, so
    chapter marks land on them. `sups`: PGS streams (.sup, e.g. from
    pgs.write_sup) muxed in as subtitle tracks."""
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        raise BdmvError("encoding needs ffmpeg (with libx264)")
    tracks = [AudioTrack(None, audio, channels)] if isinstance(audio, str) else list(audio)
    if not tracks:
        raise BdmvError("a clip needs at least one audio track")
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", "-i", source]
    inputs = {None: 0}             # file (None: source, "": silence) -> input number

    def input_of(key, args):
        if key not in inputs:
            inputs[key] = cmd.count("-i")
            cmd.extend(args)
        return inputs[key]

    graph, sound, codecs = [f"[0:v:0]{fit_filter(fps)}[v]"], [], []
    for k, tr in enumerate(tracks):
        if not _has_audio(tr.source or source, ffmpeg, tr.stream):
            if tr.codec == "copy":
                raise BdmvError(f"{tr.source or source} has no audio stream {tr.stream} to copy")
            n = input_of("", ["-f", "lavfi", "-i",
                              "anullsrc=channel_layout=stereo:sample_rate=48000"])
            sound += ["-map", f"{n}:a:0"]
        elif tr.codec == "copy":
            sound += ["-map", f"{input_of(tr.source, ['-i', tr.source])}:a:{tr.stream}"]
        else:
            # padded with silence: the picture alone decides where the clip ends
            n = input_of(tr.source, ["-i", tr.source])
            graph.append(f"[{n}:a:{tr.stream}]apad[a{k}]")
            sound += ["-map", f"[a{k}]"]
        codecs += audio_args(tr.codec, tr.channels, k, tr.bitrate)
    first_sup = cmd.count("-i")
    for sup in sups:
        cmd += ["-i", sup]
    cmd += ["-filter_complex", ";".join(graph), "-map", "[v]"] + sound
    for k in range(len(sups)):
        cmd += ["-map", f"{first_sup + k}:s:0"]
    cmd += video_args(fps, max_bps, fast, [t for t in chapters if t > 0]) + codecs
    if sups:
        cmd += ["-c:s", "copy"]
    cmd += ["-streamid", f"0:{VIDEO_PID}"]
    for k in range(len(tracks)):
        cmd += ["-streamid", f"{1 + k}:{AUDIO_PID + k}"]
    for k in range(len(sups)):
        cmd += ["-streamid", f"{1 + len(tracks) + k}:{PG_PID + k}"]
    # the picture's length ends the clip (ffmpeg's -shortest does not stop
    # reliably with padded sound from a filter graph)
    cmd += ["-t", f"{_duration(source, ffmpeg):.3f}", "-f", "mpegts", "-mpegts_m2ts_mode", "1",
            "-mpegts_pmt_start_pid", str(PMT_PID), out]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise BdmvError(f"ffmpeg could not encode {source}: {p.stderr.strip()[-800:]}")
    return out


def _duration(source, ffmpeg):
    """Seconds of the first video stream of `source` (or of the file)."""
    probe = shutil.which("ffprobe") or ffmpeg.replace("ffmpeg", "ffprobe")
    for entries in (["-select_streams", "v:0", "-show_entries", "stream=duration"],
                    ["-show_entries", "format=duration"]):
        p = subprocess.run([probe, "-v", "error"] + entries + ["-of", "csv=p=0", source],
                           capture_output=True, text=True)
        try:
            return float(p.stdout.strip().splitlines()[0])
        except (ValueError, IndexError):
            continue
    raise BdmvError(f"cannot tell how long {source} is")


def _has_audio(source, ffmpeg, stream=0):
    probe = shutil.which("ffprobe") or ffmpeg.replace("ffmpeg", "ffprobe")
    p = subprocess.run([probe, "-v", "error", "-select_streams", f"a:{stream}", "-show_entries",
                        "stream=index", "-of", "csv=p=0", source], capture_output=True, text=True)
    return bool(p.stdout.strip())


def picture(path, size=None, ffmpeg=None):
    """A picture file (PNG, JPEG ...) as (width, height, RGBA bytes), scaled
    to `size` (w, h) when given."""
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        raise BdmvError("reading pictures needs ffmpeg")
    if size is None:
        probe = shutil.which("ffprobe") or ffmpeg.replace("ffmpeg", "ffprobe")
        p = subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", path],
                           capture_output=True, text=True)
        try:
            w, h = (int(v) for v in p.stdout.strip().split(",")[:2])
        except ValueError:
            raise BdmvError(f"cannot read the picture {path}")
    else:
        w, h = size
    p = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-i", path,
                        "-frames:v", "1", "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                        "-pix_fmt", "rgba", "-"], capture_output=True)
    if p.returncode != 0 or len(p.stdout) != w * h * 4:
        why = p.stderr.decode(errors="replace")[-300:]
        raise BdmvError(f"cannot read the picture {path}: {why}")
    return w, h, p.stdout


def encode_menu(background, sup, out, fps=(24000, 1001), seconds=1.0, fast=False, ffmpeg=None,
                motion=False, music=None, keys=()):
    """A menu clip `seconds` long: the picture `background` (fitted into the
    HD frame; with `motion`, a video played from its start), with the IG
    stream `sup` (igs.ig_stream) as its buttons and, with `music`, that
    sound file as its sound track (AC-3, padded with silence to the
    length). A still menu's playlist holds its last picture; one with
    motion or music plays again. `keys`: times (s) that become key frames
    (the loop point, so its mark lands on it)."""
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        raise BdmvError("encoding needs ffmpeg (with libx264)")
    from .igs import patch_ig_stream_type
    num, den = fps
    picture = ["-i", background] if motion else \
        ["-loop", "1", "-framerate", f"{num}/{den}", "-t", f"{seconds:.3f}", "-i", background]
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y"] + picture + \
        ["-f", "sup", "-i", sup] + (["-i", music] if music else [])
    graph = f"[0:v]{fit_filter(fps)},format=yuv420p[v]"
    maps = ["-map", "[v]", "-map", "1:0"]
    ids = ["-streamid", f"0:{VIDEO_PID}", "-streamid", f"1:{IG_PID}"]
    sound = []
    if music:
        graph += ";[2:a:0]apad[a]"
        maps += ["-map", "[a]"]
        ids += ["-streamid", f"2:{AUDIO_PID}"]
        sound = audio_args("ac3", 2)
    keys = [t for t in keys if t and t > 0]
    cmd += ["-filter_complex", graph] + maps + video_args(fps, MAX_VIDEO_BPS, fast, keys) + \
        sound + ["-c:s", "copy"] + ids + \
        ["-t", f"{seconds:.3f}", "-f", "mpegts", "-mpegts_m2ts_mode", "1",
         "-mpegts_pmt_start_pid", str(PMT_PID), out]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise BdmvError(f"ffmpeg could not encode the menu {background}: "
                        f"{p.stderr.strip()[-800:]}")
    patch_ig_stream_type(out)
    return out


def is_video(path, ffmpeg=None):
    """Whether `path` is a video (moving pictures) rather than a picture."""
    ffmpeg = ffmpeg or shutil.which("ffmpeg") or "ffmpeg"
    probe = shutil.which("ffprobe") or ffmpeg.replace("ffmpeg", "ffprobe")
    p = subprocess.run([probe, "-v", "error", "-show_entries", "format=format_name", "-of",
                        "csv=p=0", path], capture_output=True, text=True)
    name = p.stdout.strip()
    if not name:
        raise BdmvError(f"cannot read {path}")
    return not (name == "image2" or name.endswith("_pipe"))


def media_seconds(path, ffmpeg=None):
    """How long a video or sound file lasts (seconds)."""
    ffmpeg = ffmpeg or shutil.which("ffmpeg") or "ffmpeg"
    probe = shutil.which("ffprobe") or ffmpeg.replace("ffmpeg", "ffprobe")
    p = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of",
                        "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        raise BdmvError(f"cannot tell how long {path} is")


def add_ig_stream(clip, sup, out, ffmpeg=None):
    """`clip` with the IG stream `sup` (igs.ig_stream, a pop-up menu) muxed
    in, as `out`: the clip's streams copied with their PIDs and their times,
    the buttons with IG_PID at the clip's first picture, marked Interactive
    Graphics in the PMT. (Segments before the first picture are before the
    play item's start, and players leave them out: so the buttons are timed
    at it, not at the clip's own start, which the sound may begin.)"""
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        raise BdmvError("muxing needs ffmpeg")
    from .igs import patch_ig_stream_type
    probe = shutil.which("ffprobe") or ffmpeg.replace("ffmpeg", "ffprobe")
    p = subprocess.run([probe, "-v", "error", "-show_entries", "stream=index,id", "-of",
                        "csv=p=0", clip], capture_output=True, text=True)
    # (ffprobe lists a stream again under its program: one each, by index)
    streams = dict(line.split(",")[:2] for line in p.stdout.split() if "," in line)
    pids = [int(streams[k], 16) for k in sorted(streams, key=int)]
    if not pids:
        raise BdmvError(f"cannot read the streams of {clip}")
    from .m2ts import scan_m2ts
    start = scan_m2ts(clip).first_pts
    with open(sup, "rb") as f:
        data = bytearray(f.read())
    i = 0
    while i + 13 <= len(data):                   # each segment's PTS and DTS: the start
        data[i + 2:i + 10] = (start & 0xFFFFFFFF).to_bytes(4, "big") * 2
        i += 13 + int.from_bytes(data[i + 11:i + 13], "big")
    timed = out + ".sup"
    with open(timed, "wb") as f:
        f.write(data)
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", "-copyts", "-i", clip,
           "-f", "sup", "-i", timed, "-map", "0", "-map", "1:0", "-c", "copy"]
    for k, pid in enumerate(pids + [IG_PID]):
        cmd += ["-streamid", f"{k}:{pid}"]
    cmd += ["-f", "mpegts", "-mpegts_m2ts_mode", "1", "-mpegts_pmt_start_pid", str(PMT_PID),
            out]
    p = subprocess.run(cmd, capture_output=True, text=True)
    os.remove(timed)
    if p.returncode != 0:
        raise BdmvError(f"ffmpeg could not add the pop-up menu to {clip}: "
                        f"{p.stderr.strip()[-800:]}")
    patch_ig_stream_type(out)
    return out

