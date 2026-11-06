from __future__ import annotations

import logging
from .queue import dequeue
from .research import run_research

LOG = logging.getLogger("heidi.worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        item = dequeue()
        if not item:
            continue
        try:
            run_research(
                item["job_id"], item["city"], item["country"],
                item["max_companies"], item.get("keywords", []),
                item.get("use_local_model", False),
            )
        except Exception:
            LOG.exception("Research worker failed for job %s", item.get("job_id"))


if __name__ == "__main__":
    main()