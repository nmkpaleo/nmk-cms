"""Tiny local demo for tooth-marking correction package.

Run:
    python -m cms.tooth_markings._demo
"""

from __future__ import annotations

from pprint import pprint

from PIL import Image

from .service import correct_element_text


def main() -> None:
    print("--- Placeholder mode (no token crops) ---")
    result = correct_element_text("Left mandible with m2 and p3 visible")
    pprint(result)

    print("\n--- Inference mode (token crops provided) ---")
    image = Image.new("RGB", (64, 64), color="white")
    try:
        result = correct_element_text(
            "Element m2",
            token_crops=[{"token": "m2", "image": image, "start": 8, "end": 10}],
        )
        pprint(result)
    except Exception as exc:  # noqa: BLE001 - demo helper should show practical setup errors
        print("Inference failed (likely missing real model weights).")
        print(exc)


if __name__ == "__main__":
    main()
