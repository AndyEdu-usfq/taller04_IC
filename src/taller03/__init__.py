def main() -> None:
    """Start the telemetry MCP server over stdio for local agent clients."""
    from .telemetry_mcp import mcp

    mcp.run(transport="stdio")
