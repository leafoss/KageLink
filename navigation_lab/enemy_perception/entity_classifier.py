from __future__ import annotations

from .entity_knowledge import EntityKnowledgeBase
from .models import EntityClassification, EntityRegion


class EntityClassifier:
    def __init__(self, knowledge: EntityKnowledgeBase) -> None:
        self.knowledge = knowledge

    def classify(
        self,
        region: EntityRegion,
        frame_index: int,
    ) -> tuple[list[float], EntityClassification, str | None]:
        feature = self.knowledge.extractor.extract(region.crop, region.mask)
        result = self.knowledge.classify_feature(feature)
        group_id: str | None = None
        if not result.known:
            group_id = self.knowledge.group_unknown(
                feature,
                region.crop,
                frame_index,
            ).id
        return feature, result, group_id
