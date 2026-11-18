"""Proceso que consume la cola de trabajos."""

import logging
import signal
import time

from employer_buddy.ai import ClaudeProfileAI
from employer_buddy.config import get_settings
from employer_buddy.conversation import Deps
from employer_buddy.db import get_sessionmaker
from employer_buddy.jobs import process_one
from employer_buddy.whatsapp import WhatsAppClient

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    deps = Deps(whatsapp=WhatsAppClient(settings), ai=ClaudeProfileAI(settings))
    make_session = get_sessionmaker()
    running = True

    def stop(*_: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("Worker iniciado")
    while running:
        with make_session() as session:
            worked = process_one(session, deps)
        if not worked:
            time.sleep(settings.worker_poll_seconds)
    log.info("Worker detenido")


if __name__ == "__main__":
    main()
