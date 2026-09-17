"""Claude Desktop이 stdio로 붙는 진입점. stdout은 프로토콜이라 로그는 stderr로만 보낸다."""

from backend.core.logging import setup
from backend.mcp import server


def main() -> None:
    setup("stdio")
    server.SYNC_VIA_HTTP = True  # 서버 프로세스의 실행 게이트를 타도록 REST에 위임
    server.mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
