"""Accounts: the people who sign in, and their sessions.

Not catalog data, and not open: nothing here is in the ODbL export.

A user is one identity at the broker, keyed by issuer and subject. The broker
links someone's Google, GitHub and email sign-ins into that one identity, so
OpenLarder never sees which provider was used. Keeping the issuer means a move
to another broker (Keycloak is the fallback) gives everyone new subjects
rather than letting one broker's subject collide with another's; it does not
carry accounts across by itself. That move would need a mapping.

No email address is stored. The broker has it, and nothing here sends mail
yet. *Chosen by Claude, 2026-11-06: keep personal data out until a feature
needs it.*

A session stores only the SHA-256 of its token, so a copy of this table does
not let anyone sign in as the people in it. It also keeps the ID token the
broker issued at sign-in, because Authentik will only send someone back
here after signing out if the request carries it as id_token_hint. An ID
token says who someone is to this client; OpenLarder never accepts one as a
way in, so holding it does not let anyone sign in either.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.sql import text

from openlarder.models.base import Base, Timestamps, uuid_pk


class User(Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("issuer", "subject"),
        CheckConstraint("issuer <> ''", name="issuer_not_empty"),
        CheckConstraint("subject <> ''", name="subject_not_empty"),
        CheckConstraint(
            "char_length(display_name) BETWEEN 2 AND 32 AND display_name = btrim(display_name)",
            name="display_name_shape",
        ),
        CheckConstraint("suggested_name <> ''", name="suggested_name_not_empty"),
        # Unique ignoring case, so "Sarah" and "sarah" are one name. The rest
        # of the rules (allowed characters, reserved names) live in names.py.
        Index("uq_users_display_name_lower", func.lower(text("display_name")), unique=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    # Chosen in OpenLarder and public; empty until chosen. See names.py.
    display_name: Mapped[str | None] = mapped_column(Text)
    # The sign-in provider's name, kept only to pre-fill that choice:
    # refreshed at each sign-in until a name is chosen, then cleared.
    suggested_name: Mapped[str | None] = mapped_column(Text)


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        # SHA-256 is 32 bytes. Anything else is a token stored in the clear,
        # or a different hash than the one the lookup computes.
        CheckConstraint("octet_length(token_hash) = 32", name="token_hash_is_sha256"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint("id_token <> ''", name="id_token_not_empty"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Null for sessions started before migration 0007.
    id_token: Mapped[str | None] = mapped_column(Text)
