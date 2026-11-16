"""Equipment: what counts as what (models/equipment.py, migration 0079).

A thing can count as several others: a multicooker as a pressure cooker and
as a slow cooker (*Ray, 2026-11-15*). So what an ingredient does with a
parent column, this does with equipment_counts_as. A recipe that needs a
stand mixer is one that needs a mixer, so a thing's recipes are its own and
those of everything that counts as it: its family.
"""

import uuid

from sqlalchemy import select

from openlarder.models import Equipment, EquipmentCountsAs


def family(*equipment_ids: uuid.UUID, name: str = "equipment_family"):
    """The things and everything that counts as them, as a select of IDs:
    asked for a mixer, the stand mixer and the hand mixer too. UNION, not
    UNION ALL, so a loop in what counts as what still ends; nothing the
    site does makes one, but rows written another way could."""
    tree = (
        select(Equipment.id).where(Equipment.id.in_(equipment_ids)).cte(name=name, recursive=True)
    )
    tree = tree.union(
        select(EquipmentCountsAs.equipment_id).where(EquipmentCountsAs.counts_as_id == tree.c.id)
    )
    return select(tree.c.id)
