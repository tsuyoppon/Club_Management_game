"""Current-season rank scoring shared by attendance and fanbase growth."""

from app.config.constants import CURRENT_RANK_SCORE_NEUTRAL, CURRENT_RANK_SCORE_STEP


def calculate_current_rank_score(rank: int | None, club_count: int) -> float:
    """Return a centered rank score with a fixed gap between adjacent ranks.

    The supported web game size is two to five clubs. Keeping the adjacent-rank
    gap fixed prevents a two-club league from turning first/second place into a
    full 0-to-1 jump. The clip keeps the helper safe if larger leagues are
    introduced later.
    """
    neutral = float(CURRENT_RANK_SCORE_NEUTRAL)
    if rank is None or club_count <= 1:
        return neutral
    if rank < 1 or rank > club_count:
        raise ValueError(f"rank must be between 1 and {club_count}; got {rank}")

    league_midpoint = (club_count + 1) / 2
    score = neutral + float(CURRENT_RANK_SCORE_STEP) * (league_midpoint - rank)
    return max(0.0, min(1.0, score))
