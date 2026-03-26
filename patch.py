import os

html_file = "index.html"
with open(html_file, "r", encoding="utf-8") as f:
    content = f.read()

# We want to replace everything from "function Dashboard(" to the end of the App component.
# Actually, replacing from "// ─── Dashboard ───" to "ReactDOM.createRoot" is safest.
start_marker = "// ─── Dashboard ────────────────────────────────────────────────────────────────"
end_marker = "ReactDOM.createRoot(document.getElementById('root')).render(<App />);"

if start_marker not in content or end_marker not in content:
    print("Markers not found!")
    exit(1)

pre_content = content.split(start_marker)[0]
post_content = content.split(end_marker)[1]

new_react_code = """// ─── Dashboard ────────────────────────────────────────────────────────────────
function Dashboard({ streaks, onCheckIn, setView, setShowCreate, showToast, totalXp, user }) {
  const todayStr = today();
  const completedToday = streaks.filter(s => s.history[todayStr]).length;
  const pct = streaks.length ? Math.round((completedToday / streaks.length) * 100) : 0;
  const lvl = levelInfo(totalXp);
  const atRisk = streaks.filter(s => !s.history[todayStr] && calcStreak(s.history) > 0);

  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  };

  return (
    <div>
      <div className="page-header">
        <div className="page-title">{greeting()}, {user?.username} 👋</div>
        <div className="page-subtitle">{new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}</div>
      </div>

      {atRisk.length > 0 && (
        <div className="notif-bar">
          ⚠️ <strong>{atRisk.length} streak{atRisk.length > 1 ? 's' : ''} at risk:</strong> {atRisk.map(s => s.title).join(', ')} — check in now!
        </div>
      )}

      <div className="stats-row card-anim">
        <div className="stat-card primary">
          <div className="stat-icon">📅</div>
          <div className="stat-label">Today's Progress</div>
          <div className="stat-value">{pct}%</div>
          <div className="stat-sub">{completedToday}/{streaks.length} habits done</div>
        </div>
        <div className="stat-card accent">
          <div className="stat-icon">🔥</div>
          <div className="stat-label">Best Streak</div>
          <div className="stat-value">{streaks.length ? Math.max(...streaks.map(s => calcStreak(s.history))) : 0}</div>
          <div className="stat-sub">days in a row</div>
        </div>
        <div className="stat-card success">
          <div className="stat-icon">⚡</div>
          <div className="stat-label">Total XP</div>
          <div className="stat-value">{totalXp.toLocaleString()}</div>
          <div className="stat-sub">Level {lvl.level} · {lvl.name}</div>
        </div>
        <div className="stat-card gold">
          <div className="stat-icon">🏆</div>
          <div className="stat-label">Habits Tracked</div>
          <div className="stat-value">{streaks.length}</div>
          <div className="stat-sub">{BADGES.filter(b => b.condition(streaks, totalXp)).length} badges earned</div>
        </div>
      </div>

      <div className="section-header">
        <div className="section-title">Today's Habits</div>
        <button className="section-action" onClick={() => setShowCreate(true)}>+ Add Habit</button>
      </div>

      {streaks.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🌱</div>
          <div className="empty-title">No habits yet</div>
          <div className="empty-sub">Start your streak journey today!</div>
          <button className="btn btn-primary" style={{ width: 'auto', padding: '12px 28px' }} onClick={() => setShowCreate(true)}>Create First Habit</button>
        </div>
      ) : (
        <div className="streak-grid">
          {streaks.map((s, i) => {
            const cur = calcStreak(s.history);
            const done = s.history[todayStr];
            return (
              <div key={s.id} className={`streak-card card-anim ${done ? 'completed' : ''}`}
                style={{ animationDelay: `${i * 0.05}s` }}>
                <div className="streak-card-header">
                  <div className="streak-icon-wrap" style={{ background: s.color + '22' }}>{s.icon}</div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    {cur >= 7 && <span className="streak-badge" style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>🔥 HOT</span>}
                    {done && <span className="streak-badge" style={{ background: 'var(--success-dim)', color: 'var(--success)' }}>✓ DONE</span>}
                  </div>
                </div>
                <div className="streak-title">{s.title}</div>
                <div className="streak-category">{s.category} · {s.frequency}</div>
                <div className="streak-stats-row">
                  <div className="streak-stat">
                    <div className="streak-stat-val" style={{ color: 'var(--accent)' }}>{cur}</div>
                    <div className="streak-stat-lbl">Current 🔥</div>
                  </div>
                  <div className="streak-stat-sep" />
                  <div className="streak-stat">
                    <div className="streak-stat-val" style={{ color: 'var(--gold)' }}>{calcLongest(s.history)}</div>
                    <div className="streak-stat-lbl">Best 🏆</div>
                  </div>
                  <div className="streak-stat-sep" />
                  <div className="streak-stat">
                    <div className="streak-stat-val" style={{ color: 'var(--primary)' }}>
                      {Math.round((Object.values(s.history).filter(Boolean).length / Math.max(Object.keys(s.history).length, 1)) * 100)}%
                    </div>
                    <div className="streak-stat-lbl">Rate</div>
                  </div>
                </div>
                <div className="fire-row" style={{ marginBottom: 4 }}>
                  {Array.from({ length: 7 }, (_, i2) => {
                    const key = dateKey(6 - i2);
                    return <div key={i2} className={`fire-dot ${s.history[key] ? 'active' : ''}`} title={key} />;
                  })}
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 6 }}>last 7 days</span>
                </div>
                <button
                  className={`checkin-btn ${done ? 'done' : 'pending'}`}
                  onClick={(e) => { e.stopPropagation(); if (!done) onCheckIn(s); }}
                  style={done ? { animation: 'checkBounce 0.4s ease' } : {}}
                >
                  {done ? '✅ Completed today!' : '☐ Mark complete'}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {streaks.length > 0 && (
        <div className="heatmap-wrap">
          <div className="section-header">
            <div className="section-title">Activity Heatmap</div>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Last 20 weeks</span>
          </div>
          <HeatMap history={(() => {
            const merged = {};
            for (let i = 0; i <= 140; i++) {
              const key = dateKey(i);
              const done = streaks.filter(s => s.history[key]).length;
              merged[key] = done > 0;
            }
            return merged;
          })()} />
        </div>
      )}
    </div>
  );
}

// ─── Habits View ──────────────────────────────────────────────────────────────
function HabitsView({ streaks, onDelete, onFreeze, setShowCreate, showToast }) {
  const [selected, setSelected] = useState(null);

  return (
    <div>
      <div className="page-header">
        <div className="page-title">My Habits 📋</div>
        <div className="page-subtitle">Manage and track all your habits</div>
      </div>

      <div className="section-header">
        <div className="section-title">{streaks.length} Active Habit{streaks.length !== 1 ? 's' : ''}</div>
        <button className="section-action" onClick={() => setShowCreate(true)}>+ New Habit</button>
      </div>

      {streaks.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🎯</div>
          <div className="empty-title">No habits yet</div>
          <div className="empty-sub">Build your first habit to start your streak journey!</div>
          <button className="btn btn-primary" style={{ width: 'auto', padding: '12px 28px' }} onClick={() => setShowCreate(true)}>Create Habit</button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {streaks.map((s, i) => {
            const cur = calcStreak(s.history);
            const rate = Math.round((Object.values(s.history).filter(Boolean).length / Math.max(Object.keys(s.history).length, 1)) * 100);
            return (
              <div key={s.id} className="chart-wrap card-anim" style={{ animationDelay: `${i * 0.05}s`, cursor: 'pointer' }}
                onClick={() => setSelected(s)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <div className="streak-icon-wrap" style={{ background: s.color + '22', width: 48, height: 48, fontSize: 24 }}>{s.icon}</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-display)' }}>{s.title}</span>
                      <span style={{ fontSize: 11, background: 'var(--surface2)', color: 'var(--text-muted)', padding: '2px 8px', borderRadius: 99, border: '1px solid var(--border)' }}>{s.category}</span>
                      {s.history[today()] && <span style={{ fontSize: 11, background: 'var(--success-dim)', color: 'var(--success)', padding: '2px 8px', borderRadius: 99 }}>✓ Today</span>}
                      {s.freezesLeft > 0 && <span style={{ fontSize: 11, background: 'rgba(96,180,255,0.1)', color: '#60b4ff', padding: '2px 8px', borderRadius: 99 }}>🧊 {s.freezesLeft}</span>}
                    </div>
                    <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
                      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>🔥 <strong style={{ color: 'var(--accent)' }}>{cur}</strong> streak</span>
                      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>📊 <strong style={{ color: 'var(--text)' }}>{rate}%</strong> rate</span>
                      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>⏰ {s.reminderTime}</span>
                    </div>
                    <div style={{ height: 4, background: 'var(--border)', borderRadius: 99, marginTop: 10, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: rate + '%', background: s.color, borderRadius: 99, transition: 'width 0.8s ease' }} />
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Last 7 days</div>
                    <div className="fire-row" style={{ justifyContent: 'flex-end' }}>
                      {Array.from({ length: 7 }, (_, idx) => {
                        const key = dateKey(6 - idx);
                        return <div key={idx} className={`fire-dot ${s.history[key] ? 'active' : ''}`} />;
                      })}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {selected && (
        <DetailModal streak={selected} onClose={() => setSelected(null)} onDelete={onDelete} onFreeze={onFreeze} />
      )}
    </div>
  );
}

// ─── Root App ─────────────────────────────────────────────────────────────────
function App() {
  const [streaks, setStreaks] = useState([]);
  const [view, setView] = useState('dashboard');
  const [showCreate, setShowCreate] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem('sf_theme') || 'dark');
  const [toast, setToast] = useState(null);
  
  // Auth state
  const [token, setToken] = useState(() => localStorage.getItem('sf_token') || null);
  const [user, setUser] = useState(null);
  const [authView, setAuthView] = useState('login');
  const [authForm, setAuthForm] = useState({ username: '', password: '' });
  const [authError, setAuthError] = useState('');

  const showToast = useCallback((msg) => { setToast(msg); }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('sf_theme', theme);
  }, [theme]);

  const fetchStreaks = async () => {
    if (!token) return;
    try {
      const res = await fetch('/api/streaks', {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setStreaks(data);
      } else if (res.status === 401) {
        logout();
      }
    } catch(e) { console.error('Failed to fetch streaks', e); }
  };

  const fetchUser = async () => {
    if (!token) return;
    try {
      const res = await fetch('/users/me', {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
      } else { logout(); }
    } catch(e) { console.error('Failed to fetch user', e); }
  };

  useEffect(() => {
    if (token) {
      localStorage.setItem('sf_token', token);
      fetchUser();
      fetchStreaks();
    } else {
      localStorage.removeItem('sf_token');
      setUser(null);
      setStreaks([]);
    }
  }, [token]);

  const handleAuth = async () => {
    setAuthError('');
    if (!authForm.username || !authForm.password) {
      setAuthError('Please fill in all fields'); return;
    }
    
    try {
      const params = new URLSearchParams();
      params.append('username', authForm.username);
      params.append('password', authForm.password);

      const endpoint = authView === 'login' ? '/token' : '/register';
      const body_data = authView === 'login' ? params : JSON.stringify({ username: authForm.username, password: authForm.password });
      const headers = authView === 'login' ? { 'Content-Type': 'application/x-www-form-urlencoded' } : { 'Content-Type': 'application/json' };
      
      const res = await fetch(endpoint, { method: 'POST', headers, body: body_data });
      const data = await res.json();
      if (res.ok) {
        setToken(data.access_token);
        setAuthForm({ username: '', password: '' });
      } else {
        setAuthError(data.detail || 'Authentication failed');
      }
    } catch (e) { setAuthError('Network error'); }
  };

  const logout = () => { setToken(null); };

  const addStreak = async (newStreak) => {
    try {
      const res = await fetch('/api/streaks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(newStreak)
      });
      if (res.ok) {
        fetchStreaks();
        showToast({ icon: '🌱', text: 'New habit created! Start your streak today.' });
      }
    } catch(e) { console.error('Failed to add streak', e); }
  };

  const checkIn = async (streak) => {
    const todayStr = today();
    const newHistory = { ...streak.history, [todayStr]: true };
    try {
      const res = await fetch(`/api/streaks/${streak.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ...streak, history: newHistory })
      });
      if (res.ok) {
        setStreaks(prev => prev.map(s => s.id === streak.id ? {...s, history: newHistory} : s));
        showToast({ icon: '🔥', text: '+15 XP — Keep it up!' });
      }
    } catch(e) { console.error('Failed to check in', e); }
  };

  const del = async (id) => {
    try {
      const res = await fetch(`/api/streaks/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setStreaks(prev => prev.filter(s => s.id !== id));
        showToast({ icon: '🗑️', text: 'Habit deleted' });
      }
    } catch(e) { console.error('Failed to delete', e); }
  };

  const freeze = async (id) => {
    const streak = streaks.find(s => s.id === id);
    if (!streak) return;
    const newHistory = { ...streak.history, [today()]: true };
    try {
      const res = await fetch(`/api/streaks/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ...streak, history: newHistory, freezesLeft: streak.freezesLeft - 1 })
      });
      if (res.ok) {
        fetchStreaks();
        showToast({ icon: '🧊', text: 'Streak freeze used! Day saved.' });
      }
    } catch(e) { console.error('Failed to freeze', e); }
  };

  // --- Auth View UI ---
  if (!token || !user) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: 'var(--bg)' }}>
        <div className="chart-wrap" style={{ width: 400, maxWidth: '90vw' }}>
          <div className="logo" style={{ justifyContent: 'center', marginBottom: 30 }}>
            <div className="logo-icon float">🔥</div>
            <span className="logo-text" style={{ fontSize: 24 }}>StreakForge</span>
          </div>
          <div className="page-title" style={{ textAlign: 'center', marginBottom: 20 }}>
            {authView === 'login' ? 'Welcome Back' : 'Create Account'}
          </div>
          {authError && <div style={{ color: 'var(--accent)', background: 'var(--accent-dim)', padding: '10px', borderRadius: '8px', marginBottom: '16px', fontSize: 13, textAlign: 'center' }}>{authError}</div>}
          <div className="form-group">
            <label className="form-label">Username</label>
            <input className="form-input" value={authForm.username} onChange={e => setAuthForm(f => ({...f, username: e.target.value}))} />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input className="form-input" type="password" value={authForm.password} onChange={e => setAuthForm(f => ({...f, password: e.target.value}))} 
              onKeyDown={e => e.key === 'Enter' && handleAuth()} />
          </div>
          <button className="btn btn-primary" style={{ width: '100%' }} onClick={handleAuth}>
            {authView === 'login' ? 'Log In' : 'Sign Up'}
          </button>
          <div style={{ textAlign: 'center', marginTop: 16, fontSize: 13, color: 'var(--text-muted)' }}>
            {authView === 'login' ? "Don't have an account? " : "Already have an account? "}
            <span style={{ color: 'var(--primary)', cursor: 'pointer', fontWeight: 600 }} onClick={() => setAuthView(authView === 'login' ? 'register' : 'login')}>
              {authView === 'login' ? 'Sign up' : 'Log in'}
            </span>
          </div>
        </div>
      </div>
    );
  }

  const totalXp = streaks.reduce((acc, s) => {
    const done = Object.values(s.history).filter(Boolean).length;
    return acc + done * 15;
  }, 0);

  const navItems = [
    { id: 'dashboard', icon: '⚡', label: 'Dashboard' },
    { id: 'habits', icon: '📋', label: 'My Habits' },
    { id: 'analytics', icon: '📊', label: 'Analytics' },
    { id: 'achievements', icon: '🏆', label: 'Achievements' },
    { id: 'coach', icon: '🧠', label: 'AI Coach' },
  ];

  const lvl = levelInfo(totalXp);
  const uncompleted = streaks.filter(s => !s.history[today()]).length;

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="logo">
          <div className="logo-icon float">🔥</div>
          <span className="logo-text">StreakForge</span>
        </div>

        {navItems.map(n => (
          <div key={n.id} className={`nav-item ${view === n.id ? 'active' : ''}`} onClick={() => setView(n.id)}>
            <span className="nav-icon">{n.icon}</span>
            <span>{n.label}</span>
            {n.id === 'habits' && uncompleted > 0 && <span className="nav-badge">{uncompleted}</span>}
          </div>
        ))}
        
        <div className="nav-item" onClick={logout} style={{ marginTop: 'auto', marginBottom: 16 }}>
          <span className="nav-icon">🚪</span>
          <span>Logout</span>
        </div>

        <div className="theme-toggle" onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}>
          <span>{theme === 'dark' ? '☀️' : '🌙'}</span>
          <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
          <div className={`toggle-switch ${theme === 'light' ? 'on' : ''}`}><div className="toggle-knob" /></div>
        </div>

        <div className="user-card" style={{ marginTop: 0 }}>
          <div className="user-avatar">
            {user.username.charAt(0).toUpperCase()}
          </div>
          <div className="user-info">
            <div className="user-name">{user.username}</div>
            <div className="user-level">Lv.{lvl.level} {lvl.name}</div>
            <div className="xp-bar"><div className="xp-fill" style={{ width: `${(lvl.xpInLevel / lvl.xpNeeded) * 100}%` }} /></div>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="main">
        {view === 'dashboard' && <Dashboard streaks={streaks} onCheckIn={checkIn} setView={setView} setShowCreate={setShowCreate} showToast={showToast} totalXp={totalXp} user={user} />}
        {view === 'habits' && <HabitsView streaks={streaks} onDelete={del} onFreeze={freeze} setShowCreate={setShowCreate} showToast={showToast} />}
        {view === 'analytics' && <AnalyticsView streaks={streaks} />}
        {view === 'achievements' && <AchievementsView streaks={streaks} totalXp={totalXp} />}
        {view === 'coach' && <CoachView streaks={streaks} />}
      </main>

      {showCreate && <CreateModal onClose={() => setShowCreate(false)} onCreate={addStreak} />}
      {toast && <Toast msg={toast} onDone={() => setToast(null)} />}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
"""

with open(html_file, "w", encoding="utf-8") as f:
    f.write(pre_content + new_react_code + post_content)
print("SUCCESS")
