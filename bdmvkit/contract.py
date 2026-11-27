"""Machine-readable contract (`bdmvkit contract --json`), in the shape the AI Video
Production OS registry reads (skill_id, version, contract_version, provides,
dependencies, not_provided)."""

from . import __version__

SKILL_ID = "bdmvkit"
CONTRACT_VERSION = "1.0"

TOOLS = [
    {"tool_id": "bdmvkit/encode", "kind": "cli", "writes_media": True, "mutates_input": False,
     "description": "Encode a video into a Blu-ray clip (.m2ts) with ffmpeg + x264",
     "argv": ["encode", "<source>", "<clip.m2ts>", "[--fps 24000/1001|25|30000/1001]", "[--chapters 0,60,120]", "[--fast]"]},
    {"tool_id": "bdmvkit/build", "kind": "cli", "writes_media": True, "mutates_input": False,
     "description": "Write a BDMV folder (playlists, clip information, HDMV navigation, menus, PGS subtitles) from encoded clips and a disc description",
     "argv": ["build", "<disc.json>", "<out_dir>", "[--fast]"]},
    {"tool_id": "bdmvkit/plan", "kind": "cli", "writes_media": False, "mutates_input": False,
     "description": "Plan a proceedings disc from a chapter list: each session a title (or a chapter), the video bit rate of each on a BD-25 or BD-50, whether it is above its quality floor (exit 1 when not), the discs the floors need, and menu entries from the session titles",
     "argv": ["plan", "<chapters>", "[--disc bd25|bd50]", "[--mode titles|chapters]", "[--floor 6M]", "[--audio 192k]", "[--duration H:MM:SS]", "[--reserve 0.03]"]},
]


def contract():
    return {
        "skill_id": SKILL_ID,
        "id": SKILL_ID,
        "version": __version__,
        "contract_version": CONTRACT_VERSION,
        "provides": [
            {"id": "bluray.encode_clip", "lifecycle": "EXPERIMENTAL", "tool_id": "bdmvkit/encode"},
            {"id": "bluray.author", "lifecycle": "EXPERIMENTAL", "tool_id": "bdmvkit/build"},
            {"id": "bluray.plan_disc", "lifecycle": "EXPERIMENTAL", "tool_id": "bdmvkit/plan"},
        ],
        # No Skill dependencies (ffmpeg-skill is not used).
        "dependencies": [],
        "external_tools": [{"id": "ffmpeg", "required": True, "detail": "with libx264; encodes clips and menus"}],
        "not_provided": [
            "disc images (udfkit)",
            "burning a disc",
            "DVD-Video (vtskit, oncemore)",
            "copy protection of any kind",
            "network access of any kind",
        ],
        "tools": TOOLS,
        "python_api": "bdmvkit.Disc",
        "execution": {"canonical_invocation": ["bdmvkit", "contract", "--json"],
                      "network": False, "shell": False},
    }
