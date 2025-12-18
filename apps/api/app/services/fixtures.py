from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID


@dataclass
class FixtureSpec:
    match_month_index: int
    home_club_id: Optional[UUID]
    away_club_id: Optional[UUID]
    is_bye: bool
    bye_club_id: Optional[UUID]


def _round_robin_pairings(team_ids: List[Optional[UUID]]):
    teams = list(team_ids)
    n = len(teams)
    if n < 2:
        return []

    rounds = []
    fixed = teams[0]
    rest = teams[1:]
    for _ in range(n - 1):
        current = [fixed] + rest
        pairings = []
        for i in range(n // 2):
            pairings.append((current[i], current[-(i + 1)]))
        rest = [current[-1]] + current[1:-1]
        rounds.append(pairings)
    return rounds


def generate_round_robin(club_ids: List[UUID], match_months: int = 10) -> List[FixtureSpec]:
    clubs = list(club_ids)
    if len(clubs) % 2 == 1:
        clubs.append(None)

    base_rounds = _round_robin_pairings(clubs)
    fixtures: List[FixtureSpec] = []
    home_counts = {club_id: 0 for club_id in club_ids}
    cycle = 0
    month_counter = 0

    while month_counter < match_months:
        for round_pairings in base_rounds:
            if month_counter >= match_months:
                break
            month_counter += 1
            swap_cycle = cycle % 2 == 1
            round_fixtures: List[FixtureSpec] = []
            for home_candidate, away_candidate in round_pairings:
                if home_candidate is None or away_candidate is None:
                    bye_team = home_candidate or away_candidate
                    round_fixtures.append(
                        FixtureSpec(
                            match_month_index=month_counter,
                            home_club_id=None,
                            away_club_id=None,
                            is_bye=True,
                            bye_club_id=bye_team,
                        )
                    )
                    continue

                home, away = (home_candidate, away_candidate)
                if swap_cycle:
                    home, away = away, home
                # balance home counts when possible
                if home_counts.get(home, 0) > home_counts.get(away, 0):
                    home, away = away, home

                home_counts[home] = home_counts.get(home, 0) + 1
                round_fixtures.append(
                    FixtureSpec(
                        match_month_index=month_counter,
                        home_club_id=home,
                        away_club_id=away,
                        is_bye=False,
                        bye_club_id=None,
                    )
                )

            fixtures.extend(round_fixtures)
        cycle += 1

    return fixtures

