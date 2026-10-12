"""bdmvkit: Blu-ray (BDMV) authoring in pure Python.

* `bdmvkit.Disc`: a BDMV folder from encoded clips (titles, chapters, sound
  and subtitle tracks), playlists, menus (still, or with motion or music)
  and pop-up menus (`MenuButton`).
* `bdmvkit.program` and `bdmvkit.nav`: the model underneath (titles,
  playlists, menu clips, transitions, actions) and its writer,
  `nav.write_program`, with the navigation commands (`nav.Navigation`).
* `bdmvkit.igs`: a menu's buttons as an Interactive Graphics stream.
* `bdmvkit.encode.encode_clip`: a clip encoded for Blu-ray with ffmpeg + x264.
* `bdmvkit.pgs`: PGS subtitle streams (.sup) from pictures.
* The files themselves: `playlist.mpls`, `clip.clpi`, `hdmv.index_bdmv`,
  `hdmv.movie_objects` and the HDMV navigation commands, `m2ts.scan_m2ts`.
"""

from .disc import Disc, MenuButton
from .errors import BdmvError

__version__ = "0.6.0"
__all__ = ["Disc", "MenuButton", "BdmvError"]
