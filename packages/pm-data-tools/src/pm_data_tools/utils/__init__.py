"""Utility functions and helpers."""

from .dates import (
    add_working_days,
    calculate_working_days,
    duration_to_timedelta,
    format_iso_datetime,
    format_mspdi_duration,
    parse_datetime,
    parse_iso_datetime,
    parse_mspdi_duration,
    timedelta_to_duration,
)
from .identifiers import (
    generate_random_uuid,
    generate_uuid_from_source,
    get_namespace_for_tool,
    is_valid_uuid,
    parse_uuid,
)
from .xml_helpers import (
    create_element,
    get_bool,
    get_float,
    get_int,
    get_text,
    parse_xml_file,
    parse_xml_string,
    strip_namespaces,
    write_xml_file,
    write_xml_string,
)

__all__ = [
    # Date utilities
    "parse_iso_datetime",
    "parse_datetime",
    "parse_mspdi_duration",
    "format_mspdi_duration",
    "duration_to_timedelta",
    "timedelta_to_duration",
    "calculate_working_days",
    "add_working_days",
    "format_iso_datetime",
    # Identifier utilities
    "generate_uuid_from_source",
    "get_namespace_for_tool",
    "generate_random_uuid",
    "parse_uuid",
    "is_valid_uuid",
    # XML utilities
    "parse_xml_file",
    "parse_xml_string",
    "get_text",
    "get_int",
    "get_float",
    "get_bool",
    "create_element",
    "write_xml_file",
    "write_xml_string",
    "strip_namespaces",
]
