"""
BTCU Harness - Storage Layer

MongoDB is the primary store. An in-memory fallback keeps the harness
fully operational when MongoDB is not available.
"""

from btcu_harness.storage.mongo_client import MongoStore

__all__ = ["MongoStore"]
