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
