'use client';

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { downloadCsv, safeCsvFilenamePart } from './csv';
import type { CsvCell } from './csv';

type Room = {
  id: string;
  game_id: string;
  status: 'lobby' | 'active' | 'completed' | 'archived';
  game_status: 'draft' | 'active' | 'completed' | 'archived';
  completed_at: string | null;
  invite_code: string;
  is_host: boolean;
  self: { user_id: string; display_name: string; club_id: string | null; ready: boolean };
  clubs: Array<{
    id: string;
    name: string;
    short_name: string | null;
    claimed_by: string | null;
    claimed_by_name: string | null;
    ready: boolean;
  }>;
  members: Array<{
    id: string;
    user_id: string;
    display_name: string;
    club_id: string | null;
    ready: boolean;
    is_host: boolean;
  }>;
};

type RecentRoom = {
  room_id: string;
  game_id: string;
  room_name: string;
  game_status: string;
  room_status: string;
  invite_code: string;
  is_host: boolean;
  club_id: string | null;
  club_name: string | null;
  season: { id: string; number: number; year_label: string; status: string } | null;
  turn: PlayState['turn'];
  last_seen_at: string | null;
  completed_at: string | null;
};

type DeletePreview = {
  game_id: string;
  room_name: string;
  invite_code: string;
  game_status: string;
  room_status: string;
  counts: Record<string, number>;
  confirm_options: string[];
};

type PlayState = {
  room: { id: string; invite_code: string; status: string };
  game_id: string;
  game_status: string;
  completion: { eligible: boolean; blockers: string[]; season_id: string | null; turn_id: string | null };
  season: { id: string; number: number; year_label: string; status: string } | null;
  turn: {
    id: string;
    season_id: string;
    season_number: number;
    month_index: number;
    month_name: string;
    state: string;
  } | null;
  self: { user_id: string; display_name: string; club_id: string | null; is_host: boolean };
  clubs: Array<{ id: string; name: string; decision_state: string | null; committed: boolean; acked: boolean }>;
  standings: Array<{
    rank: number;
    club_id: string;
    club_name: string;
    played: number;
    won: number;
    drawn: number;
    lost: number;
    gf: number;
    ga: number;
    gd: number;
    points: number;
  }>;
};

type ResultOverall = {
  club_id: string;
  club_name: string;
  final_sales_amount?: number;
  final_sales_rank?: number;
  final_equity_amount?: number;
  final_equity_rank?: number;
  championship_count?: number;
  runner_up_count?: number;
  average_rank?: number;
  average_home_attendance?: number;
  attendance_rank?: number;
  final_fanbase?: number | null;
  fanbase_rank?: number | null;
  final_followers?: number | null;
  followers_rank?: number | null;
  final_sponsor_count?: number | null;
  sponsor_rank?: number | null;
  next_sponsor_count?: number | null;
};

type ResultSeasonStanding = StandingRow & {
  season_id: string;
  season_number: number;
  year_label: string;
};

type ResultSeasonMetric = {
  season_id: string;
  season_number: number;
  year_label: string;
  rank: number | null;
  points: number | null;
  revenue: number | null;
  expense: number | null;
  net: number | null;
  closing_balance: number | null;
  average_home_attendance: number | null;
  fanbase: number | null;
  followers: number | null;
  sponsor_count: number | null;
  next_sponsor_count: number | null;
  team_power: number | null;
  bankrupt: boolean;
  points_penalty: number;
};

type ResultDecision = {
  season_number: number;
  year_label: string;
  month_index: number;
  month_name: string;
  decision_state: string;
  inputs: Record<string, unknown>;
  committed_by: string | null;
  committed_at: string | null;
  income: number | null;
  expense: number | null;
  closing_balance: number | null;
  rank: number | null;
  points: number | null;
  matches: Array<{
    opponent: string | null;
    home: boolean;
    score_for: number | null;
    score_against: number | null;
  }>;
};

type ResultClubReview = {
  club_id: string;
  club_name: string;
  season_metrics: ResultSeasonMetric[];
  decisions: ResultDecision[];
  highlights: Array<{ category: string; message: string; club_name: string }>;
};

type ResultSummary = {
  schema_version: number;
  game: { id: string; name: string; created_at: string; started_at: string; completed_at: string; seasons_played: number };
  overall_results: ResultOverall[];
  season_standings: ResultSeasonStanding[];
  club_reviews: ResultClubReview[];
  highlights: Array<{ club_id: string; club_name: string; category: string; message: string }>;
  viewer_scope: string;
};

type SeasonOption = {
  id: string;
  game_id: string;
  season_number: number;
  year_label: string;
  status: string;
};

type StandingRow = {
  rank: number;
  club_id: string;
  club_name: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  gf: number;
  ga: number;
  gd: number;
  points: number;
};

type ConsoleData = {
  turn: PlayState['turn'];
  decision: { state: string | null; payload: Record<string, unknown> | null; committed_at: string | null };
  draft: Record<string, unknown> | null;
  available_inputs: Array<{ key: string; label: string }>;
  available_actions: string[];
  finance: {
    balance: number;
    latest_closing_balance: number | null;
    latest_income: number | null;
    latest_expense: number | null;
    report: FinanceReport;
  };
  fanbase: {
    followers: number | null;
    fb_count: number | null;
    comparison: Array<{
      club_id: string;
      club_name: string;
      is_self: boolean;
      followers: number | null;
      fb_count: number | null;
    }>;
  };
  sponsor: {
    count: number;
    confirmed_next: number;
    confirmed_next_new: number;
    confirmed_next_existing: number;
  };
  event_budget: {
    key: string;
    title: string;
    input_label: string;
    saved_amount: number | null;
  } | null;
  academy: { annual_budget: number; next_annual_budget: number | null };
  staff: Array<{
    role: string;
    count: number;
    next_count: number | null;
    hiring_target: number | null;
    input_count: number | null;
  }>;
  fixtures: Array<{
    id: string;
    month_index: number;
    month: string;
    home: boolean;
    opponent: string | null;
    is_bye: boolean;
    status: string;
    score: [number, number] | null;
    score_for_club: [number, number] | null;
    weather: string | null;
    home_attendance: number | null;
    away_attendance: number | null;
    total_attendance: number | null;
  }>;
  standings: PlayState['standings'];
};

type MatchFixture = ConsoleData['fixtures'][number];

type MatchHistoryPayload = {
  seasons: SeasonOption[];
  fixtures: Record<string, MatchFixture[]>;
};

const emptyMatchHistoryPayload: MatchHistoryPayload = { seasons: [], fixtures: {} };

type FinancialSummaryClub = {
  club_id: string;
  club_name: string;
  fiscal_year?: string;
  total_revenue?: number;
  total_expense?: number;
  'total expense'?: number;
  net_income?: number;
  ending_balance?: number;
  Sponsor_revenue?: number;
  ticket_revenue?: number;
  distribution_revenue?: number;
  prize_revenue?: number;
  merchandise_revenue?: number;
  academy_transfer_fee?: number;
  reinforcement_cost?: number;
  match_operation_cost?: number;
  team_operation_cost?: number;
  academy_cost?: number;
  merchandise_cost?: number;
  staff_cost?: number;
  [key: string]: string | number | undefined;
};

type TeamPowerClub = {
  club_id: string;
  club_name: string;
  team_power: number;
  estimated_reinforcement_budget?: number;
  reinforcement_estimate_label?: string;
};

type PublicDisclosure<TClub = FinancialSummaryClub> = {
  id: string;
  season_id: string;
  disclosure_type: string;
  disclosure_month: number;
  disclosed_data: { clubs?: TClub[]; note?: string; disclosure_type?: string; disclosed_at?: string };
  created_at: string;
};

type ConsoleSection = 'Turn' | 'Matches' | 'Table' | 'Finance' | 'Fans' | 'Sponsors' | 'Staff' | 'Team Power' | 'Disclosures';
type FinanceLine = { kind: string; label: string; amount: number };
type FinanceStatement = {
  income: FinanceLine[];
  expenses: FinanceLine[];
  income_total: number;
  expense_total: number;
  net: number;
};
type FinanceReport = {
  period: {
    season_number: number;
    year_label: string | null;
    month_index: number | null;
    month_name: string | null;
  };
  monthly: FinanceStatement;
  cumulative: FinanceStatement;
  opening_balance: number | null;
  closing_balance: number | null;
};

type FinanceLedgerEntry = {
  turn_id: string;
  month_index: number;
  kind: string;
  amount: number;
  meta?: Record<string, unknown> | null;
};

type FinanceMonthBalance = {
  month_index: number;
  closing_balance: number;
};

type FinanceLedgerPayload = {
  ledger: FinanceLedgerEntry[];
  balances: FinanceMonthBalance[];
};

type AnnualFinanceSeason = {
  id: string;
  season_number: number;
  year_label: string | null;
  closing_balance: number;
};

type AnnualFinanceLedgerEntry = {
  season_id: string;
  kind: string;
  amount: number;
};

type AnnualFinanceLedgerPayload = {
  seasons: AnnualFinanceSeason[];
  ledger: AnnualFinanceLedgerEntry[];
};

type FinalStandingsPayload = {
  seasons: SeasonOption[];
  standings: Record<string, StandingRow[]>;
};

const defaultClubs = ['東京ユナイテッド', '大阪イレブン', '福岡アローズ'];
const consoleSections: ConsoleSection[] = ['Turn', 'Matches', 'Table', 'Finance', 'Fans', 'Sponsors', 'Staff', 'Team Power', 'Disclosures'];
const seasonMonthIndexes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
const financeKindOrder = [
  'sponsor_annual',
  'sponsor',
  'ticket_rev',
  'distribution_revenue',
  'prize_revenue',
  'merchandise_rev',
  'academy_transfer_fee',
  'reinforcement_cost',
  'match_operation_cost',
  'team_operation_cost',
  'academy_cost',
  'merchandise_cost',
  'sales_expense',
  'promo_expense',
  'hometown_expense',
  'staff_cost',
  'staff_severance',
  'admin_cost',
  'tax',
];
const financeIncomeKinds = new Set([
  'sponsor_annual',
  'sponsor',
  'ticket_rev',
  'distribution_revenue',
  'prize_revenue',
  'merchandise_rev',
  'academy_transfer_fee',
]);
const moneyKeys = new Set([
  'sales_expense',
  'promo_expense',
  'hometown_expense',
  'next_home_promo',
  'additional_reinforcement',
  'reinforcement_budget',
]);
const resultDecisionLabels: Record<string, string> = {
  sales_expense: '営業費',
  promo_expense: 'プロモーション費',
  hometown_expense: 'ホームタウン活動費',
  next_home_promo: '翌月ホーム向けプロモ',
  sales_allocation_new: '新規スポンサー営業配分',
  additional_reinforcement: '追加強化費',
  reinforcement_budget: '翌シーズン強化費',
  staff_plan: 'スタッフ計画',
  academy_budget: 'アカデミー予算',
};

const completionBlockerLabels: Record<string, string> = {
  game_not_active: 'ゲームが進行中ではありません',
  season_missing: '対象シーズンがありません',
  july_turn_missing: '7月ターンがありません',
  july_not_resolved: '7月の結果が未確定です',
  clubs_not_acknowledged: '全クラブのackが必要です',
  matches_incomplete: '未処理または不整合の試合があります',
};
const integerDigitsPattern = /^\d+$/;
const optionalIntegerDigitsPattern = /^\d*$/;
const thousandsSeparatorPattern = /\B(?=(\d{3})+(?!\d))/g;
const commaPattern = /,/g;

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = typeof payload?.detail === 'string' ? payload.detail : JSON.stringify(payload?.detail || payload || {});
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function amount(value: number | null | undefined) {
  if (value === null || value === undefined) return '-';
  return Math.round(value).toLocaleString('ja-JP');
}

function expenseAmount(value: number | null | undefined) {
  if (value === null || value === undefined) return '-';
  return Math.round(Math.abs(value)).toLocaleString('ja-JP');
}

function csvAmount(value: number | null | undefined) {
  if (value === null || value === undefined) return null;
  return Math.round(value);
}

function count(value: number | null | undefined) {
  if (value === null || value === undefined) return '-';
  return Math.round(value).toLocaleString('ja-JP');
}

function formatIntegerInput(value: string) {
  if (!integerDigitsPattern.test(value)) return value;
  return value.replace(thousandsSeparatorPattern, ',');
}

function FormattedIntegerInput({
  value,
  onValueChange,
}: {
  value: string;
  onValueChange: (value: string) => void;
}) {
  return (
    <input
      inputMode="numeric"
      pattern="[0-9,]*"
      type="text"
      value={formatIntegerInput(value)}
      onChange={(event) => {
        const digits = event.target.value.replace(commaPattern, '');
        if (optionalIntegerDigitsPattern.test(digits)) onValueChange(digits);
      }}
    />
  );
}

function statusText(state: string | null | undefined) {
  if (!state) return '待機';
  if (state === 'collecting') return '入力受付';
  if (state === 'locked') return '締切';
  if (state === 'resolved') return '結果確認';
  return state;
}

function friendlyError(message: string) {
  if (message.includes('Not all decisions committed')) return '未確定のクラブがあります。全クラブが入力を確定してから締切できます。';
  if (message.includes('Not all clubs acknowledged')) return '未ackのクラブがあります。全クラブが結果確認を終えてから次ターンへ進めます。';
  if (message.includes('Host only')) return 'この操作はホストだけが実行できます。';
  if (message.includes('Turn input is closed')) return 'このターンの入力は締め切られています。';
  if (message.includes('Save input before committing')) return '確定前に入力を保存してください。';
  if (message.includes('Inputs not available this turn')) return 'このターンでは入力できない項目が含まれています。画面を更新して再入力してください。';
  if (message.includes('Only a resolved turn can be acknowledged')) return '結果確定前はackできません。ホストのresolveを待ってください。';
  if (message.includes('Only a resolved turn can advance')) return '結果確定前は次ターンへ進めません。先にresolveしてください。';
  if (message.includes('Committed input can only be reopened before lock')) return '入力確定の解除は締切前だけ実行できます。';
  return message;
}

export default function Home() {
  const [room, setRoom] = useState<Room | null>(null);
  const [play, setPlay] = useState<PlayState | null>(null);
  const [consoleData, setConsoleData] = useState<ConsoleData | null>(null);
  const [financialDisclosure, setFinancialDisclosure] = useState<PublicDisclosure<FinancialSummaryClub> | null>(null);
  const [teamPowerDisclosure, setTeamPowerDisclosure] = useState<PublicDisclosure<TeamPowerClub> | null>(null);
  const [recentRooms, setRecentRooms] = useState<RecentRoom[]>([]);
  const [archivedRooms, setArchivedRooms] = useState<RecentRoom[]>([]);
  const [resultSummary, setResultSummary] = useState<ResultSummary | null>(null);
  const [stage, setStage] = useState<'entry' | 'lobby' | 'console' | 'result'>('entry');
  const [displayName, setDisplayName] = useState('');
  const [roomName, setRoomName] = useState('研修リーグ');
  const [inviteCode, setInviteCode] = useState('');
  const [clubNames, setClubNames] = useState(defaultClubs);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [draftDirty, setDraftDirty] = useState(false);
  const [draftState, setDraftState] = useState('未保存');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const restoredTurnId = useRef<string | null>(null);
  const currentGameId = room?.game_id;
  const currentClubId = play?.self.club_id;

  const report = (work: Promise<unknown>) => {
    setError('');
    setBusy(true);
    return work.catch((cause: Error) => setError(friendlyError(cause.message))).finally(() => setBusy(false));
  };

  const loadRoom = useCallback(async (roomId: string) => {
    const nextRoom = await api<Room>(`/api/rooms/${roomId}`);
    setRoom(nextRoom);
    setStage(
      nextRoom.status === 'completed' || (nextRoom.status === 'archived' && nextRoom.completed_at)
        ? 'result'
        : nextRoom.status === 'active'
        ? 'console'
        : 'lobby',
    );
    return nextRoom;
  }, []);

  const loadResultSummary = useCallback(async (gameId: string) => {
    const summary = await api<ResultSummary>(`/api/games/${gameId}/result-summary`);
    setResultSummary(summary);
    return summary;
  }, []);

  const loadRecentRooms = useCallback(async () => {
    const active = await api<{ rooms: RecentRoom[] }>('/api/rooms/recent');
    setRecentRooms(active.rooms);
    try {
      const archived = await api<{ rooms: RecentRoom[] }>('/api/rooms/recent?include_archived=true');
      setArchivedRooms(archived.rooms);
    } catch {
      setArchivedRooms([]);
    }
  }, []);

  const loadFinancialDisclosure = useCallback(async (seasonId: string) => {
    try {
      return await api<PublicDisclosure<FinancialSummaryClub>>(`/api/seasons/${seasonId}/disclosures/financial_summary`);
    } catch {
      return null;
    }
  }, []);

  const loadTeamPowerDisclosure = useCallback(async (seasonId: string) => {
    try {
      return await api<PublicDisclosure<TeamPowerClub>>(`/api/seasons/${seasonId}/team-power`);
    } catch {
      return null;
    }
  }, []);

  const loadPlay = useCallback(async (gameId: string) => {
    const nextPlay = await api<PlayState>(`/api/games/${gameId}/play-state`);
    setPlay(nextPlay);
    const [financial, teamPower, nextConsole] = await Promise.all([
      nextPlay.season ? loadFinancialDisclosure(nextPlay.season.id) : Promise.resolve(null),
      nextPlay.season ? loadTeamPowerDisclosure(nextPlay.season.id) : Promise.resolve(null),
      nextPlay.self.club_id
        ? api<ConsoleData>(`/api/games/${gameId}/clubs/${nextPlay.self.club_id}/turn-console`)
        : Promise.resolve(null),
    ]);
    setFinancialDisclosure(financial);
    setTeamPowerDisclosure(teamPower);
    setConsoleData(nextConsole);
  }, [loadFinancialDisclosure, loadTeamPowerDisclosure]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadRecentRooms().catch(() => undefined);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadRecentRooms]);

  useEffect(() => {
    if (!room || stage !== 'lobby') return undefined;
    const interval = window.setInterval(() => loadRoom(room.id).catch(() => undefined), 3000);
    return () => window.clearInterval(interval);
  }, [loadRoom, room, stage]);

  useEffect(() => {
    if (!room || stage !== 'console') return undefined;
    let cancelled = false;
    window.setTimeout(() => {
      if (!cancelled) {
        loadPlay(room.game_id).catch((cause: Error) => setError(friendlyError(cause.message)));
      }
    }, 0);
    const interval = window.setInterval(() => loadPlay(room.game_id).catch(() => undefined), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [loadPlay, room, stage]);

  useEffect(() => {
    if (!room || stage !== 'result') return undefined;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      loadResultSummary(room.game_id).catch((cause: Error) => {
        if (!cancelled) setError(friendlyError(cause.message));
      });
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [loadResultSummary, room, stage]);

  useEffect(() => {
    if (!consoleData?.turn || restoredTurnId.current === consoleData.turn.id) return;
    const source = consoleData.draft || consoleData.decision.payload || {};
    setFormValues(
      Object.fromEntries(
        consoleData.available_inputs.map(({ key }) => [key, source[key] === undefined ? '' : String(source[key])]),
      ),
    );
    setDraftDirty(false);
    setDraftState(consoleData.draft ? '下書き復元' : '未保存');
    restoredTurnId.current = consoleData.turn.id;
  }, [consoleData]);

  const formPayload = useMemo(() => {
    const payload: Record<string, number> = {};
    for (const [key, raw] of Object.entries(formValues)) {
      if (raw.trim() === '') continue;
      const numeric = Number(raw);
      if (!Number.isNaN(numeric)) payload[key] = numeric;
    }
    return payload;
  }, [formValues]);

  const saveDraft = useCallback(async () => {
    if (!currentGameId || !currentClubId) return;
    setDraftState('保存中');
    await api(`/api/games/${currentGameId}/clubs/${currentClubId}/turn-draft`, {
      method: 'PUT',
      body: JSON.stringify({ payload: formPayload }),
    });
    setDraftDirty(false);
    setDraftState('下書き保存済み');
  }, [currentClubId, currentGameId, formPayload]);

  useEffect(() => {
    if (!draftDirty || stage !== 'console') return undefined;
    const timer = window.setTimeout(
      () => saveDraft().catch((cause: Error) => {
        setDraftState('保存失敗');
        setError(friendlyError(cause.message));
      }),
      700,
    );
    return () => window.clearTimeout(timer);
  }, [draftDirty, saveDraft, stage]);

  async function createRoom(event: FormEvent) {
    event.preventDefault();
    await report(
      api<Room>('/api/rooms', {
        method: 'POST',
        body: JSON.stringify({ display_name: displayName, room_name: roomName, club_names: clubNames }),
      }).then((nextRoom) => {
        setRoom(nextRoom);
        setStage('lobby');
      }),
    );
  }

  async function joinRoom(event: FormEvent) {
    event.preventDefault();
    await report(
      api<Room>(`/api/rooms/${inviteCode.trim().toUpperCase()}/join`, {
        method: 'POST',
        body: JSON.stringify({ display_name: displayName }),
      }).then((nextRoom) => {
        setRoom(nextRoom);
        setStage('lobby');
      }),
    );
  }

  async function refreshRoom(work: Promise<unknown>) {
    await report(work);
    if (room) await loadRoom(room.id);
  }

  async function startRoom() {
    if (!room) return;
    await report(
      api(`/api/rooms/${room.id}/start`, { method: 'POST', body: JSON.stringify({}) }).then(() =>
        loadRoom(room.id),
      ),
    );
  }

  async function commitDecision() {
    if (!room || !play?.self.club_id) return;
    await report(
      saveDraft()
        .then(() => api(`/api/games/${room.game_id}/clubs/${play.self.club_id}/turn-commit`, { method: 'POST' }))
        .then(() => loadPlay(room.game_id)),
    );
  }

  async function hostAction(action: string) {
    if (!room) return;
    await report(
      api(`/api/games/${room.game_id}/host/turn-action`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      }).then(() => loadPlay(room.game_id)),
    );
  }

  async function completeGame() {
    if (!room) return;
    if (!window.confirm('このシーズンでゲームを終了し、結果サマリーを確定します。終了は後から取り消せます。')) return;
    await report(
      api<ResultSummary>(`/api/games/${room.game_id}/complete`, { method: 'POST' }).then(async (summary) => {
        setResultSummary(summary);
        await loadRoom(room.id);
      }),
    );
  }

  async function reopenGame() {
    if (!room) return;
    if (!window.confirm('ゲーム終了を取り消し、7月の結果確認状態へ戻しますか？')) return;
    await report(
      api(`/api/games/${room.game_id}/reopen`, { method: 'POST' }).then(async () => {
        setResultSummary(null);
        await loadRoom(room.id);
      }),
    );
  }

  async function downloadResultExport(format: 'pdf' | 'csv-zip') {
    if (!room) return;
    setError('');
    setBusy(true);
    try {
      const response = await fetch(`/api/games/${room.game_id}/result-summary/exports/${format}`, {
        credentials: 'include',
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const disposition = response.headers.get('Content-Disposition') || '';
      const encodedFilename = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
      const filename = (encodedFilename ? decodeURIComponent(encodedFilename) : null)
        || disposition.match(/filename="([^"]+)"/)?.[1]
        || `${safeCsvFilenamePart(resultSummary?.game.name || 'game')}_result-summary.${format === 'pdf' ? 'pdf' : 'zip'}`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      setError(friendlyError((cause as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function hostUncommit(clubId: string) {
    if (!room) return;
    await report(
      api(`/api/games/${room.game_id}/host/clubs/${clubId}/turn-uncommit`, {
        method: 'POST',
      }).then(() => loadPlay(room.game_id)),
    );
  }

  async function ackTurn() {
    if (!room || !play?.self.club_id) return;
    await report(
      api(`/api/games/${room.game_id}/clubs/${play.self.club_id}/turn-ack`, { method: 'POST' }).then(() =>
        loadPlay(room.game_id),
      ),
    );
  }

  async function saveStaffPlan(role: string, count: number) {
    if (!room || !play?.self.club_id) return;
    await report(
      api(`/api/games/${room.game_id}/clubs/${play.self.club_id}/turn-staff-plan`, {
        method: 'POST',
        body: JSON.stringify({ role, count }),
      }).then(() => loadPlay(room.game_id)),
    );
  }

  async function saveAcademyBudget(annualBudget: number) {
    if (!room || !play?.self.club_id) return;
    await report(
      api(`/api/games/${room.game_id}/clubs/${play.self.club_id}/turn-academy-budget`, {
        method: 'POST',
        body: JSON.stringify({ annual_budget: annualBudget }),
      }).then(() => loadPlay(room.game_id)),
    );
  }

  async function saveBudgetEvent(key: string, budgetAmount: number) {
    if (!room || !play?.self.club_id) return;
    await report(
      api(`/api/games/${room.game_id}/clubs/${play.self.club_id}/turn-budget-event`, {
        method: 'POST',
        body: JSON.stringify({ key, amount: budgetAmount }),
      }).then(() => loadPlay(room.game_id)),
    );
  }

  function clearCurrentGame() {
    setRoom(null);
    setPlay(null);
    setConsoleData(null);
    setFinancialDisclosure(null);
    setTeamPowerDisclosure(null);
    setResultSummary(null);
    setFormValues({});
    setDraftDirty(false);
    setDraftState('未保存');
    restoredTurnId.current = null;
    setStage('entry');
  }

  async function archiveGame(target: RecentRoom | null = null) {
    const gameId = target?.game_id || room?.game_id;
    const roomName = target?.room_name || room?.invite_code || '';
    if (!gameId) return;
    if (!window.confirm(`${roomName} をアーカイブします。通常の再開一覧から非表示になります。`)) return;
    await report(
      api(`/api/games/${gameId}/archive`, { method: 'POST' }).then(async () => {
        clearCurrentGame();
        await loadRecentRooms();
      }),
    );
  }

  async function deleteArchivedGame(target: RecentRoom) {
    await report(
      api<DeletePreview>(`/api/games/${target.game_id}/delete-preview`).then(async (preview) => {
        const confirmText = window.prompt(
          `${preview.room_name} を完全削除します。復元できません。削除するには招待コード ${preview.invite_code} を入力してください。`,
        );
        if (!confirmText) return;
        await api(`/api/games/${target.game_id}`, {
          method: 'DELETE',
          body: JSON.stringify({ confirm: confirmText }),
        });
        clearCurrentGame();
        await loadRecentRooms();
      }),
    );
  }

  return (
    <main className="shell">
      <header className="masthead">
        <div>
          <p className="eyebrow">J-League Management Multiplayer</p>
          <h1>クラブ経営コンソール</h1>
        </div>
        <div className="statusline">
          <span>{room ? `ROOM ${room.invite_code}` : 'ROOM ----'}</span>
          <span>{play?.season ? `SEASON ${play.season.number}` : 'LOBBY'}</span>
          <span>{statusText(play?.turn?.state)}</span>
          <span className="online">polling</span>
        </div>
      </header>
      {error ? <p className="errorline">{error}</p> : null}
      {stage === 'entry' ? (
        <Entry
          archivedRooms={archivedRooms}
          busy={busy}
          clubNames={clubNames}
          displayName={displayName}
          inviteCode={inviteCode}
          recentRooms={recentRooms}
          roomName={roomName}
          onArchive={archiveGame}
          onClubNames={setClubNames}
          onCreate={createRoom}
          onDeleteArchived={deleteArchivedGame}
          onDisplayName={setDisplayName}
          onInviteCode={setInviteCode}
          onJoin={joinRoom}
          onResume={(roomId) => report(loadRoom(roomId))}
          onRoomName={setRoomName}
        />
      ) : null}
      {stage === 'lobby' && room ? (
        <Lobby
          busy={busy}
          room={room}
          onClaim={(clubId) =>
            refreshRoom(api(`/api/rooms/${room.id}/clubs/${clubId}/claim`, { method: 'POST' }))
          }
          onReady={(ready) =>
            refreshRoom(
              api(`/api/rooms/${room.id}/memberships/me/ready`, {
                method: 'PATCH',
                body: JSON.stringify({ ready }),
              }),
            )
          }
          onStart={startRoom}
        />
      ) : null}
      {stage === 'console' && room ? (
        <Console
          busy={busy}
          consoleData={consoleData}
          financialDisclosure={financialDisclosure}
          teamPowerDisclosure={teamPowerDisclosure}
          draftState={draftState}
          formValues={formValues}
          play={play}
          onAck={ackTurn}
          onCommit={commitDecision}
          onFormValue={(key, value) => {
            if (key === 'sales_allocation_new' && value.trim() !== '') {
              const numeric = Number(value);
              if (Number.isNaN(numeric) || numeric < 0 || numeric > 1) return;
            }
            setFormValues((current) => ({ ...current, [key]: value }));
            setDraftDirty(true);
          }}
          onAcademyBudget={saveAcademyBudget}
          onBudgetEvent={saveBudgetEvent}
          onArchive={() => archiveGame()}
          onComplete={completeGame}
          onHostAction={hostAction}
          onHostUncommit={hostUncommit}
          onStaffPlan={saveStaffPlan}
        />
      ) : null}
      {stage === 'result' && room ? (
        <ResultSummaryView
          busy={busy}
          room={room}
          summary={resultSummary}
          onArchive={() => archiveGame()}
          onBack={() => clearCurrentGame()}
          onExport={downloadResultExport}
          onReopen={reopenGame}
        />
      ) : null}
    </main>
  );
}

function Entry({
  archivedRooms,
  busy,
  clubNames,
  displayName,
  inviteCode,
  recentRooms,
  roomName,
  onArchive,
  onClubNames,
  onCreate,
  onDeleteArchived,
  onDisplayName,
  onInviteCode,
  onJoin,
  onResume,
  onRoomName,
}: {
  archivedRooms: RecentRoom[];
  busy: boolean;
  clubNames: string[];
  displayName: string;
  inviteCode: string;
  recentRooms: RecentRoom[];
  roomName: string;
  onArchive: (room: RecentRoom) => void;
  onClubNames: (value: string[]) => void;
  onCreate: (event: FormEvent) => void;
  onDeleteArchived: (room: RecentRoom) => void;
  onDisplayName: (value: string) => void;
  onInviteCode: (value: string) => void;
  onJoin: (event: FormEvent) => void;
  onResume: (roomId: string) => void;
  onRoomName: (value: string) => void;
}) {
  return (
    <section className="entryStack">
      {recentRooms.length || archivedRooms.length ? (
        <article className="pane resumePane">
          <div className="paneTitle">
            <div>
              <p className="eyebrow">Resume</p>
              <h2>続きから再開</h2>
            </div>
          </div>
          {recentRooms.length ? (
            <div className="roomList">
              {recentRooms.map((item) => (
                <div className="roomCard" key={item.room_id}>
                  <div>
                    <strong>{item.room_name}</strong>
                    <p className="muted">
                      {item.club_name || (item.is_host ? 'ホスト' : '未割当')} / {item.season ? `S${item.season.number}` : 'ロビー'} / {item.room_status === 'completed' ? '終了済み' : item.turn?.month_name || item.room_status}
                    </p>
                  </div>
                  <div className="roomActions">
                    {item.is_host && item.room_status !== 'completed' ? (
                      <button disabled={busy} onClick={() => onArchive(item)} type="button">
                        アーカイブ
                      </button>
                    ) : null}
                    <button className="primary" disabled={busy} onClick={() => onResume(item.room_id)} type="button">
                      {item.room_status === 'completed' ? '結果を見る' : '再開'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : <p className="muted">再開できるゲームはありません。</p>}
          {archivedRooms.length ? (
            <div className="archivedList">
              <h3>アーカイブ済み</h3>
              {archivedRooms.map((item) => (
                <div className="roomCard archivedRoom" key={item.room_id}>
                  <div>
                    <strong>{item.room_name}</strong>
                    <p className="muted">招待コード {item.invite_code}</p>
                  </div>
                  <div className="roomActions">
                    {item.completed_at ? (
                      <button disabled={busy} onClick={() => onResume(item.room_id)} type="button">結果を見る</button>
                    ) : null}
                    <button disabled={busy} onClick={() => onDeleteArchived(item)} type="button">
                      完全削除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </article>
      ) : null}
      <section className="entryGrid">
      <form className="pane entryPane" onSubmit={onCreate}>
        <h2>ルーム作成</h2>
        <label>
          ホスト表示名
          <input required value={displayName} onChange={(event) => onDisplayName(event.target.value)} />
        </label>
        <label>
          ルーム名
          <input required value={roomName} onChange={(event) => onRoomName(event.target.value)} />
        </label>
        <div className="clubSlots">
          <span>クラブ枠</span>
          {clubNames.map((clubName, index) => (
            <input
              key={`slot-${index}`}
              required={index < 2}
              value={clubName}
              onChange={(event) =>
                onClubNames(clubNames.map((value, valueIndex) => (valueIndex === index ? event.target.value : value)))
              }
            />
          ))}
        </div>
        <button disabled={busy}>ホストとして開始</button>
      </form>
      <form className="pane entryPane" onSubmit={onJoin}>
        <h2>招待コード参加</h2>
        <label>
          プレイヤー表示名
          <input required value={displayName} onChange={(event) => onDisplayName(event.target.value)} />
        </label>
        <label>
          招待コード
          <input required value={inviteCode} onChange={(event) => onInviteCode(event.target.value)} />
        </label>
        <button disabled={busy}>ルームへ入る</button>
      </form>
      </section>
    </section>
  );
}

function Lobby({
  busy,
  room,
  onClaim,
  onReady,
  onStart,
}: {
  busy: boolean;
  room: Room;
  onClaim: (clubId: string) => void;
  onReady: (ready: boolean) => void;
  onStart: () => void;
}) {
  const allReady = room.clubs.every((club) => club.claimed_by && club.ready);
  return (
    <section className="lobbyGrid">
      <article className="pane widePane">
        <div className="paneTitle">
          <h2>ロビー</h2>
          <strong>招待コード {room.invite_code}</strong>
        </div>
        <table>
          <thead>
            <tr><th>クラブ</th><th>担当</th><th>状態</th><th /></tr>
          </thead>
          <tbody>
            {room.clubs.map((club) => (
              <tr key={club.id}>
                <td>{club.name}</td>
                <td>{club.claimed_by_name || '未割当'}</td>
                <td><span className={club.ready ? 'ok' : 'pending'}>{club.ready ? 'ready' : 'waiting'}</span></td>
                <td>
                  {!club.claimed_by || club.claimed_by === room.self.user_id ? (
                    <button type="button" disabled={busy} onClick={() => onClaim(club.id)}>
                      {club.claimed_by === room.self.user_id ? '選択中' : '担当する'}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
      <aside className="pane sidePane">
        <h2>参加者</h2>
        <ul className="memberList">
          {room.members.map((member) => (
            <li key={member.id}>
              <span>{member.display_name}</span>
              <small>{member.is_host ? 'HOST' : member.ready ? 'READY' : 'WAIT'}</small>
            </li>
          ))}
        </ul>
        {room.self.club_id ? (
          <button type="button" disabled={busy} onClick={() => onReady(!room.self.ready)}>
            {room.self.ready ? 'ready解除' : 'readyにする'}
          </button>
        ) : <p className="muted">クラブを選ぶと ready にできます。</p>}
        {room.is_host ? (
          <button className="primary" type="button" disabled={busy || !allReady} onClick={onStart}>
            ゲーム開始
          </button>
        ) : <p className="muted">ホストの開始を待っています。</p>}
      </aside>
    </section>
  );
}

type ResultSection = 'overall' | 'seasons' | 'club' | 'decisions';

function ResultTrendChart({
  metrics,
  metric,
  invert = false,
}: {
  metrics: ResultSeasonMetric[];
  metric: keyof ResultSeasonMetric;
  invert?: boolean;
}) {
  const points = metrics
    .map((row, index) => ({ index, value: typeof row[metric] === 'number' ? Number(row[metric]) : null }))
    .filter((row): row is { index: number; value: number } => row.value !== null);
  if (!points.length) return <p className="muted">記録なし</p>;
  const values = points.map((row) => row.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const path = points.map((point, pointIndex) => {
    const x = metrics.length <= 1 ? 50 : 6 + (point.index / (metrics.length - 1)) * 88;
    const normalized = (point.value - min) / range;
    const y = 86 - (invert ? 1 - normalized : normalized) * 70;
    return `${pointIndex ? 'L' : 'M'} ${x} ${y}`;
  }).join(' ');
  return (
    <svg aria-label={`${String(metric)}のシーズン推移`} className="resultTrendChart" role="img" viewBox="0 0 100 100">
      <path className="resultTrendLine" d={path} fill="none" />
      {points.map((point) => {
        const x = metrics.length <= 1 ? 50 : 6 + (point.index / (metrics.length - 1)) * 88;
        const normalized = (point.value - min) / range;
        const y = 86 - (invert ? 1 - normalized : normalized) * 70;
        return <circle key={`${point.index}-${point.value}`} cx={x} cy={y} r="2.5" />;
      })}
      {metrics.map((row, index) => (
        <text key={row.season_id} x={metrics.length <= 1 ? 50 : 6 + (index / (metrics.length - 1)) * 88} y="98" textAnchor="middle">
          S{row.season_number}
        </text>
      ))}
    </svg>
  );
}

function ResultSummaryView({
  busy,
  room,
  summary,
  onArchive,
  onBack,
  onExport,
  onReopen,
}: {
  busy: boolean;
  room: Room;
  summary: ResultSummary | null;
  onArchive: () => void;
  onBack: () => void;
  onExport: (format: 'pdf' | 'csv-zip') => void;
  onReopen: () => void;
}) {
  const [section, setSection] = useState<ResultSection>('overall');
  const [selectedClubId, setSelectedClubId] = useState('');
  const reviews = summary?.club_reviews || [];
  const selectedReview = reviews.find((review) => review.club_id === selectedClubId) || reviews[0] || null;
  const seasons = Array.from(new Map((summary?.season_standings || []).map((row) => [row.season_id, {
    id: row.season_id,
    number: row.season_number,
    year: row.year_label,
  }])).values());

  if (!summary) {
    return <section className="pane resultLoading"><h2>結果サマリーを生成中...</h2></section>;
  }

  return (
    <section className="resultShell">
      <article className="pane resultHeader">
        <div>
          <p className="eyebrow">Completed game</p>
          <h2>{summary.game.name} 結果サマリー</h2>
          <p className="muted">
            {summary.game.seasons_played}シーズン / {new Date(summary.game.started_at || summary.game.created_at).toLocaleDateString('ja-JP')}
            {' 〜 '}{new Date(summary.game.completed_at).toLocaleString('ja-JP')}
          </p>
        </div>
        <div className="resultActions">
          <button disabled={busy} onClick={() => onExport('pdf')} type="button">PDF出力</button>
          <button disabled={busy} onClick={() => onExport('csv-zip')} type="button">CSV一括出力</button>
          {room.is_host && room.status === 'completed' ? (
            <button disabled={busy} onClick={onReopen} type="button">終了を取り消す</button>
          ) : null}
          {room.is_host && room.status !== 'archived' ? (
            <button disabled={busy} onClick={onArchive} type="button">アーカイブ</button>
          ) : null}
          <button disabled={busy} onClick={onBack} type="button">一覧へ</button>
        </div>
      </article>

      <nav className="pane resultTabs" aria-label="Result summary sections">
        {([
          ['overall', '総合結果'],
          ['seasons', 'シーズン推移'],
          ['club', 'クラブレビュー'],
          ['decisions', '意思決定タイムライン'],
        ] as Array<[ResultSection, string]>).map(([key, label]) => (
          <button aria-pressed={section === key} className={section === key ? 'active' : ''} key={key} onClick={() => setSection(key)} type="button">
            {label}
          </button>
        ))}
      </nav>

      {section === 'overall' ? (
        <article className="pane resultPane">
          <h2>総合結果</h2>
          <p className="muted">単一の総合優勝者は決定せず、複数の評価軸で結果を表示します。</p>
          <div className="wideTableWrap">
            <table className="resultTable">
              <thead><tr><th>クラブ</th><th>売上</th><th>純資産</th><th>優勝/準優勝</th><th>平均順位</th><th>平均入場者</th><th>ファンベース</th><th>フォロワー</th><th>スポンサー</th><th>次年度スポンサー</th></tr></thead>
              <tbody>
                {summary.overall_results.map((row) => (
                  <tr key={row.club_id}>
                    <td>{row.club_name}</td>
                    <td>{amount(row.final_sales_amount)} <small>#{row.final_sales_rank ?? '-'}</small></td>
                    <td>{amount(row.final_equity_amount)} <small>#{row.final_equity_rank ?? '-'}</small></td>
                    <td>{count(row.championship_count)} / {count(row.runner_up_count)}</td>
                    <td>{row.average_rank ?? '-'}</td>
                    <td>{count(row.average_home_attendance)} <small>#{row.attendance_rank ?? '-'}</small></td>
                    <td>{count(row.final_fanbase)} <small>#{row.fanbase_rank ?? '-'}</small></td>
                    <td>{count(row.final_followers)} <small>#{row.followers_rank ?? '-'}</small></td>
                    <td>{count(row.final_sponsor_count)} <small>#{row.sponsor_rank ?? '-'}</small></td>
                    <td>{count(row.next_sponsor_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <section className="resultHighlights">
            <h3>ゲームのハイライト</h3>
            {summary.highlights.length ? summary.highlights.map((row, index) => (
              <p key={`${row.club_id}-${row.category}-${index}`}><strong>{row.club_name}</strong> — {row.message}</p>
            )) : <p className="muted">抽出できるハイライトはありません。</p>}
          </section>
        </article>
      ) : null}

      {section === 'seasons' ? (
        <article className="pane resultPane">
          <h2>シーズン別最終順位</h2>
          {seasons.map((season) => (
            <section className="resultSeason" key={season.id}>
              <h3>Season {season.number} / {season.year}</h3>
              <div className="wideTableWrap"><table><thead><tr><th>順位</th><th>クラブ</th><th>試合</th><th>勝</th><th>分</th><th>敗</th><th>得点</th><th>失点</th><th>得失点</th><th>勝点</th></tr></thead>
                <tbody>{summary.season_standings.filter((row) => row.season_id === season.id).map((row) => (
                  <tr key={row.club_id}><td>{row.rank}</td><td>{row.club_name}</td><td>{row.played}</td><td>{row.won}</td><td>{row.drawn}</td><td>{row.lost}</td><td>{row.gf}</td><td>{row.ga}</td><td>{row.gd}</td><td>{row.points}</td></tr>
                ))}</tbody>
              </table></div>
            </section>
          ))}
        </article>
      ) : null}

      {(section === 'club' || section === 'decisions') ? (
        <article className="pane resultPane">
          <div className="paneTitle">
            <h2>{section === 'club' ? 'クラブレビュー' : '意思決定タイムライン'}</h2>
            {reviews.length > 1 ? (
              <label className="compactSelect">クラブ
                <select value={selectedReview?.club_id || ''} onChange={(event) => setSelectedClubId(event.target.value)}>
                  {reviews.map((review) => <option key={review.club_id} value={review.club_id}>{review.club_name}</option>)}
                </select>
              </label>
            ) : null}
          </div>
          {!selectedReview ? <p className="muted">閲覧可能なクラブ詳細はありません。</p> : null}
          {selectedReview && section === 'club' ? (
            <>
              <div className="resultCharts">
                <section><h3>順位推移</h3><ResultTrendChart invert metric="rank" metrics={selectedReview.season_metrics} /></section>
                <section><h3>期末残高推移</h3><ResultTrendChart metric="closing_balance" metrics={selectedReview.season_metrics} /></section>
                <section><h3>ファンベース推移</h3><ResultTrendChart metric="fanbase" metrics={selectedReview.season_metrics} /></section>
              </div>
              <div className="wideTableWrap"><table><thead><tr><th>Season</th><th>順位</th><th>売上</th><th>費用</th><th>純収支</th><th>残高</th><th>入場者</th><th>ファン</th><th>フォロワー</th><th>スポンサー</th><th>チーム力</th><th>債務超過</th></tr></thead>
                <tbody>{selectedReview.season_metrics.map((row) => (
                  <tr key={row.season_id}><td>S{row.season_number}</td><td>{row.rank ?? '-'}</td><td>{amount(row.revenue)}</td><td>{expenseAmount(row.expense)}</td><td>{amount(row.net)}</td><td>{amount(row.closing_balance)}</td><td>{count(row.average_home_attendance)}</td><td>{count(row.fanbase)}</td><td>{count(row.followers)}</td><td>{count(row.sponsor_count)}</td><td>{row.team_power?.toFixed(2) ?? '-'}</td><td>{row.bankrupt ? 'あり' : 'なし'}</td></tr>
                ))}</tbody>
              </table></div>
              <div className="resultHighlights">{selectedReview.highlights.map((row, index) => <p key={`${row.category}-${index}`}>{row.message}</p>)}</div>
            </>
          ) : null}
          {selectedReview && section === 'decisions' ? (
            <div className="wideTableWrap"><table><thead><tr><th>Season</th><th>月</th><th>意思決定</th><th>確定者/日時</th><th>試合結果</th><th>収入</th><th>費用</th><th>残高</th><th>順位</th><th>勝点</th></tr></thead>
              <tbody>{selectedReview.decisions.map((row, index) => (
                <tr key={`${row.season_number}-${row.month_index}-${index}`}><td>S{row.season_number}</td><td>{row.month_name}</td><td className="decisionCell">{Object.keys(row.inputs).length ? Object.entries(row.inputs).map(([key, value]) => <span key={key}>{resultDecisionLabels[key] || key}: {typeof value === 'object' ? JSON.stringify(value) : amount(Number(value))}</span>) : '記録なし'}</td><td>{row.committed_by || '-'}<small>{row.committed_at ? new Date(row.committed_at).toLocaleString('ja-JP') : '記録なし'}</small></td><td className="decisionCell">{row.matches.length ? row.matches.map((match, matchIndex) => <span key={`${match.opponent}-${matchIndex}`}>{match.home ? 'H' : 'A'} vs {match.opponent || '記録なし'}: {match.score_for ?? '-'}-{match.score_against ?? '-'}</span>) : '記録なし'}</td><td>{amount(row.income)}</td><td>{expenseAmount(row.expense)}</td><td>{amount(row.closing_balance)}</td><td>{row.rank ?? '-'}</td><td>{row.points ?? '-'}</td></tr>
              ))}</tbody>
            </table></div>
          ) : null}
        </article>
      ) : null}
    </section>
  );
}

function Console({
  busy,
  consoleData,
  financialDisclosure,
  teamPowerDisclosure,
  draftState,
  formValues,
  play,
  onAck,
  onAcademyBudget,
  onArchive,
  onBudgetEvent,
  onCommit,
  onComplete,
  onFormValue,
  onHostAction,
  onHostUncommit,
  onStaffPlan,
}: {
  busy: boolean;
  consoleData: ConsoleData | null;
  financialDisclosure: PublicDisclosure<FinancialSummaryClub> | null;
  teamPowerDisclosure: PublicDisclosure<TeamPowerClub> | null;
  draftState: string;
  formValues: Record<string, string>;
  play: PlayState | null;
  onAck: () => void;
  onAcademyBudget: (annualBudget: number) => void;
  onArchive: () => void;
  onBudgetEvent: (key: string, amount: number) => void;
  onCommit: () => void;
  onComplete: () => void;
  onFormValue: (key: string, value: string) => void;
  onHostAction: (action: string) => void;
  onHostUncommit: (clubId: string) => void;
  onStaffPlan: (role: string, count: number) => void;
}) {
  const [activeSection, setActiveSection] = useState<ConsoleSection>('Turn');
  const turnState = play?.turn?.state || null;
  const clubs = play?.clubs || [];
  const selfClubId = play?.self.club_id || null;
  const ownClub = clubs.find((club) => club.id === selfClubId);
  const allCommitted = Boolean(clubs.length) && clubs.every((club) => club.committed);
  const allAcked = Boolean(clubs.length) && clubs.every((club) => club.acked);
  const committed = Boolean(ownClub?.committed);
  const acked = Boolean(ownClub?.acked);
  const canCommit = Boolean(
    consoleData
    && selfClubId
    && consoleData.available_inputs.length
    && !committed
    && (turnState === 'open' || turnState === 'collecting'),
  );
  const nextStep = (() => {
    if (!play?.turn) return 'ゲーム開始または次ターンを待っています。';
    if (!play.self.club_id) return play.self.is_host ? 'ホスト操作と公開進捗を確認できます。' : '担当クラブの割当を待っています。';
    if (turnState === 'locked') return 'ホストが結果計算を実行するまで待機してください。';
    if (turnState === 'resolved') return acked
      ? play.turn?.month_index === 12
        ? '全員のack後、ホストが次シーズンへ進むかゲームを終了します。'
        : '全員のack後、ホストが次ターンへ進めます。'
      : '結果を確認してackしてください。';
    if (committed) return '入力確定済みです。全クラブ確定後、ホストが締切できます。';
    return '表示されている項目を入力し、入力を確定してください。';
  })();
  const hostActionDisabled = (action: string) => {
    if (busy || !play?.self.is_host) return true;
    if (action === 'open') return turnState !== 'open';
    if (action === 'lock') return !(turnState === 'open' || turnState === 'collecting') || !allCommitted;
    if (action === 'resolve') return turnState !== 'locked';
    if (action === 'advance') return turnState !== 'resolved' || !allAcked;
    return true;
  };
  const canHostUncommit = Boolean(play?.self.is_host && (turnState === 'open' || turnState === 'collecting'));

  return (
    <section className="consoleGrid">
      <nav className="pane rail" aria-label="Console sections">
        {consoleSections.map((item) => (
          <button
            key={item}
            className={item === activeSection ? 'active' : ''}
            type="button"
            onClick={() => setActiveSection(item)}
          >
            {item}
          </button>
        ))}
      </nav>
      <section className="centerStack">
        {activeSection === 'Turn' ? (
          <>
            <article className="pane turnPane">
              <div className="paneTitle">
                <div>
                  <p className="eyebrow">{play?.turn ? `Season ${play.turn.season_number} / ${play.turn.month_name}` : 'Season -'}</p>
                  <h2>ターン入力</h2>
                </div>
                <span className="saveState">{draftState}</span>
              </div>
              <p className="nextStep">{nextStep}</p>
              {!play?.self.club_id ? <p>担当クラブがありません。ホスト操作と公開進捗のみ利用できます。</p> : null}
              {consoleData ? (
                <>
                  <div className="inputGrid">
                    {consoleData.available_inputs.map((input) => (
                      <label key={input.key}>
                        {input.label}
                        <span className="moneyField">
                          {moneyKeys.has(input.key) ? (
                            <FormattedIntegerInput
                              value={formValues[input.key] || ''}
                              onValueChange={(value) => onFormValue(input.key, value)}
                            />
                          ) : (
                            <input
                              inputMode="decimal"
                              min="0"
                              max="1"
                              step="0.01"
                              type="number"
                              value={formValues[input.key] || ''}
                              onChange={(event) => onFormValue(input.key, event.target.value)}
                            />
                          )}
                          <small>{moneyKeys.has(input.key) ? 'JPY' : '0..1'}</small>
                        </span>
                      </label>
                    ))}
                  </div>
                  {consoleData.available_actions.includes('staff_hiring_firing_available') ? (
                    <MayActions
                      academy={consoleData.academy}
                      busy={busy}
                      staff={consoleData.staff}
                      onAcademyBudget={onAcademyBudget}
                      onStaffPlan={onStaffPlan}
                    />
                  ) : null}
                  {consoleData.event_budget ? (
                    <BudgetEventActions
                      busy={busy}
                      event={consoleData.event_budget}
                      onBudgetEvent={onBudgetEvent}
                    />
                  ) : null}
                  <div className="actionRow">
                    <button className="primary" disabled={!canCommit} onClick={onCommit}>
                      {committed ? '入力確定済み' : '入力を確定'}
                    </button>
                    <span>state: {consoleData.decision.state || 'draft'}</span>
                    {play?.turn?.state === 'resolved' ? (
                      <button disabled={busy || acked} onClick={onAck}>{acked ? 'ack済み' : '結果を確認して ack'}</button>
                    ) : null}
                  </div>
                </>
              ) : <p className="muted">担当クラブの入力コンソールを待機中です。</p>}
            </article>
            <SummaryTables consoleData={consoleData} standings={play?.standings || []} />
          </>
        ) : (
          <ConsoleSectionPanel
            clubName={ownClub?.name || null}
            consoleData={consoleData}
            financialDisclosure={financialDisclosure}
            gameId={play?.game_id || null}
            section={activeSection}
            selfClubId={selfClubId}
            seasonId={play?.season?.id || null}
            standings={play?.standings || []}
            teamPowerDisclosure={teamPowerDisclosure}
          />
        )}
      </section>
      <aside className="rightStack">
        <article className="pane progressPane">
          <h2>対戦進捗</h2>
          <p className="muted progressHint">
            {turnState === 'resolved'
              ? play?.turn?.month_index === 12
                ? '全クラブのack後に次シーズンかゲーム終了を選べます。'
                : '全クラブのack後にadvanceできます。'
              : '全クラブのcommit後にlockできます。'}
          </p>
          <table>
            <tbody>
              {(play?.clubs || []).map((club) => (
                <tr key={club.id}>
                  <td>{club.name}</td>
                  <td className={club.committed ? 'ok' : 'pending'}>{club.committed ? 'commit' : 'input'}</td>
                  <td className={club.acked ? 'ok' : 'pending'}>{club.acked ? 'ack' : '-'}</td>
                  {play?.self.is_host ? (
                    <td>
                      <button
                        disabled={busy || !canHostUncommit || !club.committed}
                        onClick={() => onHostUncommit(club.id)}
                        type="button"
                      >
                        解除
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </article>
        <article className="pane hostPane">
          <h2>ホスト操作</h2>
          {play?.self.is_host ? (
            <div className="hostButtons">
              {['open', 'lock', 'resolve', 'advance'].map((action) => (
                <button key={action} disabled={hostActionDisabled(action)} onClick={() => onHostAction(action)}>
                  {action === 'advance' && play?.turn?.month_index === 12 ? '次シーズンへ' : action}
                </button>
              ))}
              {play?.turn?.month_index === 12 ? (
                <>
                  <button
                    className="primary"
                    disabled={busy || !play.completion?.eligible}
                    onClick={onComplete}
                    type="button"
                  >
                    ゲーム終了
                  </button>
                  {!play.completion?.eligible ? (
                    <small className="muted completionReason">
                      {(play.completion?.blockers || []).map((blocker) => completionBlockerLabels[blocker] || blocker).join(' / ')}
                    </small>
                  ) : null}
                </>
              ) : null}
              <button disabled={busy} onClick={onArchive} type="button">アーカイブ</button>
            </div>
          ) : <p className="muted">ホストが締切と解決を進めます。</p>}
        </article>
      </aside>
    </section>
  );
}

function ConsoleSectionPanel({
  clubName,
  consoleData,
  financialDisclosure,
  gameId,
  section,
  selfClubId,
  seasonId,
  standings,
  teamPowerDisclosure,
}: {
  clubName: string | null;
  consoleData: ConsoleData | null;
  financialDisclosure: PublicDisclosure<FinancialSummaryClub> | null;
  gameId: string | null;
  section: Exclude<ConsoleSection, 'Turn'>;
  selfClubId: string | null;
  seasonId: string | null;
  standings: PlayState['standings'];
  teamPowerDisclosure: PublicDisclosure<TeamPowerClub> | null;
}) {
  const titleMap: Record<Exclude<ConsoleSection, 'Turn'>, string> = {
    Matches: '試合',
    Table: '順位表',
    Finance: '財務',
    Fans: 'ファン',
    Sponsors: 'スポンサー',
    Staff: 'スタッフ',
    'Team Power': 'チーム力',
    Disclosures: '公開情報',
  };

  return (
    <article className="pane sectionPane">
      <div className="paneTitle">
        <div>
          <p className="eyebrow">{section}</p>
          <h2>{titleMap[section]}</h2>
        </div>
      </div>
      {!consoleData && section !== 'Matches' && section !== 'Disclosures' && section !== 'Team Power' ? <p className="muted">担当クラブの情報を待機中です。</p> : null}
      {section === 'Matches' ? (
        <MatchHistoryPanel
          currentFixtures={consoleData?.fixtures || null}
          currentSeasonId={seasonId}
          gameId={gameId}
          selfClubId={selfClubId}
        />
      ) : null}
      {section === 'Table' ? (
        <StandingsPanel gameId={gameId} standings={standings} />
      ) : null}
      {consoleData && section === 'Finance' ? (
        <FinancePanel
          clubId={selfClubId}
          clubName={clubName}
          gameId={gameId}
          report={consoleData.finance.report}
          seasonId={seasonId}
        />
      ) : null}
      {consoleData && section === 'Fans' ? (
        <table>
          <thead>
            <tr><th>クラブ</th><th>公開フォロワー</th><th>ファンベース count</th></tr>
          </thead>
          <tbody>
            {consoleData.fanbase.comparison.map((row) => (
              <tr key={row.club_id} className={row.is_self ? 'selfRow' : ''}>
                <td>{row.club_name}</td>
                <td>{count(row.followers)}</td>
                <td>{count(row.fb_count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {consoleData && section === 'Sponsors' ? (
        <dl className="detailList">
          <dt>現スポンサー数</dt><dd>{consoleData.sponsor.count}</dd>
          <dt>翌期確定見込み</dt><dd>{consoleData.sponsor.confirmed_next}</dd>
          <dt className="detailSubLabel">└ 新規</dt><dd>{consoleData.sponsor.confirmed_next_new}</dd>
          <dt className="detailSubLabel">└ 既存</dt><dd>{consoleData.sponsor.confirmed_next_existing}</dd>
        </dl>
      ) : null}
      {consoleData && section === 'Staff' ? (
        <table>
          <thead>
            <tr><th>区分</th><th>現在人数</th><th>来季予定</th></tr>
          </thead>
          <tbody>
            {consoleData.staff.map((staff) => (
              <tr key={staff.role}>
                <td>{staff.role}</td>
                <td>{staff.count}</td>
                <td>{staff.input_count ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {section === 'Team Power' ? (
        <TeamPowerPanel disclosure={teamPowerDisclosure} selfClubId={selfClubId} />
      ) : null}
      {section === 'Disclosures' ? (
        <FinancialDisclosurePanel disclosure={financialDisclosure} selfClubId={selfClubId} />
      ) : null}
    </article>
  );
}

function MatchHistoryPanel({
  currentFixtures,
  currentSeasonId,
  gameId,
  selfClubId,
}: {
  currentFixtures: MatchFixture[] | null;
  currentSeasonId: string | null;
  gameId: string | null;
  selfClubId: string | null;
}) {
  const [payload, setPayload] = useState<MatchHistoryPayload>(emptyMatchHistoryPayload);
  const [payloadSource, setPayloadSource] = useState('');
  const [selectedSeasonId, setSelectedSeasonId] = useState(currentSeasonId || '');
  const [loadFailure, setLoadFailure] = useState({ source: '', message: '' });
  const source = gameId && selfClubId ? `${gameId}:${selfClubId}` : '';

  useEffect(() => {
    if (!source || !gameId || !selfClubId) {
      return undefined;
    }

    let cancelled = false;
    api<MatchHistoryPayload>(`/api/games/${gameId}/clubs/${selfClubId}/match-history`)
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
        setPayloadSource(source);
        setLoadFailure({ source, message: '' });
        setSelectedSeasonId((selected) => {
          if (selected && data.seasons.some((season) => season.id === selected)) return selected;
          if (currentSeasonId && data.seasons.some((season) => season.id === currentSeasonId)) {
            return currentSeasonId;
          }
          return data.seasons[0]?.id || '';
        });
      })
      .catch((cause: Error) => {
        if (!cancelled) setLoadFailure({ source, message: friendlyError(cause.message) });
      });

    return () => {
      cancelled = true;
    };
  }, [currentSeasonId, gameId, selfClubId, source]);

  const visiblePayload = payloadSource === source ? payload : emptyMatchHistoryPayload;
  const loadError = loadFailure.source === source ? loadFailure.message : '';
  const loading = Boolean(source && payloadSource !== source && !loadError);
  const selectedSeason = visiblePayload.seasons.find((season) => season.id === selectedSeasonId);
  const historicalFixtures = selectedSeasonId ? visiblePayload.fixtures[selectedSeasonId] || [] : [];
  const fixtures = selectedSeasonId === currentSeasonId && currentFixtures
    ? currentFixtures
    : historicalFixtures;

  if (!selfClubId) {
    return <p className="muted">担当クラブの情報を待機中です。</p>;
  }

  return (
    <section className="matchHistoryPanel">
      <div className="matchHistoryToolbar">
        <p className="muted">
          {selectedSeason
            ? `対象: Season ${selectedSeason.season_number} / ${selectedSeason.year_label}`
            : loading
            ? 'シーズン情報を読み込み中です。'
            : loadError
            ? 'シーズン情報を取得できませんでした。'
            : '閲覧できるシーズンはまだありません。'}
        </p>
        <label className="compactSelect">
          シーズン
          <select
            aria-label="試合結果を表示するシーズン"
            disabled={loading || !visiblePayload.seasons.length}
            value={visiblePayload.seasons.length ? selectedSeasonId : ''}
            onChange={(event) => setSelectedSeasonId(event.target.value)}
          >
            {!visiblePayload.seasons.length ? (
              <option value="">{loading ? '読み込み中' : '未登録'}</option>
            ) : null}
            {visiblePayload.seasons.map((season) => (
              <option key={season.id} value={season.id}>
                Season {season.season_number} / {season.year_label}
                {season.id === currentSeasonId ? '（現在）' : ''}
              </option>
            ))}
          </select>
        </label>
      </div>
      {loadError ? <p className="errorline">{loadError}</p> : null}
      {!loading && !loadError && !visiblePayload.seasons.length ? (
        <p className="muted">閲覧できるシーズンはまだありません。</p>
      ) : null}
      {!loading && selectedSeason && !fixtures.length ? (
        <p className="muted">このシーズンの試合はありません。</p>
      ) : null}
      {fixtures.length ? (
        <div className="wideTableWrap matchTableWrap">
          <table>
            <thead>
              <tr><th>月</th><th>H/A</th><th>相手</th><th>状態</th><th>結果</th><th>入場者数</th><th>天気</th></tr>
            </thead>
            <tbody>
              {fixtures.map((fixture) => (
                <tr key={fixture.id}>
                  <td>{fixture.month}</td>
                  <td>{fixture.is_bye ? 'bye' : fixture.home ? 'H' : 'A'}</td>
                  <td>{fixture.opponent || '-'}</td>
                  <td>{fixture.status}</td>
                  <td>{fixture.score_for_club ? fixture.score_for_club.join('-') : '-'}</td>
                  <td>{count(fixture.total_attendance)}</td>
                  <td>{fixture.weather || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function disclosureValue(row: FinancialSummaryClub, keys: readonly string[]) {
  for (const key of keys) {
    const value = row[key];
    if (typeof value === 'number') return value;
    if (typeof value === 'string') {
      const numeric = Number(value);
      if (!Number.isNaN(numeric)) return numeric;
    }
  }
  return null;
}

function teamPowerDisclosureLabel(type: string | undefined) {
  if (type === 'team_power_june_preview') return '6月入力ベース / 暫定公開';
  if (type === 'team_power_july') return '7月公開 / 次シーズン予測';
  if (type === 'team_power_december') return '12月公開 / 最新';
  if (type === 'team_power_july_carried') return '前シーズン7月公開値';
  return type || 'チーム力開示';
}

const financialDisclosureRows: ReadonlyArray<{
  label: string;
  keys: readonly string[];
  isExpense?: boolean;
  totalKind?: 'income' | 'expense';
}> = [
  { label: 'スポンサー収入', keys: ['Sponsor_revenue'] },
  { label: '入場料収入', keys: ['ticket_revenue'] },
  { label: '配分金', keys: ['distribution_revenue'] },
  { label: '賞金', keys: ['prize_revenue'] },
  { label: '物販収入', keys: ['merchandise_revenue'] },
  { label: '移籍金収入', keys: ['academy_transfer_fee'] },
  { label: '収入合計', keys: ['total_revenue'], totalKind: 'income' },
  { label: '強化費', keys: ['reinforcement_cost'], isExpense: true },
  { label: '試合関連経費', keys: ['match_operation_cost'], isExpense: true },
  { label: 'トップチーム運営経費', keys: ['team_operation_cost'], isExpense: true },
  { label: 'アカデミー運営経費', keys: ['academy_cost'], isExpense: true },
  { label: '物販原価', keys: ['merchandise_cost'], isExpense: true },
  { label: '人件費', keys: ['staff_cost'], isExpense: true },
  { label: '費用合計', keys: ['total_expense', 'total expense'], isExpense: true, totalKind: 'expense' },
  { label: '純利益', keys: ['net_income'] },
  { label: '期末残高', keys: ['ending_balance'] },
];

function TeamPowerPanel({
  disclosure,
  selfClubId,
}: {
  disclosure: PublicDisclosure<TeamPowerClub> | null;
  selfClubId: string | null;
}) {
  const clubs = disclosure?.disclosed_data?.clubs || [];
  const disclosureType = disclosure?.disclosed_data?.disclosure_type || disclosure?.disclosure_type;
  const reinforcementEstimateLabel = clubs.find(
    (club) => club.reinforcement_estimate_label,
  )?.reinforcement_estimate_label;

  if (!disclosure || clubs.length === 0) {
    return <p className="muted">7月ターン終了後または12月ターン終了後に、全クラブのチーム力指標が公開されます。</p>;
  }

  return (
    <section className="disclosurePanel">
      <div className="financePeriod">
        <strong>{teamPowerDisclosureLabel(disclosureType)}</strong>
        <span>公開月 {seasonMonthLabel(disclosure.disclosure_month)} / {new Date(disclosure.created_at).toLocaleString('ja-JP')}</span>
      </div>
      {disclosure.disclosed_data.note ? <p className="muted">{disclosure.disclosed_data.note}</p> : null}
      {reinforcementEstimateLabel ? (
        <p className="muted">強化費は入力額を基準に、約±20%の範囲で概算表示しています。</p>
      ) : null}
      <div className="disclosureTableWrap compactDisclosureTable">
        <table>
          <thead>
            <tr>
              <th>順位</th>
              <th>クラブ</th>
              <th>チーム力</th>
              {reinforcementEstimateLabel ? <th>{reinforcementEstimateLabel}</th> : null}
            </tr>
          </thead>
          <tbody>
            {clubs.map((club, index) => (
              <tr key={club.club_id} className={club.club_id === selfClubId ? 'selfRow' : ''}>
                <td>{index + 1}</td>
                <td>{club.club_name}</td>
                <td className="numeric">{club.team_power.toFixed(2)}</td>
                {reinforcementEstimateLabel ? (
                  <td className="numeric">
                    約 {amount(club.estimated_reinforcement_budget)}円
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StandingsPanel({
  gameId,
  standings,
}: {
  gameId: string | null;
  standings: PlayState['standings'];
}) {
  return (
    <section className="stackedPanel">
      <section className="subSection">
        <h3>現シーズン順位表</h3>
        <div className="wideTableWrap">
          <table>
            <thead>
              <tr><th>順位</th><th>クラブ</th><th>試合</th><th>勝</th><th>分</th><th>敗</th><th>得点</th><th>失点</th><th>得失点</th><th>勝点</th></tr>
            </thead>
            <tbody>
              {standings.map((row) => (
                <tr key={row.club_id}>
                  <td>{row.rank}</td>
                  <td>{row.club_name}</td>
                  <td>{row.played}</td>
                  <td>{row.won}</td>
                  <td>{row.drawn}</td>
                  <td>{row.lost}</td>
                  <td>{row.gf}</td>
                  <td>{row.ga}</td>
                  <td>{row.gd}</td>
                  <td>{row.points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <FinalStandingsPanel gameId={gameId} />
    </section>
  );
}

function FinalStandingsPanel({ gameId }: { gameId: string | null }) {
  const [seasons, setSeasons] = useState<SeasonOption[]>([]);
  const [selectedSeasonId, setSelectedSeasonId] = useState('');
  const [standingsBySeason, setStandingsBySeason] = useState<Record<string, StandingRow[]>>({});
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    if (!gameId) {
      return undefined;
    }

    let cancelled = false;
    api<FinalStandingsPayload>(`/api/games/${gameId}/final-standings`)
      .then((data) => {
        if (cancelled) return;
        setLoadError('');
        setSeasons(data.seasons);
        setStandingsBySeason(data.standings || {});
        setSelectedSeasonId((current) => (
          current && data.seasons.some((season) => season.id === current)
            ? current
            : data.seasons[0]?.id || ''
        ));
      })
      .catch((cause: Error) => {
        if (!cancelled) setLoadError(friendlyError(cause.message));
      });

    return () => {
      cancelled = true;
    };
  }, [gameId]);

  const availableSeasons = gameId ? seasons : [];
  const selectedSeason = availableSeasons.find((season) => season.id === selectedSeasonId);
  const visibleRows = selectedSeasonId ? standingsBySeason[selectedSeasonId] || [] : [];

  return (
    <section className="subSection">
      <div className="paneTitle compactTitle">
        <div>
          <p className="eyebrow">Final standings</p>
          <h3>シーズン別最終順位表</h3>
        </div>
        <label className="compactSelect">
          シーズン
          <select
            disabled={!availableSeasons.length}
            value={availableSeasons.length ? selectedSeasonId : ''}
            onChange={(event) => setSelectedSeasonId(event.target.value)}
          >
            {!availableSeasons.length ? <option value="">未確定</option> : null}
            {availableSeasons.map((season) => (
              <option key={season.id} value={season.id}>
                Season {season.season_number} / {season.year_label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {loadError ? <p className="errorline">{loadError}</p> : null}
      {!availableSeasons.length ? <p className="muted">確定済みシーズンの最終順位表はまだありません。</p> : null}
      {selectedSeason ? (
        <p className="muted">対象: Season {selectedSeason.season_number} / {selectedSeason.year_label}</p>
      ) : null}
      {visibleRows.length ? (
        <div className="wideTableWrap">
          <table>
            <thead>
              <tr><th>順位</th><th>クラブ</th><th>試合</th><th>勝</th><th>分</th><th>敗</th><th>得点</th><th>失点</th><th>得失点</th><th>勝点</th></tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <tr key={row.club_id}>
                  <td>{row.rank}</td>
                  <td>{row.club_name}</td>
                  <td>{row.played}</td>
                  <td>{row.won}</td>
                  <td>{row.drawn}</td>
                  <td>{row.lost}</td>
                  <td>{row.gf}</td>
                  <td>{row.ga}</td>
                  <td>{row.gd}</td>
                  <td>{row.points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function seasonMonthLabel(monthIndex: number) {
  const labels: Record<number, string> = {
    1: '8月',
    2: '9月',
    3: '10月',
    4: '11月',
    5: '12月',
    6: '1月',
    7: '2月',
    8: '3月',
    9: '4月',
    10: '5月',
    11: '6月',
    12: '7月',
  };
  return labels[monthIndex] || `${monthIndex}`;
}

function FinancialDisclosurePanel({
  disclosure,
  selfClubId,
}: {
  disclosure: PublicDisclosure | null;
  selfClubId: string | null;
}) {
  const clubs = disclosure?.disclosed_data?.clubs || [];
  const fiscalYear = clubs.find((club) => club.fiscal_year)?.fiscal_year;

  if (!disclosure || clubs.length === 0) {
    return <p className="muted">12月ターン終了後に、前シーズン末の全クラブ財務概要が公開されます。</p>;
  }

  return (
    <section className="disclosurePanel">
      <div className="financePeriod">
        <strong>{fiscalYear ? `対象年度 ${fiscalYear}` : '財務概要'}</strong>
        <span>公開月 {seasonMonthLabel(disclosure.disclosure_month)} / {new Date(disclosure.created_at).toLocaleString('ja-JP')}</span>
      </div>
      <div className="disclosureTableWrap">
        <table className="financialDisclosureTable" style={{ minWidth: Math.max(980, 180 + clubs.length * 150) }}>
          <thead>
            <tr>
              <th>項目</th>
              {clubs.map((club) => (
                <th key={club.club_id} className={club.club_id === selfClubId ? 'selfColumn' : ''}>
                  {club.club_name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {financialDisclosureRows.map((row) => (
              <tr
                key={row.label}
                className={row.totalKind ? `totalRow ${row.totalKind}TotalRow` : undefined}
              >
                <th scope="row">{row.label}</th>
                {clubs.map((club) => (
                  <td key={club.club_id} className={club.club_id === selfClubId ? 'numeric selfColumn' : 'numeric'}>
                    {row.isExpense
                      ? expenseAmount(disclosureValue(club, row.keys))
                      : amount(disclosureValue(club, row.keys))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function financeKindKey(kind: string) {
  if (kind === 'additional_reinforcement_applied') return null;
  if (kind === 'next_home_promo_expense') return 'promo_expense';
  if (kind.startsWith('staff_severance_')) return 'staff_severance';

  for (const prefix of ['match_operation_cost', 'merchandise_cost', 'merchandise_rev', 'ticket_rev']) {
    if (kind.startsWith(prefix)) return prefix;
  }
  return kind;
}

function financeKindLabel(kind: string) {
  const labels: Record<string, string> = {
    sponsor_annual: 'スポンサー収入',
    sponsor: 'スポンサー収入',
    ticket_rev: '入場料収入',
    distribution_revenue: '配分金',
    prize_revenue: '賞金',
    merchandise_rev: '物販収入',
    academy_transfer_fee: '移籍金収入',
    reinforcement_cost: '強化費',
    match_operation_cost: '試合関連経費',
    team_operation_cost: 'トップチーム運営経費',
    academy_cost: 'アカデミー運営経費',
    merchandise_cost: '物販原価',
    sales_expense: '営業費',
    promo_expense: 'プロモーション費',
    hometown_expense: 'ホームタウン活動費',
    staff_cost: '人件費',
    staff_severance: 'スタッフ退職金',
    admin_cost: '管理運営経費',
    tax: '税金',
  };
  return labels[kind] || kind;
}

function FinancePanel({
  clubId,
  clubName,
  gameId,
  report,
  seasonId,
}: {
  clubId: string | null;
  clubName: string | null;
  gameId: string | null;
  report: FinanceReport;
  seasonId: string | null;
}) {
  const [view, setView] = useState<'summary' | 'monthly' | 'annual'>('summary');

  if (view === 'monthly') {
    return (
      <MonthlyFinanceTrendPage
        clubId={clubId}
        clubName={clubName}
        gameId={gameId}
        seasonNumber={report.period.season_number}
        seasonId={seasonId}
        onBack={() => setView('summary')}
      />
    );
  }

  if (view === 'annual') {
    return (
      <AnnualFinanceTrendPage
        clubId={clubId}
        clubName={clubName}
        gameId={gameId}
        onBack={() => setView('summary')}
      />
    );
  }

  const period = report.period.month_name
    ? `Season ${report.period.season_number} / ${report.period.month_name}`
    : `Season ${report.period.season_number} / 未確定`;

  return (
    <section className="financePanel">
      <div className="financePeriod">
        <strong>{period}</strong>
        <span>期首 {amount(report.opening_balance)} / 期末 {amount(report.closing_balance)}</span>
      </div>
      <div className="actionRow flushActionRow">
        <button type="button" disabled={!clubId || !gameId || !seasonId} onClick={() => setView('monthly')}>
          月次財務推移
        </button>
        <button type="button" disabled={!clubId || !gameId} onClick={() => setView('annual')}>
          年次財務推移
        </button>
      </div>
      <div className="financeStatements">
        <FinanceStatementTable statement={report.monthly} title="今月の収支" />
        <FinanceStatementTable statement={report.cumulative} title="今シーズン累積の収支" />
      </div>
    </section>
  );
}

function MonthlyFinanceTrendPage({
  clubId,
  clubName,
  gameId,
  seasonNumber,
  seasonId,
  onBack,
}: {
  clubId: string | null;
  clubName: string | null;
  gameId: string | null;
  seasonNumber: number;
  seasonId: string | null;
  onBack: () => void;
}) {
  const [ledger, setLedger] = useState<FinanceLedgerEntry[]>([]);
  const [balances, setBalances] = useState<FinanceMonthBalance[]>([]);
  const [ledgerSource, setLedgerSource] = useState('');
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    if (!clubId || !gameId || !seasonId) {
      return undefined;
    }

    let cancelled = false;
    const source = `${gameId}:${clubId}:${seasonId}`;
    api<FinanceLedgerPayload>(`/api/games/${gameId}/clubs/${clubId}/finance-ledger?season_id=${seasonId}`)
      .then((data) => {
        if (!cancelled) {
          setLoadError('');
          setLedgerSource(source);
          setLedger(data.ledger || []);
          setBalances(data.balances || []);
        }
      })
      .catch((cause: Error) => {
        if (!cancelled) setLoadError(friendlyError(cause.message));
      });

    return () => {
      cancelled = true;
    };
  }, [clubId, gameId, seasonId]);

  const visibleLedger = useMemo(() => {
    if (!clubId || !gameId || !seasonId || ledgerSource !== `${gameId}:${clubId}:${seasonId}`) return [];
    return ledger;
  }, [clubId, gameId, ledger, ledgerSource, seasonId]);

  const visibleBalances = useMemo(() => {
    if (!clubId || !gameId || !seasonId || ledgerSource !== `${gameId}:${clubId}:${seasonId}`) return [];
    return balances;
  }, [balances, clubId, gameId, ledgerSource, seasonId]);

  const { rows, incomeTotals, expenseTotals, netTotals, cashBalances } = useMemo(() => {
    const byKind = new Map<string, Record<number, number>>();
    const income: Record<number, number> = {};
    const expense: Record<number, number> = {};
    const net: Record<number, number> = {};
    const cash: Record<number, number | null> = {};

    for (const month of seasonMonthIndexes) {
      income[month] = 0;
      expense[month] = 0;
      net[month] = 0;
      cash[month] = null;
    }

    for (const entry of visibleLedger) {
      const key = financeKindKey(entry.kind);
      if (!key || !seasonMonthIndexes.includes(entry.month_index)) continue;

      const current = byKind.get(key) || Object.fromEntries(seasonMonthIndexes.map((month) => [month, 0])) as Record<number, number>;
      current[entry.month_index] = (current[entry.month_index] || 0) + entry.amount;
      byKind.set(key, current);

      if (entry.amount > 0) income[entry.month_index] += entry.amount;
      if (entry.amount < 0) expense[entry.month_index] += entry.amount;
      net[entry.month_index] += entry.amount;
    }

    for (const balance of visibleBalances) {
      if (seasonMonthIndexes.includes(balance.month_index)) {
        cash[balance.month_index] = balance.closing_balance;
      }
    }

    const orderIndex = new Map(financeKindOrder.map((kind, index) => [kind, index]));
    const sortedRows = Array.from(byKind.entries())
      .sort(([left], [right]) => (orderIndex.get(left) ?? 999) - (orderIndex.get(right) ?? 999) || left.localeCompare(right))
      .map(([kind, values]) => ({ kind, label: financeKindLabel(kind), values }));

    return {
      rows: sortedRows,
      incomeTotals: income,
      expenseTotals: expense,
      netTotals: net,
      cashBalances: cash,
    };
  }, [visibleBalances, visibleLedger]);

  const incomeRows = useMemo(
    () => rows.filter((row) => financeIncomeKinds.has(row.kind)),
    [rows],
  );
  const expenseRows = useMemo(
    () => rows.filter((row) => !financeIncomeKinds.has(row.kind)),
    [rows],
  );

  const csvRows = useMemo<CsvCell[][]>(() => [
    ['費目', ...seasonMonthIndexes.map(seasonMonthLabel)],
    ...rows.map((row) => [
      row.label,
      ...seasonMonthIndexes.map((month) => csvAmount(row.values[month])),
    ]),
    ['収入合計', ...seasonMonthIndexes.map((month) => csvAmount(incomeTotals[month]))],
    ['費用合計', ...seasonMonthIndexes.map((month) => csvAmount(expenseTotals[month]))],
    ['純収支', ...seasonMonthIndexes.map((month) => csvAmount(netTotals[month]))],
    ['現金残高', ...seasonMonthIndexes.map((month) => csvAmount(cashBalances[month]))],
  ], [cashBalances, expenseTotals, incomeTotals, netTotals, rows]);

  const exportCsv = () => {
    const filenameClub = safeCsvFilenamePart(clubName || 'club');
    downloadCsv(`${filenameClub}_月次財務_Season${seasonNumber}.csv`, csvRows);
  };

  return (
    <section className="financePanel">
      <div className="paneTitle compactTitle">
        <div>
          <p className="eyebrow">Monthly finance</p>
          <h3>月次財務推移</h3>
        </div>
        <div className="paneTitleActions">
          <button type="button" disabled={!rows.length} onClick={exportCsv}>CSVエクスポート</button>
          <button type="button" onClick={onBack}>戻る</button>
        </div>
      </div>
      {loadError ? <p className="errorline">{loadError}</p> : null}
      {!clubId || !gameId || !seasonId ? <p className="muted">担当クラブとシーズン情報を待機中です。</p> : null}
      {clubId && gameId && seasonId && ledgerSource === `${gameId}:${clubId}:${seasonId}` && !rows.length ? <p className="muted">このシーズンの財務台帳はまだありません。</p> : null}
      {rows.length ? (
        <div className="wideTableWrap">
          <table className="monthlyFinanceTable">
            <thead>
              <tr>
                <th>費目</th>
                {seasonMonthIndexes.map((month) => <th key={month}>{seasonMonthLabel(month)}</th>)}
              </tr>
            </thead>
            <tbody>
              {incomeRows.map((row) => (
                <tr key={row.kind}>
                  <td>{row.label}</td>
                  {seasonMonthIndexes.map((month) => (
                    <td key={month} className="numeric">{amount(row.values[month])}</td>
                  ))}
                </tr>
              ))}
              <tr className="totalRow incomeTotalRow">
                <td>収入合計</td>
                {seasonMonthIndexes.map((month) => <td key={month} className="numeric">{amount(incomeTotals[month])}</td>)}
              </tr>
              {expenseRows.map((row) => (
                <tr key={row.kind}>
                  <td>{row.label}</td>
                  {seasonMonthIndexes.map((month) => (
                    <td key={month} className="numeric">{expenseAmount(row.values[month])}</td>
                  ))}
                </tr>
              ))}
              <tr className="totalRow expenseTotalRow">
                <td>費用合計</td>
                {seasonMonthIndexes.map((month) => <td key={month} className="numeric">{expenseAmount(expenseTotals[month])}</td>)}
              </tr>
              <tr className="netRow">
                <td>純収支</td>
                {seasonMonthIndexes.map((month) => <td key={month} className="numeric">{amount(netTotals[month])}</td>)}
              </tr>
              <tr className="cashRow">
                <td>現金残高</td>
                {seasonMonthIndexes.map((month) => <td key={month} className="numeric">{amount(cashBalances[month])}</td>)}
              </tr>
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function AnnualFinanceTrendPage({
  clubId,
  clubName,
  gameId,
  onBack,
}: {
  clubId: string | null;
  clubName: string | null;
  gameId: string | null;
  onBack: () => void;
}) {
  const [payload, setPayload] = useState<AnnualFinanceLedgerPayload>({ seasons: [], ledger: [] });
  const [ledgerSource, setLedgerSource] = useState('');
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    if (!clubId || !gameId) return undefined;

    let cancelled = false;
    const source = `${gameId}:${clubId}`;
    api<AnnualFinanceLedgerPayload>(`/api/games/${gameId}/clubs/${clubId}/annual-finance-ledger`)
      .then((data) => {
        if (!cancelled) {
          setLoadError('');
          setLedgerSource(source);
          setPayload(data);
        }
      })
      .catch((cause: Error) => {
        if (!cancelled) setLoadError(friendlyError(cause.message));
      });

    return () => {
      cancelled = true;
    };
  }, [clubId, gameId]);

  const visiblePayload = useMemo(() => {
    if (!clubId || !gameId || ledgerSource !== `${gameId}:${clubId}`) {
      return { seasons: [], ledger: [] } as AnnualFinanceLedgerPayload;
    }
    return payload;
  }, [clubId, gameId, ledgerSource, payload]);

  const { rows, incomeTotals, expenseTotals, netTotals } = useMemo(() => {
    const byKind = new Map<string, Record<string, number>>();
    const income: Record<string, number> = {};
    const expense: Record<string, number> = {};
    const net: Record<string, number> = {};

    for (const season of visiblePayload.seasons) {
      income[season.id] = 0;
      expense[season.id] = 0;
      net[season.id] = 0;
    }

    for (const entry of visiblePayload.ledger) {
      const key = financeKindKey(entry.kind);
      if (!key || !(entry.season_id in net)) continue;

      const current = byKind.get(key) || {};
      current[entry.season_id] = (current[entry.season_id] || 0) + entry.amount;
      byKind.set(key, current);

      if (entry.amount > 0) income[entry.season_id] += entry.amount;
      if (entry.amount < 0) expense[entry.season_id] += entry.amount;
      net[entry.season_id] += entry.amount;
    }

    const orderIndex = new Map(financeKindOrder.map((kind, index) => [kind, index]));
    const sortedRows = Array.from(byKind.entries())
      .sort(([left], [right]) => (orderIndex.get(left) ?? 999) - (orderIndex.get(right) ?? 999) || left.localeCompare(right))
      .map(([kind, values]) => ({ kind, label: financeKindLabel(kind), values }));

    return { rows: sortedRows, incomeTotals: income, expenseTotals: expense, netTotals: net };
  }, [visiblePayload]);

  const incomeRows = useMemo(
    () => rows.filter((row) => financeIncomeKinds.has(row.kind)),
    [rows],
  );
  const expenseRows = useMemo(
    () => rows.filter((row) => !financeIncomeKinds.has(row.kind)),
    [rows],
  );

  const csvRows = useMemo<CsvCell[][]>(() => [
    ['費目', ...visiblePayload.seasons.map((season) => `Season ${season.season_number}`)],
    ...incomeRows.map((row) => [
      row.label,
      ...visiblePayload.seasons.map((season) => csvAmount(row.values[season.id] || 0)),
    ]),
    ['収入合計', ...visiblePayload.seasons.map((season) => csvAmount(incomeTotals[season.id]))],
    ...expenseRows.map((row) => [
      row.label,
      ...visiblePayload.seasons.map((season) => csvAmount(row.values[season.id] || 0)),
    ]),
    ['費用合計', ...visiblePayload.seasons.map((season) => csvAmount(expenseTotals[season.id]))],
    ['累積収支', ...visiblePayload.seasons.map((season) => csvAmount(netTotals[season.id]))],
    ['現金残高', ...visiblePayload.seasons.map((season) => csvAmount(season.closing_balance))],
  ], [expenseRows, expenseTotals, incomeRows, incomeTotals, netTotals, visiblePayload.seasons]);

  const exportCsv = () => {
    const filenameClub = safeCsvFilenamePart(clubName || 'club');
    downloadCsv(`${filenameClub}_年次財務.csv`, csvRows);
  };

  return (
    <section className="financePanel">
      <div className="paneTitle compactTitle">
        <div>
          <p className="eyebrow">Annual finance</p>
          <h3>年次財務推移</h3>
        </div>
        <div className="paneTitleActions">
          <button type="button" disabled={!visiblePayload.seasons.length} onClick={exportCsv}>CSVエクスポート</button>
          <button type="button" onClick={onBack}>戻る</button>
        </div>
      </div>
      {loadError ? <p className="errorline">{loadError}</p> : null}
      {!clubId || !gameId ? <p className="muted">担当クラブ情報を待機中です。</p> : null}
      {clubId && gameId && ledgerSource === `${gameId}:${clubId}` && !visiblePayload.seasons.length ? (
        <p className="muted">シーズン末まで確定した年次財務はまだありません。</p>
      ) : null}
      {visiblePayload.seasons.length ? (
        <div className="wideTableWrap">
          <table className="monthlyFinanceTable">
            <thead>
              <tr>
                <th>費目</th>
                {visiblePayload.seasons.map((season) => (
                  <th key={season.id}>Season {season.season_number}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {incomeRows.map((row) => (
                <tr key={row.kind}>
                  <td>{row.label}</td>
                  {visiblePayload.seasons.map((season) => (
                    <td key={season.id} className="numeric">{amount(row.values[season.id] || 0)}</td>
                  ))}
                </tr>
              ))}
              <tr className="totalRow incomeTotalRow">
                <td>収入合計</td>
                {visiblePayload.seasons.map((season) => <td key={season.id} className="numeric">{amount(incomeTotals[season.id])}</td>)}
              </tr>
              {expenseRows.map((row) => (
                <tr key={row.kind}>
                  <td>{row.label}</td>
                  {visiblePayload.seasons.map((season) => (
                    <td key={season.id} className="numeric">{expenseAmount(row.values[season.id] || 0)}</td>
                  ))}
                </tr>
              ))}
              <tr className="totalRow expenseTotalRow">
                <td>費用合計</td>
                {visiblePayload.seasons.map((season) => <td key={season.id} className="numeric">{expenseAmount(expenseTotals[season.id])}</td>)}
              </tr>
              <tr className="netRow">
                <td>累積収支</td>
                {visiblePayload.seasons.map((season) => <td key={season.id} className="numeric">{amount(netTotals[season.id])}</td>)}
              </tr>
              <tr className="cashRow">
                <td>現金残高</td>
                {visiblePayload.seasons.map((season) => <td key={season.id} className="numeric">{amount(season.closing_balance)}</td>)}
              </tr>
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function FinanceStatementTable({
  statement,
  title,
}: {
  statement: FinanceStatement;
  title: string;
}) {
  return (
    <section className="statementBlock">
      <h3>{title}</h3>
      <table>
        <tbody>
          <tr className="sectionRow"><th colSpan={2}>収入</th></tr>
          {statement.income.length ? statement.income.map((line) => (
            <tr key={line.kind}>
              <td>{line.label}</td>
              <td>{amount(line.amount)}</td>
            </tr>
          )) : (
            <tr><td>収入なし</td><td>{amount(0)}</td></tr>
          )}
          <tr className="totalRow incomeTotalRow"><td>収入合計</td><td>{amount(statement.income_total)}</td></tr>
          <tr className="sectionRow"><th colSpan={2}>費用</th></tr>
          {statement.expenses.length ? statement.expenses.map((line) => (
            <tr key={line.kind}>
              <td>{line.label}</td>
              <td>{expenseAmount(line.amount)}</td>
            </tr>
          )) : (
            <tr><td>費用なし</td><td>{amount(0)}</td></tr>
          )}
          <tr className="totalRow expenseTotalRow"><td>費用合計</td><td>{expenseAmount(statement.expense_total)}</td></tr>
          <tr className="netRow"><td>純収支</td><td>{amount(statement.net)}</td></tr>
        </tbody>
      </table>
    </section>
  );
}

function MayActions({
  academy,
  busy,
  staff,
  onAcademyBudget,
  onStaffPlan,
}: {
  academy: ConsoleData['academy'];
  busy: boolean;
  staff: ConsoleData['staff'];
  onAcademyBudget: (annualBudget: number) => void;
  onStaffPlan: (role: string, count: number) => void;
}) {
  const [role, setRole] = useState(staff[0]?.role || 'sales');
  const [count, setCount] = useState('1');
  const [budget, setBudget] = useState('');

  return (
    <section className="mayActions">
      <p className="eventline">5月イベント: 来季スタッフ計画とアカデミー予算を設定できます。</p>
      <table>
        <thead>
          <tr><th>ポジション</th><th>現在の人数</th><th>入力した人数</th></tr>
        </thead>
        <tbody>
          {staff.map((item) => (
            <tr key={item.role}>
              <td>{item.role}</td>
              <td>{item.count}</td>
              <td>{item.input_count ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="inputGrid">
        <label>
          スタッフ区分
          <select
            value={role}
            onChange={(event) => {
              const nextRole = event.target.value;
              const nextStaff = staff.find((item) => item.role === nextRole);
              setRole(nextRole);
              if (nextStaff) setCount(String(nextStaff.input_count ?? nextStaff.count));
            }}
          >
            {['sales', 'hometown', 'operations', 'promotion', 'administration', 'topteam', 'academy'].map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          来季目標人数
          <span className="moneyField">
            <FormattedIntegerInput value={count} onValueChange={setCount} />
            <button disabled={busy} onClick={() => onStaffPlan(role, Math.max(1, Number(count) || 1))} type="button">保存</button>
          </span>
        </label>
        <label>
          翌年度アカデミー予算
          <span className="moneyField">
            <FormattedIntegerInput value={budget} onValueChange={setBudget} />
            <button disabled={busy} onClick={() => onAcademyBudget(Math.max(0, Number(budget) || 0))} type="button">保存</button>
          </span>
        </label>
      </div>
      <dl className="academyConfirm">
        <dt>保存済み翌年度アカデミー予算</dt>
        <dd>{amount(academy.next_annual_budget)}</dd>
      </dl>
    </section>
  );
}

function BudgetEventActions({
  busy,
  event,
  onBudgetEvent,
}: {
  busy: boolean;
  event: NonNullable<ConsoleData['event_budget']>;
  onBudgetEvent: (key: string, amount: number) => void;
}) {
  const [budget, setBudget] = useState('');

  return (
    <section className="eventActions">
      <p className="eventline">
        {event.key === 'additional_reinforcement'
          ? '12月イベント: シーズン中の移籍ウインドウ-追加強化費を設定できます'
          : `${event.title}: ${event.input_label}を設定できます。`}
      </p>
      <div className="inputGrid">
        <label>
          {event.input_label}
          <span className="moneyField">
            <FormattedIntegerInput value={budget} onValueChange={setBudget} />
            <button
              disabled={busy}
              onClick={() => onBudgetEvent(event.key, Math.max(0, Number(budget) || 0))}
              type="button"
            >
              保存
            </button>
          </span>
        </label>
      </div>
      <dl className="savedEventValue">
        <dt>入力中の数値</dt>
        <dd>{budget.trim() === '' ? '-' : amount(Number(budget))}</dd>
        <dt>保存済みの数値</dt>
        <dd>{amount(event.saved_amount)}</dd>
      </dl>
    </section>
  );
}

function SummaryTables({
  consoleData,
  standings,
}: {
  consoleData: ConsoleData | null;
  standings: PlayState['standings'];
}) {
  return (
    <section className="summaryGrid">
      <article className="pane metricPane">
        <h3>財務サマリ</h3>
        <dl>
          <dt>残高</dt><dd>{amount(consoleData?.finance.balance)}</dd>
          <dt>直近収入</dt><dd>{amount(consoleData?.finance.latest_income)}</dd>
          <dt>直近費用</dt><dd>{expenseAmount(consoleData?.finance.latest_expense)}</dd>
        </dl>
      </article>
      <article className="pane metricPane">
        <h3>次の試合</h3>
        <table>
          <tbody>
            {(consoleData?.fixtures || [])
              .filter((fixture) => fixture.status !== 'played')
              .slice(0, 3)
              .map((fixture) => (
              <tr key={fixture.id}>
                <td>{fixture.month}</td>
                <td>{fixture.is_bye ? 'bye' : fixture.home ? 'H' : 'A'}</td>
                <td>{fixture.opponent || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
      <article className="pane metricPane">
        <h3>順位表</h3>
        <table>
          <tbody>
            {standings.slice(0, 5).map((row) => (
              <tr key={row.club_id}>
                <td>{row.rank}</td>
                <td>{row.club_name}</td>
                <td>{row.points}pt</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </section>
  );
}
