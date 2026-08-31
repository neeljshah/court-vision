"""Build deterministic footage-cycle queues for supported sports."""

import argparse
import json
from pathlib import Path


FORMAT = "bv*[height>=1080][vcodec^=avc1]+ba/b[height<=720]"

QUEUES = {
    "tennis": (
        "tennis",
        "LGVOJA-VSRo,awpU69Jy-CQ,inlj61TsIRw,VoqmR5b5zB0,ckbX699wngs,"
        "qorFNY2lSN8,I2napxp1ym0,wicRKbd6B8w,XWwnQjnZCLU,wZJRZhaGrdo",
    ),
    "wnba": (
        "wnba",
        "1zPhldjbJnU,3HzlOdI93FA,ySBeFAmTNcc,bkyUjVLU-LY,YqPCZWAfX_U,"
        "OCyYXq4nEK0,a2pEHm9YzFo,6UIwdBefryw,dUgtHnazuXE,HKrKBqII7vg",
    ),
    "npb": (
        "baseball",
        "i_cK9Bih6iU,ti6ftAkww3g,JBt4qlGQ_HI,1-9AK2j9QIg,Ge_OGPlFGIU,"
        "_Q5kIp3yTPA,9_0g8xnopB8,7karndqBELk,9s9GDqtZWVw,2YNBP_OPafo",
    ),
    "kbo": (
        "baseball",
        "ChxXA-7uyHk,cMK6Y-nMqvo,8Fvt9V55iIk,DgpmHC-MMyM,RtaI_ibDOuE,"
        "JKOftiA4zBA,ja-qoWCMQIA,LaCm6zld944,zRjrI-bkHLo,tVoYbMrIc94",
    ),
}


def build_queue(name: str, sport: str, video_ids: str) -> list[dict[str, str]]:
    """Return queue entries for one sport."""
    return [
        {
            "sport": sport,
            "game_id": f"{name}_{index:02d}",
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "format": FORMAT,
        }
        for index, video_id in enumerate(video_ids.split(","), 1)
    ]


def main(output_dir: Path | str = Path("data")) -> None:
    """Write all footage queues to output_dir."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for name, (sport, video_ids) in QUEUES.items():
        path = destination / f"footage_queue_{name}.json"
        path.write_text(
            json.dumps(build_queue(name, sport, video_ids), indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    main(parser.parse_args().output_dir)
