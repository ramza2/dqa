"""Candidate Schema Inspector contract only. No runtime wiring or authorization.

Metadata inspection must be invoked by a future admin-only service using a
separately restricted Oracle metadata account. Do not import an Inspector into
query execution, MCP handlers or production Connection Profile selection.
"""
