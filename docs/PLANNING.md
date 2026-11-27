# Planning a proceedings disc

A conference or company event is delivered as a Blu-ray of the day: 2 to 8
hours of sessions on one disc, a title (or a chapter) per session and a
menu that lists them. Each time, someone has to work out what bit rate fits
the day on a BD-25 or a BD-50 and whether that is still good enough.
`bdmvkit plan` (`bdmvkit.plan.plan_disc`) does that sum and says when it is
not good enough.

## Decision

**Input.** A chapter list: one `H:MM:SS Title` line per session (a YouTube
chapter list; slide-sync-skill's `--chapters-out`), or JSON: a list of
`{title, start, end, floor}` under `sessions`, `chapters` or `segments`,
with the recording's `duration` (a slide-sync timeline's `segments` are
read too, as `Session N`). Each session lasts until the next starts, its
own `end`, or the duration.

**Space.** The disc's capacity less a reserve (3 % by default, `--reserve`)
for the UDF file system, the navigation files and their backups, the menu
clips, and the encoder not landing exactly on its average.

**Rate.** Every title gets the same video bit rate: the space the sound
leaves, shared by time,

    video = (usable x 8 / MUX_OVERHEAD - sound x total seconds) / total seconds

capped at 40 Mbit/s, and at what keeps the transport stream under 48 Mbit/s.
A title may name a floor of its own (a session with video clips needs more
than one of slides); a title whose floor is above the share gets its floor,
and the others share what is left. When the floors cannot all be met,
every title gets the same share and each title below its floor is named,
with how many discs the floors need and where to split the sessions
(in order, a new disc when the next session would not fit at its floor).

**Floor.** 6 Mbit/s for 1080 H.264 by default (`--floor`). It is a
starting point for slides and speakers, not a measured quality threshold;
the caller states it, and every title in the plan carries the floor it was
held to.

**Output.** JSON: per title its session, times, video and sound rates,
floor, `above_floor` and bytes; `disc_titles` (what to give
`Disc.add_title`: a title per session, or one title with a chapter at each
session's start); `menu` (a label from the session title and the action of
its button, `title:N` or `chapter:1:N`); `fits`, `all_above_floor`,
`below_floor`, `discs_needed_at_floor`, `split_at_floor`, `warnings`. The
command exits 1 when a title is below its floor or the plan does not fit.
`encode_clip(..., bitrate=)` encodes a title at its planned average (x264
ABR, peak still 40 Mbit/s) instead of constant quality.

**Not done here.** Cutting the recording into sessions (ffmpeg-skill), the
menu pictures (the caller draws them; oncemore does), and the disc image (udfkit).

## Where the numbers come from

| Number | Value | Source |
|---|---|---|
| Capacity | 25.025 GB a layer, 50.050 GB with two | Blu-ray Disc Association, White Paper Blu-ray Disc Format, 1.C Physical Format Specifications for BD-ROM, 6th edition (October 2010), table 2-1 |
| Logical sector, source packet | 2048 bytes; 192-byte source packets (a 4-byte TP_extra_header and a 188-byte transport packet), aligned units of 3 sectors | Blu-ray Disc Association, White paper Blu-ray Disc Format, 2.B Audio Visual Application Format Specifications for BD-ROM (March 2005), 3.1 |
| Transport stream | at most 48 Mbit/s | the same, 3.1 |
| Video | at most 40 Mbit/s (MPEG-4 AVC HP@4.1 among others) | the same, 3.3, figure 3-3 |
| Mux overhead | 1.08 (size of the clip / (video + sound bits / 8)) | measured, below |
| Titles, chapter marks | 999 each, warned about, not refused | not in the public white papers; see below |

**Mux overhead, measured.** A 60 s 1080p 23.976 clip from
`encode_clip(..., bitrate=)` with AC-3 at 192 kbit/s (x264 medium):

| Target video rate | Video stream | Clip | Clip / (video + sound) |
|---|---|---|---|
| 3 Mbit/s | | 25 546 752 bytes | 1.066 (with the encoder's deviation) |
| 8 Mbit/s | 8.02 Mbit/s, 60 215 353 bytes | 64 776 192 bytes | 1.051 (to the measured streams) |

A source packet carries at most 184 bytes of a stream in 192 (1.0435); PES
headers, PAT/PMT/PCR and padding add the rest. 1.08 keeps a margin over
both measurements; `tests/test_plan.py` encodes a clip at a planned rate and
checks it is no bigger than the plan says.

**Counts.** The number of titles in `index.bdmv` and of chapter marks in a
playlist is limited by the BD-ROM specification (Part 3), which is
licensed; the public white papers above do not state the limits. The
planner warns above 999 titles or 999 chapters, the figure authoring tools
commonly allow; a day of sessions is far below either. This is not
verified against the specification.

## Alternatives considered

* **Rate by content** (slides less, video more, measured from the
  recording). Left to the caller through per-session floors: measuring
  content means decoding the recording, which this library does not do.
* **Two-pass encoding for exact sizes.** The reserve covers single-pass ABR;
  a caller who needs the last percent can encode in two passes with the
  planned rate.
* **Splitting automatically onto several discs.** The plan says how many
  discs and where to split; building each disc is a separate
  `bdmvkit build`, so the caller decides.
