from __future__ import annotations
import argparse
import logging
from pathlib import Path
from find_my_next_place.config import load_config
from find_my_next_place.scheduler import run


def main():
    parser = argparse.ArgumentParser(prog="find-my-next-place")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--data-dir", default=Path("data"), type=Path)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config(args.config)
    run(cfg, data_dir=args.data_dir, once=args.once)


if __name__ == "__main__":
    main()
