"""Numbers of the BD-ROM format bdmvkit writes: stream PIDs, coding types,
video format and frame rate codes, languages."""

VERSION = b"0200"              # of the navigation files
WIDTH, HEIGHT = 1920, 1080

MAX_VIDEO_BPS = 40_000_000     # primary video limit
VBV_BUFFER = 30_000_000        # coded picture buffer at level 4.1
TS_RATE = 48_000_000 // 8      # ts_recording_rate: the 48 Mbit/s maximum, in bytes/s

VIDEO_PID = 0x1011
AUDIO_PID = 0x1100             # + track number
PG_PID = 0x1200                # + subtitle track number
IG_PID = 0x1400                # a menu's buttons (Interactive Graphics)
PMT_PID = 0x0100

# frame rate -> (video_format, frame_rate) codes; 25 and 29.97 fps are coded
# as progressive frames in an interlaced (1080i) stream, as the format has
# no 1080p at those rates
FORMATS = {
    (24000, 1001): (6, 1),     # 1080p 23.976
    (25, 1): (4, 3),           # 1080i 25
    (30000, 1001): (4, 4),     # 1080i 29.97
}
# 720p: 1280 x 720 progressive. 50 and 59.94 frames a second stay as they
# are, so 25 and 29.97 fps pictures go on it at twice their rate (disc_rate).
# The codes are libbluray's bd_video_format_e / bd_video_rate_e (720P = 5;
# 23.976 = 1, 50 = 6, 59.94 = 7)
FORMATS_720 = {
    (24000, 1001): (5, 1),     # 720p 23.976
    (50, 1): (5, 6),           # 720p 50
    (60000, 1001): (5, 7),     # 720p 59.94
}
FRAMES = {"1080": (WIDTH, HEIGHT), "720": (1280, 720)}


def disc_rate(fps, video="1080"):
    """The rate a picture at `fps` goes on the disc at: on a 720p disc, 25
    and 29.97 become 50 and 59.94 progressive."""
    if video == "720" and fps in ((25, 1), (30000, 1001)):
        return (2 * fps[0], fps[1])
    return fps


def video_codes(fps, video="1080"):
    """(video_format, frame_rate) codes of pictures at `fps` on a `video`
    ("1080" or "720") disc, or None when it has no such format."""
    return (FORMATS_720 if video == "720" else FORMATS).get(disc_rate(fps, video))


CODING_H264, CODING_LPCM, CODING_AC3, CODING_DTS = 0x1B, 0x80, 0x81, 0x82
CODING_PG, CODING_IG = 0x90, 0x91

# ISO 639-1 -> ISO 639-2/B (the disc's codes)
LANGS = {
    "ar": "ara", "bg": "bul", "ca": "cat", "cs": "cze", "da": "dan", "de": "ger",
    "el": "gre", "en": "eng", "es": "spa", "et": "est", "fa": "per", "fi": "fin",
    "fr": "fre", "he": "heb", "hi": "hin", "hr": "hrv", "hu": "hun", "id": "ind",
    "is": "ice", "it": "ita", "ja": "jpn", "ko": "kor", "lt": "lit", "lv": "lav",
    "ms": "may", "nl": "dut", "no": "nor", "pl": "pol", "pt": "por", "ro": "rum",
    "ru": "rus", "sk": "slo", "sl": "slv", "sr": "srp", "sv": "swe", "th": "tha",
    "tr": "tur", "uk": "ukr", "vi": "vie", "zh": "chi",
}


def lang3(code):
    return LANGS.get((code or "").lower(), "und")


CODECS = {"ac3": CODING_AC3, "lpcm": CODING_LPCM, "dts": CODING_DTS}
