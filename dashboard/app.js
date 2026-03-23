const API = '/api';

async function fetchPosts() {
  const res = await fetch(`${API}/posts/today`);
  return res.json();
}

function scoreClass(score) {
  if (score === null || score === undefined) return 'score-none';
  if (score >= 9.5) return 'score-high';
  if (score >= 7.5) return 'score-mid';
  return 'score-low';
}

function barClass(val) {
  if (val >= 9) return '';
  if (val >= 7) return 'mid';
  return 'low';
}

function cardClass(status) {
  if (status === 'approved') return 'is-approved';
  if (status === 'below_target') return 'is-below-target';
  if (status === 'rejected') return 'is-rejected';
  return '';
}

function renderBreakdown(breakdown) {
  const LABELS = {
    hook_strength: 'Hook strength',
    tone_compliance: 'Tone compliance',
    data_specificity: 'Data specificity',
    pillar_alignment: 'Pillar alignment',
    funnel_stage_accuracy: 'Funnel accuracy',
    cta_quality: 'CTA quality',
    x_algorithm_optimization: 'Algo optimization',
  };

  const rows = Object.entries(breakdown).map(([k, v]) => {
    const pct = (v / 10) * 100;
    const cls = barClass(v);
    return `
      <div class="breakdown-row">
        <span class="breakdown-label">${LABELS[k] || k.replace(/_/g, ' ')}</span>
        <div class="breakdown-bar-track">
          <div class="breakdown-bar-fill ${cls}" style="width:${pct}%"></div>
        </div>
        <span class="breakdown-value">${v}/10</span>
      </div>`;
  }).join('');

  return `
    <details class="breakdown">
      <summary>Score breakdown</summary>
      <div class="breakdown-grid">${rows}</div>
    </details>`;
}

function renderPost(post) {
  const card = document.createElement('div');
  card.className = `post-card ${cardClass(post.status)}`;
  card.id = `card-${post.id}`;

  const scoreLabel = (post.score !== null && post.score !== undefined)
    ? `${post.score}/10`
    : '—';

  const scoreCls = scoreClass(post.score);

  let statusBadge = '';
  if (post.status === 'approved')     statusBadge = '<span class="status-badge status-approved">✓ Approved</span>';
  else if (post.status === 'below_target') statusBadge = '<span class="status-badge status-warn">⚠ Below target</span>';
  else if (post.status === 'rejected') statusBadge = '<span class="status-badge status-rejected">Rejected</span>';

  const isApproved = post.status === 'approved';
  const isRejected = post.status === 'rejected';

  const primaryActions = isApproved
    ? `<button class="btn-post" onclick="postTweet('${post.id}')">Post ↗</button>
       <button class="btn-cancel" onclick="cancelApproval('${post.id}')">Cancel</button>`
    : `${!isRejected ? `<button class="btn-approve" onclick="approve('${post.id}')">Approve</button>` : ''}
       <button class="btn-reject" onclick="reject('${post.id}')">${isRejected ? 'Rejected' : 'Reject'}</button>`;

  const regenHint = isApproved || isRejected ? '' : `<span class="action-hint">Edit re-scores · Regen replaces</span>`;

  card.innerHTML = `
    <div class="card-header">
      <span class="tag tag-pillar">${post.pillar}</span>
      <span class="tag tag-funnel">${post.funnel}</span>
      ${statusBadge}
      <span class="score-badge ${scoreCls}">${scoreLabel}</span>
    </div>
    <div class="edit-hint">Editing — click Save when done</div>
    <div class="post-text" id="text-${post.id}" contenteditable="false">${post.text}</div>
    <div class="card-actions">
      ${primaryActions}
      <button class="btn-copy" id="copy-btn-${post.id}" onclick="copyPost('${post.id}')">Copy</button>
      <button class="btn-edit" id="edit-btn-${post.id}" onclick="toggleEdit('${post.id}')">Edit</button>
      <button class="btn-regen" id="regen-btn-${post.id}" onclick="regenPost('${post.id}')">Regen</button>
      ${regenHint}
    </div>
    ${post.score_breakdown ? renderBreakdown(post.score_breakdown) : ''}
  `;
  return card;
}

async function approve(id) {
  await fetch(`${API}/posts/${id}/approve`, { method: 'POST' });
  render();
}

async function reject(id) {
  await fetch(`${API}/posts/${id}/reject`, { method: 'POST' });
  render();
}

async function cancelApproval(id) {
  await fetch(`${API}/posts/${id}/unapprove`, { method: 'POST' });
  render();
}

async function copyPost(id) {
  const el = document.getElementById(`text-${id}`);
  const text = el.innerText.trim();
  await navigator.clipboard.writeText(text);
  const btn = document.getElementById(`copy-btn-${id}`);
  btn.textContent = 'Copied!';
  setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
}

async function postTweet(id) {
  const el = document.getElementById(`text-${id}`);
  const text = el.innerText.trim();
  await navigator.clipboard.writeText(text);
  window.open('https://x.com/compose/tweet', '_blank');
}

async function regenPost(id) {
  const btn = document.getElementById(`regen-btn-${id}`);
  const card = document.getElementById(`card-${id}`);
  btn.disabled = true;
  btn.textContent = 'Regenning…';
  card.style.opacity = '0.5';

  await fetch(`${API}/posts/${id}/regen`, { method: 'POST' });

  // Poll regen status endpoint until done or error
  const poll = setInterval(async () => {
    try {
      const res = await fetch(`${API}/posts/${id}/regen/status`);
      const data = await res.json();
      if (data.status === 'done') {
        clearInterval(poll);
        render();
      } else if (data.status === 'error') {
        clearInterval(poll);
        btn.disabled = false;
        btn.textContent = 'Regen';
        card.style.opacity = '1';
        alert(`Regen failed: ${data.error || 'unknown error'}`);
      }
    } catch (e) {
      clearInterval(poll);
      btn.disabled = false;
      btn.textContent = 'Regen';
      card.style.opacity = '1';
    }
  }, 2000);
}

function toggleEdit(id) {
  const el = document.getElementById(`text-${id}`);
  const card = document.getElementById(`card-${id}`);
  const btn = document.getElementById(`edit-btn-${id}`);
  const isEditing = el.contentEditable === 'true';

  if (isEditing) {
    el.contentEditable = 'false';
    card.classList.remove('editing');
    btn.textContent = 'Edit';
    btn.className = 'btn-edit';

    const newText = el.innerText.trim();
    fetch(`${API}/posts/${id}/edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: newText }),
    }).then(() => setTimeout(render, 3000));
  } else {
    el.contentEditable = 'true';
    el.focus();
    card.classList.add('editing');
    btn.textContent = 'Save';
    btn.className = 'btn-save';
  }
}

function skipToday() {
  document.getElementById('skip-modal').style.display = 'flex';
}

async function confirmSkip() {
  document.getElementById('skip-modal').style.display = 'none';
  await fetch(`${API}/skip-today`, { method: 'POST' });
  render();
}

function cancelSkip() {
  document.getElementById('skip-modal').style.display = 'none';
}

async function render() {
  const container = document.getElementById('posts-container');
  container.innerHTML = '';

  let posts;
  try {
    posts = await fetchPosts();
  } catch (e) {
    container.innerHTML = '<div class="empty-state"><p>Could not connect to server. Is it running?</p></div>';
    return;
  }

  if (!posts.length) {
    container.innerHTML = '<div class="empty-state"><p>No posts ready yet. Check back after 7:00 AM PDT.</p></div>';
    return;
  }

  posts.forEach(post => container.appendChild(renderPost(post)));
}

// Tab switching
function switchTab(tab) {
  document.getElementById('tab-content-today').style.display = tab === 'today' ? '' : 'none';
  document.getElementById('tab-content-history').style.display = tab === 'history' ? '' : 'none';
  document.getElementById('tab-today').classList.toggle('active', tab === 'today');
  document.getElementById('tab-history').classList.toggle('active', tab === 'history');
  if (tab === 'history') renderHistory();
}

async function fetchHistory() {
  const res = await fetch('/api/performance');
  return res.json();
}

function renderHistoryCard(post) {
  const eng = post.actual_engagement;
  const engHtml = eng
    ? `<div class="eng-metrics">
        <span class="eng-stat"><strong>${eng.likes}</strong> likes</span>
        <span class="eng-stat"><strong>${eng.retweets}</strong> RTs</span>
        <span class="eng-stat"><strong>${eng.replies}</strong> replies</span>
        ${eng.impressions ? `<span class="eng-stat"><strong>${eng.impressions}</strong> impressions</span>` : ''}
       </div>`
    : '<div class="eng-pending">Metrics pending</div>';

  return `
    <div class="post-card history-card">
      <div class="card-header">
        <span class="tag tag-pillar">${post.pillar || ''}</span>
        <span class="tag tag-funnel">${post.funnel || ''}</span>
        <span class="score-badge ${scoreClass(post.score)}">${post.score}/10</span>
      </div>
      <div class="post-text-preview">${post.text}</div>
      ${engHtml}
    </div>`;
}

async function renderHistory() {
  const container = document.getElementById('history-container');
  container.innerHTML = '<div class="empty-state"><div class="spinner"></div><p>Loading history…</p></div>';

  let posts = await fetchHistory();
  if (!posts.length) {
    container.innerHTML = '<div class="empty-state"><p>No published posts yet.</p></div>';
    return;
  }

  // Filter
  const pillar = document.getElementById('filter-pillar').value;
  if (pillar) posts = posts.filter(p => p.pillar === pillar);

  // Sort
  const sortBy = document.getElementById('sort-by').value;
  if (sortBy === 'score') posts.sort((a, b) => (b.score || 0) - (a.score || 0));
  else if (sortBy === 'engagement') {
    posts.sort((a, b) => {
      const engA = a.actual_engagement ? a.actual_engagement.likes + a.actual_engagement.retweets * 20 : 0;
      const engB = b.actual_engagement ? b.actual_engagement.likes + b.actual_engagement.retweets * 20 : 0;
      return engB - engA;
    });
  }

  container.innerHTML = posts.map(renderHistoryCard).join('');
}

// Playbook refresh
let refreshPollInterval = null;

function startRefresh() {
  document.getElementById('refresh-confirm-modal').style.display = 'flex';
}

async function confirmRefreshStart() {
  document.getElementById('refresh-confirm-modal').style.display = 'none';
  const btn = document.getElementById('refresh-btn');
  btn.disabled = true;
  btn.textContent = 'Refreshing…';
  await fetch('/api/playbooks/refresh', { method: 'POST' });
  refreshPollInterval = setInterval(pollRefreshStatus, 2000);
}

function cancelRefreshStart() {
  document.getElementById('refresh-confirm-modal').style.display = 'none';
}

async function pollRefreshStatus() {
  const res = await fetch('/api/playbooks/refresh/status');
  const status = await res.json();

  if (!status.done) return;

  clearInterval(refreshPollInterval);
  refreshPollInterval = null;

  const btn = document.getElementById('refresh-btn');
  btn.disabled = false;
  btn.textContent = 'Refresh Playbooks';

  if (status.error) {
    alert('Refresh failed: ' + status.error);
    return;
  }

  if (status.written) {
    alert('Playbooks already updated.');
    return;
  }

  showRefreshModal(status.diffs);
}

function showRefreshModal(diffs) {
  const diffEl = document.getElementById('refresh-diff');
  diffEl.innerHTML = Object.entries(diffs).map(([key, text]) => `
    <div class="diff-section">
      <div class="diff-label">${key} playbook</div>
      <pre class="diff-text">${escapeHtml(text.trim())}</pre>
    </div>
  `).join('');
  document.getElementById('refresh-modal').style.display = 'flex';
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function confirmRefresh() {
  document.getElementById('refresh-modal').style.display = 'none';
  await fetch('/api/playbooks/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirm: true }),
  });
  alert('Playbooks updated successfully.');
}

function cancelRefresh() {
  document.getElementById('refresh-modal').style.display = 'none';
}

// Generate new posts
let generatePollInterval = null;

async function generatePosts() {
  const btn = document.getElementById('generate-btn');
  const status = document.getElementById('generate-status');
  btn.disabled = true;
  btn.textContent = 'Generating…';
  status.textContent = 'Fetching trends and drafting posts — takes about 30 seconds';

  const res = await fetch('/api/posts/generate', { method: 'POST' });
  if (!res.ok) {
    btn.disabled = false;
    btn.textContent = 'Generate New Posts';
    status.textContent = 'Already running — please wait.';
    return;
  }
  generatePollInterval = setInterval(pollGenerateStatus, 3000);
}

async function pollGenerateStatus() {
  const res = await fetch('/api/posts/generate/status');
  const data = await res.json();
  if (!data.done) return;

  clearInterval(generatePollInterval);
  generatePollInterval = null;

  const btn = document.getElementById('generate-btn');
  const status = document.getElementById('generate-status');
  btn.disabled = false;
  btn.textContent = 'Generate New Posts';

  if (data.error) {
    status.textContent = 'Error: ' + data.error;
    return;
  }
  status.textContent = 'Drafts 8 posts · scores each · surfaces top 5';
  render();
}

async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    const cfg = await res.json();
    document.getElementById('header-handle').textContent = '@' + cfg.handle;
    document.getElementById('header-avatar').textContent = cfg.avatar_initial;
    document.title = '@' + cfg.handle + ' — Daily Review';
  } catch (e) {}
}

async function loadPlaybookLastUpdated() {
  try {
    const res = await fetch('/api/playbooks/last-updated');
    const data = await res.json();
    const el = document.getElementById('playbook-last-updated');
    if (data.timestamp) {
      const d = new Date(data.timestamp * 1000);
      el.textContent = `Last updated ${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`;
    }
  } catch (e) {}
}

// Init
document.getElementById('skip-btn').addEventListener('click', skipToday);
document.getElementById('confirm-skip-btn').addEventListener('click', confirmSkip);
document.getElementById('cancel-skip-btn').addEventListener('click', cancelSkip);
document.getElementById('generate-btn').addEventListener('click', generatePosts);
document.getElementById('refresh-btn').addEventListener('click', startRefresh);
document.getElementById('confirm-refresh-start-btn').addEventListener('click', confirmRefreshStart);
document.getElementById('cancel-refresh-start-btn').addEventListener('click', cancelRefreshStart);
document.getElementById('confirm-refresh-btn').addEventListener('click', confirmRefresh);
document.getElementById('cancel-refresh-btn').addEventListener('click', cancelRefresh);
document.getElementById('day-info').innerText = new Date().toLocaleDateString('en-US', {
  weekday: 'long', month: 'long', day: 'numeric'
});

render();
loadConfig();
loadPlaybookLastUpdated();
