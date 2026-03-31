"""PM Data Tools - Project management data interoperability library.

This library provides a canonical data model and conversion utilities for project
management data across multiple platforms and standards, targeting UK Government
NISTA compliance.
"""

__version__ = "0.2.0"

# Import public API
from .exceptions import (
    ExportError,
    ParseError,
    PMDataToolsError,
    UnsupportedFormatError,
    ValidationError,
)
from .exporters import create_exporter
from .parsers import create_parser, detect_format, parse_project

# Models are imported via pm_data_tools.models
# from .models import Project, Task, Resource, Dependency, etc.

__all__ = [
    "__version__",
    # Parser API
    "detect_format",
    "create_parser",
    "parse_project",
    # Exporter API
    "create_exporter",
    # Exceptions
    "PMDataToolsError",
    "ParseError",
    "UnsupportedFormatError",
    "ValidationError",
    "ExportError",
]
