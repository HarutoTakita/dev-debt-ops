"""Galaxy personal-KC delivery schemas (issue 032) — snake_case, matching ``personalGalaxySchema``.

Reads issue 029's ``file_kc`` / ``dependencies`` and projects them into the personal galaxy. Plain
``BaseModel`` keeps field names snake_case on the wire. ``WormholeOut.from_`` is aliased to ``from``
(reserved word); FastAPI serializes response models by alias by default, so the wire key is ``from``.
"""

from pydantic import BaseModel, ConfigDict, Field


class FileMasteryOut(BaseModel):
    """One file (star) with the developer's KC + mastery (``fileMasterySchema``)."""

    path: str
    module: str
    kc: float
    mastery: str
    mastered: bool


class WormholeOut(BaseModel):
    """A dependency edge (``wormholeSchema``); ``from`` is reserved so the field is ``from_``."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class StarSystemOut(BaseModel):
    """A module (star system) with its files and aggregate KC (``starSystemSchema``)."""

    module: str
    kc: float
    files: list[FileMasteryOut]


class PersonalGalaxyOut(BaseModel):
    """The personal galaxy payload (``personalGalaxySchema``)."""

    developer: str
    org_kc: float
    observed: bool
    systems: list[StarSystemOut]
    wormholes: list[WormholeOut]
