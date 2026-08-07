from sqlmodel import Session

from db.tables import ArchiveChangeLog


def log_change(
    session: Session,
    entity_type: str,
    entity_id: str,
    field_name: str,
    old,
    new,
):
    session.add(
        ArchiveChangeLog(
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            old_value=None if old is None else str(old),
            new_value=None if new is None else str(new),
        )
    )