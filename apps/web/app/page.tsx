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
  finance: { balance: number; latest_closing_balance: number | null; latest_income: number | null; latest_expense: number | null };
  fanbase: { followers: number | null; fb_count: number | null };
  sponsor: { count: number; confirmed_next: number };
  staff: Array<{ role: string; count: number; next_count: number | null }>;
  fixtures: Array<{
    id: string;
    month: string;
    home: boolean;
    opponent: string | null;
    is_bye: boolean;
    status: string;
    score: [number, number] | null;
  }>;
  standings: PlayState['standings'];
};

const defaultClubs = ['東京ユナイテッド', '大阪イレブン', '福岡アローズ'];
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
  return `JPY ${Math.round(value).toLocaleString('ja-JP')}`;
}

function statusText(state: string | null | undefined) {
  if (!state) return '待機';
  if (state === 'collecting') return '入力受付';
  if (state === 'locked') return '締切';
  if (state === 'resolved') return '結果確認';
  return state;
}

export default function Home() {
  const [room, setRoom] = useState<Room | null>(null);
  const [play, setPlay] = useState<PlayState | null>(null);
  const [consoleData, setConsoleData] = useState<ConsoleData | null>(null);
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
    return work.catch((cause: Error) => setError(cause.message)).finally(() => setBusy(false));
  };

  const loadRoom = useCallback(async (roomId: string) => {
    const nextRoom = await api<Room>(`/api/rooms/${roomId}`);
    setRoom(nextRoom);
    setStage(nextRoom.status === 'active' ? 'console' : 'lobby');
    return nextRoom;
  }, []);

  const loadPlay = useCallback(async (gameId: string) => {
    const nextPlay = await api<PlayState>(`/api/games/${gameId}/play-state`);
    setPlay(nextPlay);
    if (nextPlay.self.club_id) {
      const nextConsole = await api<ConsoleData>(
        `/api/games/${gameId}/clubs/${nextPlay.self.club_id}/turn-console`,
      );
      setConsoleData(nextConsole);
    } else {
      setConsoleData(null);
    }
  }, []);

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
        loadPlay(room.game_id).catch((cause: Error) => setError(cause.message));
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
    const timer = window.setTimeout(() => saveDraft().catch((cause: Error) => setError(cause.message)), 700);
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
          onHostAction={hostAction}
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
  draftState,
  formValues,
  play,
  onAck,
  onAcademyBudget,
  onCommit,
  onFormValue,
  onHostAction,
  onStaffPlan,
}: {
  busy: boolean;
  consoleData: ConsoleData | null;
  draftState: string;
  formValues: Record<string, string>;
  play: PlayState | null;
  onAck: () => void;
  onAcademyBudget: (annualBudget: number) => void;
  onCommit: () => void;
  onFormValue: (key: string, value: string) => void;
  onHostAction: (action: string) => void;
  onStaffPlan: (role: string, count: number) => void;
}) {
  return (
    <section className="consoleGrid">
      <nav className="pane rail" aria-label="Console sections">
        {['Turn', 'Matches', 'Table', 'Finance', 'Fans', 'Sponsors', 'Staff', 'Disclosures'].map((item) => (
          <span key={item} className={item === 'Turn' ? 'active' : ''}>{item}</span>
        ))}
      </nav>
      <section className="centerStack">
        <article className="pane turnPane">
          <div className="paneTitle">
            <div>
              <p className="eyebrow">{play?.turn ? `Season ${play.turn.season_number} / ${play.turn.month_name}` : 'Season -'}</p>
              <h2>ターン入力</h2>
            </div>
            <span className="saveState">{draftState}</span>
          </div>
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
                  busy={busy}
                  staff={consoleData.staff}
                  onAcademyBudget={onAcademyBudget}
                  onStaffPlan={onStaffPlan}
                />
              ) : null}
              <div className="actionRow">
                <button className="primary" disabled={busy || !consoleData.available_inputs.length} onClick={onCommit}>
                  入力を確定
                </button>
                <span>state: {consoleData.decision.state || 'draft'}</span>
                {play?.turn?.state === 'resolved' ? (
                  <button disabled={busy} onClick={onAck}>結果を確認して ack</button>
                ) : null}
              </div>
            </>
          ) : <p className="muted">担当クラブの入力コンソールを待機中です。</p>}
        </article>
        <SummaryTables consoleData={consoleData} standings={play?.standings || []} />
      </section>
      <aside className="rightStack">
        <article className="pane progressPane">
          <h2>対戦進捗</h2>
          <table>
            <tbody>
              {(play?.clubs || []).map((club) => (
                <tr key={club.id}>
                  <td>{club.name}</td>
                  <td className={club.committed ? 'ok' : 'pending'}>{club.committed ? 'commit' : 'input'}</td>
                  <td className={club.acked ? 'ok' : 'pending'}>{club.acked ? 'ack' : '-'}</td>
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
                <button key={action} disabled={busy} onClick={() => onHostAction(action)}>{action}</button>
              ))}
            </div>
          ) : <p className="muted">ホストが締切と解決を進めます。</p>}
        </article>
      </aside>
    </section>
  );
}

function MayActions({
  busy,
  staff,
  onAcademyBudget,
  onStaffPlan,
}: {
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
      <div className="inputGrid">
        <label>
          スタッフ区分
          <select value={role} onChange={(event) => setRole(event.target.value)}>
            {['sales', 'hometown', 'operations', 'promotion', 'administration', 'topteam', 'academy'].map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          来季目標人数
          <span className="moneyField">
            <input min="1" type="number" value={count} onChange={(event) => setCount(event.target.value)} />
            <button disabled={busy} onClick={() => onStaffPlan(role, Math.max(1, Number(count) || 1))}>保存</button>
          </span>
        </label>
        <label>
          翌年度アカデミー予算
          <span className="moneyField">
            <input min="0" step="100000" type="number" value={budget} onChange={(event) => setBudget(event.target.value)} />
            <button disabled={busy} onClick={() => onAcademyBudget(Math.max(0, Number(budget) || 0))}>保存</button>
          </span>
        </label>
      </div>
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
            {(consoleData?.fixtures || []).map((fixture) => (
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
