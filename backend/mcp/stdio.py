"""Claude Desktop이 stdio로 붙는 진입점. stdout은 프로토콜이라 로그는 stderr로만 보낸다."""

import logging
import sys

from backend.mcp.server import mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
