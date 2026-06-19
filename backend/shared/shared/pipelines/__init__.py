"""Trivial pipelines (``echo`` / ``ping``) shared by api's mock-worker and service.

These live in ``shared`` — not ``service`` — because ``api`` cannot import ``service``
(only ``shared`` is an installed workspace package), and api's in-process mock-worker
needs to call the same ``process`` functions the real ``service`` runs. They are
dependency-light (shared schemas only); heavy pipelines (e.g. stack analysis, issue-018)
live in ``service`` and are registered there.
"""
