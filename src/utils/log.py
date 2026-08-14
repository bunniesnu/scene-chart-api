from sqlmodel import Session

from src.db.tables import ArchiveChangeLog


def update_with_change_log(
    session: Session,
    *,
    entity_type: str,
    entity_id: str,
    obj,
    updates: dict,
    skip_log: bool = False,
) -> dict[str, dict]:
    """
    Update SQLModel object fields and record changed values.

    Args:
        session: SQLModel session
        entity_type: e.g. "artist", "album", "song"
        entity_id: primary key of the entity
        obj: SQLModel instance being updated
        updates: {field_name: new_value}
        skip_log: True when this is a newly created row

    Returns:
        {
            "field": {
                "old": old_value,
                "new": new_value,
            }
        }
    """

    changes = {}

    for field, new_value in updates.items():
        old_value = getattr(obj, field, None)

        if old_value == new_value:
            continue

        changes[field] = {
            "old": old_value,
            "new": new_value,
        }

        if not skip_log:
            session.add(
                ArchiveChangeLog(
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    field_name=field,
                    old_value=None if old_value is None else str(old_value),
                    new_value=None if new_value is None else str(new_value),
                )
            )

        setattr(obj, field, new_value)

    return changes