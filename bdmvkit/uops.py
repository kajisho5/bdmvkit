"""User operations: remote keys a title or a menu does not allow.

A title or a menu names them in its `prohibit` (for example a notice that
cannot be skipped: ["next", "fast_forward", "menu"]). They become the UO
mask of its playlist (64 bits, BD-ROM UO_mask_table), or of each play item
of a playlist that is made of several titles.
"""

# the names, and the UO_mask_table bits each sets (counted from the most
# significant)
KEYS = {
    "menu": (0, 24),                   # menu call (top menu), pop-up on
    "title": (0,),
    "search": (1, 2, 3),               # title / chapter / time search
    "next": (4,),
    "prev": (5,),
    "stop": (7,),
    "pause": (8,),
    "fast_forward": (11,),
    "rewind": (12,),
    "audio": (21,),
    "subtitle": (26, 27),
}


def mask(names):
    """The UO mask of the keys `names` turns off."""
    out = 0
    for n in names or ():
        for bit in KEYS[n]:
            out |= 1 << (63 - bit)
    return out
