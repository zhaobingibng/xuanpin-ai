"""XuanPin AI - Application Entry Point."""

import sys

from loguru import logger

from app.config.config import setup_logging
from app.config.settings import get_settings


def main() -> None:
    """Application entry point."""
    # Initialize logging
    setup_logging()

    settings = get_settings()

    logger.info("=" * 60)
    logger.info("Starting {} v{}", settings.app_name, "0.1.0")
    logger.info("Environment: {}", settings.app_env)
    logger.info("Debug mode: {}", settings.app_debug)
    logger.info("=" * 60)

    logger.info("Application started successfully. Ready.")

    # Keep the application running
    try:
        logger.info("Press Ctrl+C to exit.")
        import signal
        signal.pause() if hasattr(signal, "pause") else input()
    except (KeyboardInterrupt, EOFError):
        logger.info("Shutting down gracefully...")
    finally:
        logger.info("Application stopped.")


def start_api(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the FastAPI server via uvicorn."""
    import uvicorn

    setup_logging()
    logger.info("Starting xuanpin-ai API server on {}:{}", host, port)
    uvicorn.run("app.api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "api":
        start_api()
    else:
        main()
