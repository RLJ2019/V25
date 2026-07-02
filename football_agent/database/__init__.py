"""Optional shadow database infrastructure for V25.1.0.

The database layer is deliberately fail-open during Phase 1: the existing CSV/JSON
and Telegram paths remain authoritative while identical records are mirrored to a
central Supabase/PostgreSQL database for parity validation.
"""

from .connection import DatabaseSettings, SupabaseRestClient
from .repository import DatabaseRepository
from .shadow_writer import ShadowDatabaseWriter

__all__ = [
    "DatabaseSettings",
    "SupabaseRestClient",
    "DatabaseRepository",
    "ShadowDatabaseWriter",
]
