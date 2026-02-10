"""Image preprocessing for tooth-marking classifiers.

Ported from `pretrained_models/demo.ipynb` in
korolainenriikka/fine-tuned-ocr-for-dental-markings.
"""

from __future__ import annotations

from PIL import Image
from torch import Tensor
from torchvision import transforms

# Matches notebook exactly: grayscale with 3 channels, resize 224x224,
# normalize mean=[0.5]*3 std=[0.2]*3.
PREPROCESS = transforms.Compose(
    [
        transforms.Grayscale(3),
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.5, 0.5, 0.5], [0.2, 0.2, 0.2]),
    ]
)


def image_to_batch(image: Image.Image) -> Tensor:
    """Convert a PIL image to a model batch of shape [1, C, H, W]."""
    input_tensor = PREPROCESS(image)
    return input_tensor.unsqueeze(0)
