"""Claude Desktop이 stdio로 붙는 진입점. stdout은 프로토콜이라 로그는 stderr로만 보낸다."""

from backend.core.logging import setup
from backend.mcp.server import mcp


def main() -> None:
    setup("stdio")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
