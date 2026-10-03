from .telemetry_mcp import mcp


def main() -> None:
    """Start the telemetry MCP server over stdio for local agent clients."""
    mcp.run(transport="stdio")
