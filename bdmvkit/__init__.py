"""bdmvkit: Blu-ray (BDMV) authoring in pure Python.

* `bdmvkit.Disc`: a BDMV folder from encoded clips (titles, chapters, sound
  and subtitle tracks, played in order).
* `bdmvkit.encode.encode_clip`: a clip encoded for Blu-ray with ffmpeg + x264.
* `bdmvkit.pgs`: PGS subtitle streams (.sup) from pictures.
* The files themselves: `playlist.mpls`, `clip.clpi`, `hdmv.index_bdmv`,
  `hdmv.movie_objects` and the HDMV navigation commands, `m2ts.scan_m2ts`.
"""

from .disc import Disc
from .errors import BdmvError

__version__ = "0.1.0"
__all__ = ["Disc", "BdmvError"]
