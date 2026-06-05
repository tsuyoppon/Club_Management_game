'use client';

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';

type Room = {
  id: string;
  game_id: string;
  status: 'lobby' | 'active';
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

type PlayState = {
  room: { id: string; invite_code: string; status: string };
  game_id: string;
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
    gd: number;
    points: number;
  }>;
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
  sponsor: { count: number; confirmed_next: number };
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
  Distribution_revenue?: number;
  Business_operation_cost?: number;
  staff_cost?: number;
  admin_cost?: number;
  [key: string]: string | number | undefined;
};

type PublicDisclosure = {
  id: string;
  season_id: string;
  disclosure_type: string;
  disclosure_month: number;
  disclosed_data: { clubs?: FinancialSummaryClub[] };
  created_at: string;
};

type ConsoleSection = 'Turn' | 'Matches' | 'Table' | 'Finance' | 'Fans' | 'Sponsors' | 'Staff' | 'Disclosures';
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

const defaultClubs = ['東京ユナイテッド', '大阪イレブン', '福岡アローズ'];
const consoleSections: ConsoleSection[] = ['Turn', 'Matches', 'Table', 'Finance', 'Fans', 'Sponsors', 'Staff', 'Disclosures'];
const moneyKeys = new Set([
  'sales_expense',
  'promo_expense',
  'hometown_expense',
  'next_home_promo',
  'additional_reinforcement',
  'reinforcement_budget',
]);

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

function count(value: number | null | undefined) {
  if (value === null || value === undefined) return '-';
  return Math.round(value).toLocaleString('ja-JP');
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
  const [financialDisclosure, setFinancialDisclosure] = useState<PublicDisclosure | null>(null);
  const [stage, setStage] = useState<'entry' | 'lobby' | 'console'>('entry');
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
    setStage(nextRoom.status === 'active' ? 'console' : 'lobby');
    return nextRoom;
  }, []);

  const loadFinancialDisclosure = useCallback(async (seasonId: string) => {
    try {
      return await api<PublicDisclosure>(`/api/seasons/${seasonId}/disclosures/financial_summary`);
    } catch {
      return null;
    }
  }, []);

  const loadPlay = useCallback(async (gameId: string) => {
    const nextPlay = await api<PlayState>(`/api/games/${gameId}/play-state`);
    setPlay(nextPlay);
    if (nextPlay.season) {
      setFinancialDisclosure(await loadFinancialDisclosure(nextPlay.season.id));
    } else {
      setFinancialDisclosure(null);
    }
    if (nextPlay.self.club_id) {
      const nextConsole = await api<ConsoleData>(
        `/api/games/${gameId}/clubs/${nextPlay.self.club_id}/turn-console`,
      );
      setConsoleData(nextConsole);
    } else {
      setConsoleData(null);
    }
  }, [loadFinancialDisclosure]);

  useEffect(() => {
    api<{ rooms: Array<{ id: string; status: string }> }>('/api/me')
      .then((me) => {
        const lastRoom = me.rooms[me.rooms.length - 1];
        if (lastRoom) return loadRoom(lastRoom.id);
        return null;
      })
      .catch(() => undefined);
  }, [loadRoom]);

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
          busy={busy}
          clubNames={clubNames}
          displayName={displayName}
          inviteCode={inviteCode}
          roomName={roomName}
          onClubNames={setClubNames}
          onCreate={createRoom}
          onDisplayName={setDisplayName}
          onInviteCode={setInviteCode}
          onJoin={joinRoom}
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
          draftState={draftState}
          formValues={formValues}
          play={play}
          onAck={ackTurn}
          onCommit={commitDecision}
          onFormValue={(key, value) => {
            setFormValues((current) => ({ ...current, [key]: value }));
            setDraftDirty(true);
          }}
          onAcademyBudget={saveAcademyBudget}
          onBudgetEvent={saveBudgetEvent}
          onHostAction={hostAction}
          onHostUncommit={hostUncommit}
          onStaffPlan={saveStaffPlan}
        />
      ) : null}
    </main>
  );
}

function Entry({
  busy,
  clubNames,
  displayName,
  inviteCode,
  roomName,
  onClubNames,
  onCreate,
  onDisplayName,
  onInviteCode,
  onJoin,
  onRoomName,
}: {
  busy: boolean;
  clubNames: string[];
  displayName: string;
  inviteCode: string;
  roomName: string;
  onClubNames: (value: string[]) => void;
  onCreate: (event: FormEvent) => void;
  onDisplayName: (value: string) => void;
  onInviteCode: (value: string) => void;
  onJoin: (event: FormEvent) => void;
  onRoomName: (value: string) => void;
}) {
  return (
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

function Console({
  busy,
  consoleData,
  financialDisclosure,
  draftState,
  formValues,
  play,
  onAck,
  onAcademyBudget,
  onBudgetEvent,
  onCommit,
  onFormValue,
  onHostAction,
  onHostUncommit,
  onStaffPlan,
}: {
  busy: boolean;
  consoleData: ConsoleData | null;
  financialDisclosure: PublicDisclosure | null;
  draftState: string;
  formValues: Record<string, string>;
  play: PlayState | null;
  onAck: () => void;
  onAcademyBudget: (annualBudget: number) => void;
  onBudgetEvent: (key: string, amount: number) => void;
  onCommit: () => void;
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
    if (turnState === 'resolved') return acked ? '全員のack後、ホストが次ターンへ進めます。' : '結果を確認してackしてください。';
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
                          <input
                            inputMode="decimal"
                            min="0"
                            step={input.key === 'sales_allocation_new' ? '0.01' : '100000'}
                            type="number"
                            value={formValues[input.key] || ''}
                            onChange={(event) => onFormValue(input.key, event.target.value)}
                          />
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
            consoleData={consoleData}
            financialDisclosure={financialDisclosure}
            section={activeSection}
            selfClubId={selfClubId}
            standings={play?.standings || []}
          />
        )}
      </section>
      <aside className="rightStack">
        <article className="pane progressPane">
          <h2>対戦進捗</h2>
          <p className="muted progressHint">
            {turnState === 'resolved' ? '全クラブのack後にadvanceできます。' : '全クラブのcommit後にlockできます。'}
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
                <button key={action} disabled={hostActionDisabled(action)} onClick={() => onHostAction(action)}>{action}</button>
              ))}
            </div>
          ) : <p className="muted">ホストが締切と解決を進めます。</p>}
        </article>
      </aside>
    </section>
  );
}

function ConsoleSectionPanel({
  consoleData,
  financialDisclosure,
  section,
  selfClubId,
  standings,
}: {
  consoleData: ConsoleData | null;
  financialDisclosure: PublicDisclosure | null;
  section: Exclude<ConsoleSection, 'Turn'>;
  selfClubId: string | null;
  standings: PlayState['standings'];
}) {
  const titleMap: Record<Exclude<ConsoleSection, 'Turn'>, string> = {
    Matches: '試合',
    Table: '順位表',
    Finance: '財務',
    Fans: 'ファン',
    Sponsors: 'スポンサー',
    Staff: 'スタッフ',
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
      {!consoleData && section !== 'Disclosures' ? <p className="muted">担当クラブの情報を待機中です。</p> : null}
      {consoleData && section === 'Matches' ? (
        <table>
          <thead>
            <tr><th>月</th><th>H/A</th><th>相手</th><th>状態</th><th>結果</th><th>入場者数</th><th>天気</th></tr>
          </thead>
          <tbody>
            {consoleData.fixtures.map((fixture) => (
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
      ) : null}
      {section === 'Table' ? (
        <table>
          <thead>
            <tr><th>順位</th><th>クラブ</th><th>試合</th><th>得失点</th><th>勝点</th></tr>
          </thead>
          <tbody>
            {standings.map((row) => (
              <tr key={row.club_id}>
                <td>{row.rank}</td>
                <td>{row.club_name}</td>
                <td>{row.played}</td>
                <td>{row.gd}</td>
                <td>{row.points}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {consoleData && section === 'Finance' ? (
        <FinancePanel report={consoleData.finance.report} />
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
      {section === 'Disclosures' ? (
        <FinancialDisclosurePanel disclosure={financialDisclosure} selfClubId={selfClubId} />
      ) : null}
    </article>
  );
}

function disclosureValue(row: FinancialSummaryClub, keys: string[]) {
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
        <table>
          <thead>
            <tr>
              <th>クラブ</th>
              <th>収入合計</th>
              <th>費用合計</th>
              <th>純利益</th>
              <th>期末残高</th>
              <th>スポンサー</th>
              <th>配分・賞金</th>
              <th>事業運営費</th>
              <th>人件費</th>
            </tr>
          </thead>
          <tbody>
            {clubs.map((club) => (
              <tr key={club.club_id} className={club.club_id === selfClubId ? 'selfRow' : ''}>
                <td>{club.club_name}</td>
                <td className="numeric">{amount(disclosureValue(club, ['total_revenue']))}</td>
                <td className="numeric">{amount(disclosureValue(club, ['total_expense', 'total expense']))}</td>
                <td className="numeric">{amount(disclosureValue(club, ['net_income']))}</td>
                <td className="numeric">{amount(disclosureValue(club, ['ending_balance']))}</td>
                <td className="numeric">{amount(disclosureValue(club, ['Sponsor_revenue']))}</td>
                <td className="numeric">{amount(disclosureValue(club, ['Distribution_revenue']))}</td>
                <td className="numeric">{amount(disclosureValue(club, ['Business_operation_cost']))}</td>
                <td className="numeric">{amount(disclosureValue(club, ['staff_cost']))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FinancePanel({ report }: { report: FinanceReport }) {
  const period = report.period.month_name
    ? `Season ${report.period.season_number} / ${report.period.month_name}`
    : `Season ${report.period.season_number} / 未確定`;

  return (
    <section className="financePanel">
      <div className="financePeriod">
        <strong>{period}</strong>
        <span>期首 {amount(report.opening_balance)} / 期末 {amount(report.closing_balance)}</span>
      </div>
      <div className="financeStatements">
        <FinanceStatementTable statement={report.monthly} title="今月の収支" />
        <FinanceStatementTable statement={report.cumulative} title="今シーズン累積の収支" />
      </div>
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
          <tr className="totalRow"><td>収入合計</td><td>{amount(statement.income_total)}</td></tr>
          <tr className="sectionRow"><th colSpan={2}>費用</th></tr>
          {statement.expenses.length ? statement.expenses.map((line) => (
            <tr key={line.kind}>
              <td>{line.label}</td>
              <td>{amount(line.amount)}</td>
            </tr>
          )) : (
            <tr><td>費用なし</td><td>{amount(0)}</td></tr>
          )}
          <tr className="totalRow"><td>費用合計</td><td>{amount(statement.expense_total)}</td></tr>
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
            <input min="1" type="number" value={count} onChange={(event) => setCount(event.target.value)} />
            <button disabled={busy} onClick={() => onStaffPlan(role, Math.max(1, Number(count) || 1))} type="button">保存</button>
          </span>
        </label>
        <label>
          翌年度アカデミー予算
          <span className="moneyField">
            <input min="0" step="100000" type="number" value={budget} onChange={(event) => setBudget(event.target.value)} />
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
      <p className="eventline">{event.title}: {event.input_label}を設定できます。</p>
      <div className="inputGrid">
        <label>
          {event.input_label}
          <span className="moneyField">
            <input
              min="0"
              step="100000"
              type="number"
              value={budget}
              onChange={(changeEvent) => setBudget(changeEvent.target.value)}
            />
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
          <dt>直近費用</dt><dd>{amount(consoleData?.finance.latest_expense)}</dd>
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
