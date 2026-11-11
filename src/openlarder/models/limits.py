"""Daily allowances for things anyone may do signed out: ask for a book,
report a problem (daily.py). In the database, so a deploy or a second app
process doesn't start the day's count again. A caller signed out is a
pseudonym (usage.py), never an address. Yesterday's rows are let go."""

from datetime import date

from sqlalchemy import CheckConstraint, Date, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base


class DailyCount(Base):
    __tablename__ = "daily_counts"
    __table_args__ = (
        CheckConstraint("what <> '' AND caller <> ''", name="names_not_empty"),
        CheckConstraint("n >= 1", name="n_positive"),
    )

    # UTC; first, so letting old days go reads the key.
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    # "request" or "report".
    what: Mapped[str] = mapped_column(Text, primary_key=True)
    # "user:<id>", or "ip:<pseudonym>".
    caller: Mapped[str] = mapped_column(Text, primary_key=True)
    n: Mapped[int] = mapped_column(Integer, nullable=False)
