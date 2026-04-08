"""Shared enums for land-monitor."""

from __future__ import annotations

from enum import Enum


class UserLotStatus(str, Enum):
    NEW = "NEW"
    REVIEW = "REVIEW"
    PLAN = "PLAN"
    APPLIED = "APPLIED"
    BIDDING = "BIDDING"
    WON = "WON"
    LOST = "LOST"
    SKIPPED = "SKIPPED"
    ARCHIVE = "ARCHIVE"
