from enum import Enum
from pathlib import Path

from doctr.io import DocumentFile
from doctr.models import ocr_predictor
from pydantic import BaseModel


class BBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class Block(BaseModel):
    text: str
    confidence: float
    bbox: BBox


class Label(BaseModel):
    blocks: list[Block]
    bbox: BBox


class OCRResult(BaseModel):
    labels: list[Label]

    def serialize(self, *, include_bbox: bool = True) -> dict:
        if include_bbox:
            return self.model_dump()
        return self.model_dump(exclude={
            "labels": {"__all__": {"bbox": True, "blocks": {"__all__": {"bbox": True}}}}
        })


class Axis(Enum):
    X = "x"
    Y = "y"


def _geometry_to_bbox(geometry) -> BBox:
    (x1, y1), (x2, y2) = geometry
    return BBox(x1=x1, y1=y1, x2=x2, y2=y2)


def _union_bbox(bboxes: list[BBox]) -> BBox:
    return BBox(
        x1=min(b.x1 for b in bboxes),
        y1=min(b.y1 for b in bboxes),
        x2=max(b.x2 for b in bboxes),
        y2=max(b.y2 for b in bboxes),
    )


def _adaptive_split(
    blocks: list[Block],
    axis: Axis,
    multiplier: float,
    floor: float,
) -> list[list[Block]]:
    """Split blocks where the gap between consecutive items exceeds multiplier × median gap."""
    if not blocks:
        return []
    if len(blocks) == 1:
        return [blocks]

    if axis is Axis.Y:
        sorted_blocks = sorted(blocks, key=lambda b: b.bbox.y1)
        gap_values = [
            max(sorted_blocks[i].bbox.y1 - sorted_blocks[i - 1].bbox.y2, 0.0)
            for i in range(1, len(sorted_blocks))
        ]
    else:
        sorted_blocks = sorted(blocks, key=lambda b: b.bbox.x1)
        gap_values = [
            max(sorted_blocks[i].bbox.x1 - sorted_blocks[i - 1].bbox.x2, 0.0)
            for i in range(1, len(sorted_blocks))
        ]

    median_gap = sorted(gap_values)[len(gap_values) // 2]
    threshold = max(median_gap * multiplier, floor)

    groups: list[list[Block]] = [[sorted_blocks[0]]]
    for i, block in enumerate(sorted_blocks[1:]):
        if gap_values[i] > threshold:
            groups.append([block])
        else:
            groups[-1].append(block)

    return groups


def _cluster_into_labels(
    blocks: list[Block],
    multiplier: float,
    floor: float,
) -> list[list[Block]]:
    labels = []
    for row in _adaptive_split(blocks, Axis.Y, multiplier, floor):
        labels.extend(_adaptive_split(row, Axis.X, multiplier, floor))
    return labels


class OCREngine:
    def __init__(
        self,
        det_arch: str = "db_resnet50",
        reco_arch: str = "crnn_vgg16_bn",
        gap_multiplier: float = 3.0,
        gap_floor: float = 0.002,
    ):
        self.model = ocr_predictor(det_arch=det_arch, reco_arch=reco_arch, pretrained=True)
        self.gap_multiplier = gap_multiplier
        self.gap_floor = gap_floor

    def run(self, image_path: Path) -> OCRResult:
        doc = DocumentFile.from_images(str(image_path))
        result = self.model(doc)

        lines: list[Block] = []
        for page in result.pages:
            for doctr_block in page.blocks:
                for line in doctr_block.lines:
                    if not line.words:
                        continue
                    text = " ".join(w.value for w in line.words)
                    confidence = sum(w.confidence for w in line.words) / len(line.words)
                    lines.append(Block(
                        text=text,
                        confidence=confidence,
                        bbox=_geometry_to_bbox(line.geometry),
                    ))

        label_groups = _cluster_into_labels(lines, self.gap_multiplier, self.gap_floor)
        return OCRResult(
            labels=[
                Label(blocks=group, bbox=_union_bbox([b.bbox for b in group]))
                for group in label_groups
            ]
        )
