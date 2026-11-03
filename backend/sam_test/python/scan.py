# backend/sam_test/python/scan.py
import argparse
import asyncio
import json
from pathlib import Path

from measure import scan_door


def main():
    parser = argparse.ArgumentParser(description="Measure door clear width using paper calibration.")
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(scan_door(args.image)), indent=2))


if __name__ == "__main__":
    main()