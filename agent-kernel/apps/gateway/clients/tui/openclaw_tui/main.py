"""OpenClaw TUI - Terminal UI for Agent Kernel Gateway."""

import argparse
import asyncio
import logging
import sys

from openclaw_tui.app import OpenClawApp


def setup_logging(debug: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
        ],
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="OpenClaw Terminal UI - TUI client for Agent Kernel Gateway",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  openclaw                          # Connect to default Gateway (localhost:3000)
  openclaw --url http://gateway:3000  # Connect to custom Gateway
  openclaw --user myuser            # Use custom user ID
  openclaw --debug                  # Enable debug logging
        """,
    )

    parser.add_argument(
        "--url",
        default="http://localhost:3000",
        help="Gateway URL (default: http://localhost:3000)",
    )

    parser.add_argument(
        "--user",
        default="openclaw-user",
        help="User ID (default: openclaw-user)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    setup_logging(args.debug)

    logging.info(f"Starting OpenClaw TUI")
    logging.info(f"Gateway URL: {args.url}")
    logging.info(f"User ID: {args.user}")

    app = OpenClawApp(
        gateway_url=args.url,
        user_id=args.user,
    )

    try:
        app.run()
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        return 130
    except Exception as e:
        logging.exception("Application error")
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
