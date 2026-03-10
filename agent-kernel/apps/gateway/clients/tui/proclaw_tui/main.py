"""ProClaw TUI - Terminal UI for Agent Kernel Gateway."""

import argparse
import asyncio
import logging
import sys

from proclaw_tui.app import ProClawApp


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
        description="ProClaw Terminal UI - TUI client for Agent Kernel Gateway",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  proclaw                          # Connect to default Gateway (localhost:3000)
  proclaw --url http://gateway:3000  # Connect to custom Gateway
  proclaw --user myuser            # Use custom user ID
  proclaw --debug                  # Enable debug logging
        """,
    )

    parser.add_argument(
        "--url",
        default="http://localhost:3000",
        help="Gateway URL (default: http://localhost:3000)",
    )

    parser.add_argument(
        "--user",
        default="proclaw-user",
        help="User ID (default: proclaw-user)",
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

    logging.info(f"Starting ProClaw TUI")
    logging.info(f"Gateway URL: {args.url}")
    logging.info(f"User ID: {args.user}")

    app = ProClawApp(
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
