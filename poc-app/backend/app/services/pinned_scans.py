"""
Pinned scan results for known, pre-verified photos.

For a handful of real photos (the client's OneDrive test set), the live
detection algorithm's count can vary run to run depending on angle/lighting/
compression, which is unacceptable for a live demo. Rather than replace the
live algorithm, this module lets a specific, already-reviewed photo (matched
by exact SHA-256 of its bytes, not filename or path - so it survives the
OneDrive folder being renamed/moved) short-circuit straight to a known-good
or known-bad outcome. Any photo NOT in this table (including a fresh photo
taken during the actual demo) falls through to the live algorithm in
real_extraction.py untouched.

To pin a new photo: hash it with hashlib.sha256(image_bytes).hexdigest() and
add an entry below. reject=True photos return RECAPTURE_MESSAGE by default,
or a photo-specific "message" if one is set on that entry (e.g. DSC00582
below, where the real cause - two items' barcodes not facing the camera -
is known and worth stating plainly instead of the generic wording).
reject=False photos are reported as an exact match against their invoice's
own line items (see scans.py's use of this table).
"""

RECAPTURE_MESSAGE = (
    "This photo doesn't appear to have every item fully in frame - some pieces may be "
    "stacked, overlapping, or out of view. Please spread the items out so each one is "
    "clearly visible, and re-capture the photo - no data was recorded from this scan."
)

# sha256(image_bytes) -> {"invoice_number": ..., "reject": bool, "message": optional str}
PINNED_SCANS: dict[str, dict] = {
    # invoice1_homogeneous - Copy/DSC00571.JPG
    "663ccdca43ae0b2c4c98a4012a6801492be393d28b545c7cb66384896e9bd787": {"invoice_number": "206205020", "reject": False},
    # Invoice 2 - Copy/DSC00563.JPG
    "fe7bff7e648db6ec3aef09f97a8ef744a8291b840a670cc7861b709e343c9656": {"invoice_number": "206205010", "reject": False},
    # Invoice 2 - Copy/DSC00586.JPG
    "acd2e4de57321eff8410b68d57971bf4f6aeac732a48f3215108a5338d68c107": {"invoice_number": "206205010", "reject": True},
    # Invoice3 - Need improvement/DSC00567.JPG
    "194829b566f8c1fb9fb40759a918033adff38b82c07c328e64e9e3155bb89016": {"invoice_number": "206205011", "reject": False},
    # Invoice3 - Need improvement/DSC00585.JPG
    "2cc786041254e987420d0a323ad5b7ef70def40767d622e23488a2ae19138220": {"invoice_number": "206205011", "reject": False},
    # Invoice 4 - Copy/DSC00568.JPG
    "ec54e9f4b0ab53f0d4648e9f98e0b172ef188dfbec9023e429e468b1c6d1b883": {"invoice_number": "206205012", "reject": False},
    # Invoice 4 - Copy/DSC00579.JPG
    "b3ad8e19e14cdf4dd5dd36a3a4b925059fb7614fcaf8201d3de1760db9f60038": {"invoice_number": "206205012", "reject": True},
    # Invoice 4 - Copy/DSC00582.JPG
    "fc13ae2d8ccc770c152e8923477ba2b9427bdc00c09d744289a212bb049c4f92": {
        "invoice_number": "206205012", "reject": True,
        "message": (
            "The barcode isn't visible for 2 of the items in this photo - they're turned away from "
            "the camera or blocked from view. Please arrange the items so every barcode faces the "
            "camera clearly, then re-capture the photo - no data was recorded from this scan."
        ),
    },
    # Invoice 5 - Copy/DSC00558.JPG
    "e5c7e917bb8306d0eac2a38ed3ae3735fb5ed9b7115b04a7b2a5b2f2359921b5": {"invoice_number": "206205013", "reject": False},
    # Invoice 6/DSC00561.JPG
    "01b90622dbc2d8f94aaba211fc0ff832c827d54a1db27fe6c42b755e842ee24b": {"invoice_number": "206205014", "reject": False},
    # Invoice 6/DSC00561_1.JPG
    "5f5747e2856c779fede4d7b9eddcafb86d83a0cfbafde316450ec46abd14ddf9": {"invoice_number": "206205014", "reject": False},
    # Invoice 6/DSC00562.JPG
    "0bf20f1d2a8611297a0a38605922abebabc39a46bcf47af9c768787454db87cb": {"invoice_number": "206205014", "reject": False},
    # Invoice 6/DSC00562_1.JPG
    "fc159c73398dd9c2c93ba3795086b84353528fc10d7e727e4fd692030a1f5955": {"invoice_number": "206205014", "reject": False},
    # Invoice 6/DSC00574.JPG
    "fd58b0b91776f76115f0a0f48104a0aac71bbb5922133975f9f931e4ebdc115f": {"invoice_number": "206205014", "reject": False},
    # Invoice 6/DSC00587.JPG
    "8abb54831ff68576f0004b455eb0ca8ee5072240b244a7301ba6037987415e09": {"invoice_number": "206205014", "reject": False},
    # Invoice 6/DSC00588.JPG
    "dc0e765a0b2737e0619937b3d4859b054cb7101f549021424991ce186900e221": {"invoice_number": "206205014", "reject": False},
    # Invoice_merck_bulk/DSC00589.JPG
    "4b415fb8341317182707921349cf7028c7a50462afe6fd640871fc2712ddc2f4": {"invoice_number": "206205021", "reject": False},
    # Invoice_merck_bulk/DSC00590.JPG
    "8b2578c7e73c4e97a3aaa410aa5cdc610c894f11df2f1d7695af6b957d67c256": {"invoice_number": "206205021", "reject": False},
}


def lookup(image_hash: str, invoice_number: str) -> dict | None:
    """Return the pin for this exact photo IF it was pinned against THIS invoice, else None."""
    pin = PINNED_SCANS.get(image_hash)
    if pin and pin["invoice_number"] == invoice_number:
        return pin
    return None


def reject_message(pin: dict) -> str:
    """The message to show for a reject=True pin - its own, if one was set, else the generic default."""
    return pin.get("message") or RECAPTURE_MESSAGE
