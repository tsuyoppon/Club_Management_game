from typing import List, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models import Match, MatchStatus, Fixture, Season, SeasonFinalStanding

class StandingsCalculator:
    def __init__(self, session: Session, season_id: UUID):
        self.session = session
        self.season_id = season_id

    def calculate(self, up_to_month: int = None) -> List[Dict[str, Any]]:
        # 0. Check if season is finalized
        # If up_to_month is specified, we should ignore finalized state and recalculate?
        # Or if finalized, and up_to_month covers all, return finalized?
        # Safer to recalculate if up_to_month is specified.
        season = self.session.query(Season).filter(Season.id == self.season_id).first()
        if season and season.is_finalized and up_to_month is None:
            return self._get_finalized_standings()

        # 1. Fetch all completed matches for the season
        query = self.session.query(Match).join(Fixture).filter(
            Fixture.season_id == self.season_id,
            Match.status == MatchStatus.played
        )
        
        if up_to_month is not None:
            query = query.filter(Fixture.match_month_index <= up_to_month)
            
        matches = query.all()

        # 2. Aggregate stats
        stats: Dict[UUID, Dict[str, Any]] = {}

        def ensure_club(c_id: UUID, c_name: str):
            if c_id not in stats:
                stats[c_id] = {
                    "club_id": c_id,
                    "club_name": c_name,
                    "played": 0,
                    "won": 0,
                    "drawn": 0,
                    "lost": 0,
                    "gf": 0,
                    "ga": 0,
                    "gd": 0,
                    "points": 0
                }

        for m in matches:
            # Access clubs via fixture
            home_id = m.fixture.home_club_id
            away_id = m.fixture.away_club_id
            home_name = m.fixture.home_club.name
            away_name = m.fixture.away_club.name
            
            ensure_club(home_id, home_name)
            ensure_club(away_id, away_name)

            h = stats[home_id]
            a = stats[away_id]

            h["played"] += 1
            a["played"] += 1

            h["gf"] += m.home_goals
            h["ga"] += m.away_goals
            a["gf"] += m.away_goals
            a["ga"] += m.home_goals

            h["gd"] = h["gf"] - h["ga"]
            a["gd"] = a["gf"] - a["ga"]

            if m.home_goals > m.away_goals:
                h["won"] += 1
                h["points"] += 3
                a["lost"] += 1
            elif m.home_goals < m.away_goals:
                a["won"] += 1
                a["points"] += 3
                h["lost"] += 1
            else:
                h["drawn"] += 1
                h["points"] += 1
                a["drawn"] += 1
                a["points"] += 1

        standings_list = list(stats.values())

        # 3. Sort
        # Primary: Points, GD, GF
        standings_list.sort(key=lambda x: (x['points'], x['gd'], x['gf']), reverse=True)

        # 4. Resolve Ties (H2H)
        i = 0
        while i < len(standings_list):
            j = i + 1
            while j < len(standings_list):
                if (standings_list[i]['points'] == standings_list[j]['points'] and
                    standings_list[i]['gd'] == standings_list[j]['gd'] and
                    standings_list[i]['gf'] == standings_list[j]['gf']):
                    j += 1
                else:
                    break
            
            if j > i + 1:
                tied_group = standings_list[i:j]
                self._resolve_h2h(tied_group, matches)
                standings_list[i:j] = tied_group
            
            i = j

        # 4.5 PR8: Apply point penalties (bankruptcy deductions)
        from app.services.bankruptcy import get_point_penalty_for_club
        for row in standings_list:
            penalty = get_point_penalty_for_club(self.session, row["club_id"], self.season_id)
            if penalty != 0:
                row["penalty"] = penalty
                row["points_before_penalty"] = row["points"]
                row["points"] = max(0, row["points"] + penalty)  # 0以上にクリップ
            else:
                row["penalty"] = 0
        
        # 4.6 Re-sort after applying penalties
        standings_list.sort(key=lambda x: (x['points'], x['gd'], x['gf']), reverse=True)

        # 5. Assign Ranks
        for idx, row in enumerate(standings_list):
            row['rank'] = idx + 1

        return standings_list

    def _get_finalized_standings(self) -> List[Dict[str, Any]]:
        final_standings = self.session.query(SeasonFinalStanding).filter(
            SeasonFinalStanding.season_id == self.season_id
        ).order_by(SeasonFinalStanding.rank).all()

        return [
            {
                "club_id": fs.club_id,
                "club_name": fs.club.name,
                "rank": fs.rank,
                "points": fs.points,
                "gd": fs.gd,
                "gf": fs.gf,
                "ga": fs.ga,
                "won": fs.won,
                "drawn": fs.drawn,
                "lost": fs.lost,
                "played": fs.played
            }
            for fs in final_standings
        ]

    def _resolve_h2h(self, group: List[Dict[str, Any]], all_matches: List[Match]):
        group_ids = set(x['club_id'] for x in group)
        
        relevant_matches = [
            m for m in all_matches 
            if m.fixture.home_club_id in group_ids and m.fixture.away_club_id in group_ids
        ]

        mini_stats = {cid: {'points': 0, 'gd': 0, 'gf': 0} for cid in group_ids}

        for m in relevant_matches:
            h_id = m.fixture.home_club_id
            a_id = m.fixture.away_club_id
            
            mini_stats[h_id]['gf'] += m.home_goals
            mini_stats[h_id]['gd'] += (m.home_goals - m.away_goals)
            mini_stats[a_id]['gf'] += m.away_goals
            mini_stats[a_id]['gd'] += (m.away_goals - m.home_goals)

            if m.home_goals > m.away_goals:
                mini_stats[h_id]['points'] += 3
            elif m.away_goals > m.home_goals:
                mini_stats[a_id]['points'] += 3
            else:
                mini_stats[h_id]['points'] += 1
                mini_stats[a_id]['points'] += 1

        # Sort by name ascending first (as secondary tie breaker for H2H)
        group.sort(key=lambda x: x['club_name'])
        
        # Sort by H2H stats descending
        group.sort(key=lambda x: (
            mini_stats[x['club_id']]['points'],
            mini_stats[x['club_id']]['gd'],
            mini_stats[x['club_id']]['gf']
        ), reverse=True)

    def calculate_with_may_extras(self) -> List[Dict[str, Any]]:
        """
        PR9: 5月用拡張順位表
        
        v1Spec Section 13.2:
        - 1位「優勝」、2位「準優勝」を横に表示
        - 各クラブの平均入場者数（ホームゲーム平均）を順位表に追加
        
        既存のcalculate()を拡張（破壊的変更なし）
        """
        standings = self.calculate()
        
        for entry in standings:
            # 優勝・準優勝ラベル追加
            if entry['rank'] == 1:
                entry['title'] = '優勝'
            elif entry['rank'] == 2:
                entry['title'] = '準優勝'
            else:
                entry['title'] = None
            
            # ホームゲーム平均入場者数追加
            entry['avg_home_attendance'] = self._calculate_avg_home_attendance(
                entry['club_id']
            )
        
        return standings

    def _calculate_avg_home_attendance(self, club_id: UUID) -> int:
        """
        シーズン内のホームゲーム平均入場者数を計算
        """
        fixtures = self.session.query(Fixture).filter(
            Fixture.season_id == self.season_id,
            Fixture.home_club_id == club_id,
            Fixture.home_attendance != None,
        ).all()
        
        if not fixtures:
            return 0
        
        total = sum(f.home_attendance or 0 for f in fixtures)
        return total // len(fixtures) if fixtures else 0

