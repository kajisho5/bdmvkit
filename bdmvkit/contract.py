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
        ],
        # No Skill dependencies (ffmpeg-skill is not used).
        "dependencies": [],
        "external_tools": [{"id": "ffmpeg", "required": True, "detail": "with libx264; encodes clips and menus"}],
        "not_provided": [
            "disc images (udfkit)",
            "burning a disc",
            "DVD-Video (vtskit, oncemore)",
            "AACS or other copy protection",
            "network access of any kind",
        ],
        "tools": TOOLS,
        "python_api": "bdmvkit.Disc",
        "execution": {"canonical_invocation": ["bdmvkit", "contract", "--json"],
                      "network": False, "shell": False},
    }
