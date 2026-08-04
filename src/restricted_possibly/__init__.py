"""restricted-possibly -- survey tooling for the National Archives Catalog corpus.

`Restricted - Possibly` is a real NARA status value. It means nobody has
looked yet.
"""

__version__ = "0.1.0"

from . import corpus, forensics, inventory, schema

__all__ = ["__version__", "corpus", "forensics", "inventory", "schema"]
