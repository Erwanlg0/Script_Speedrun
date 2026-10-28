from dataclasses import dataclass


@dataclass(frozen=True)
class Run:
    run_id: str
    game_id: str
    category_id: str
    game_name: str
    category_name: str
    player_name: str
    country: str
    date: str
    video_url: str
    run_link: str
    player_profile_link: str
    duration: float
    rank: int = 1
