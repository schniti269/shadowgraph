from abc import ABC, abstractmethod


class DimensionProvider(ABC):
    """Each dimension is a pluggable data source for recall().

    query() returns a dict merged into the 'dimensions' key of the recall response.
    Return {} if nothing found — never raise.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def query(self, symbol: str, file_path: str | None, opts: dict) -> dict: ...
