// ═══════════════════════════════════════════════════
//   ALUMACRAFT — FRONTEND JAVASCRIPT
// ═══════════════════════════════════════════════════

const API = '';  // Same origin
let currentUser = null;
let allServices = [];
let feedbackOrderId = null;
let selectedRating = 0;
let activeServiceFilter = 'All';

// ─── INIT ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await checkSession();
  await loadServices();
  showPage('home');
  setupScrollNavbar();
  setMinDate();
});

function setMinDate() {
  const d = document.getElementById('apptDate');
  if (d) d.min = new Date().toISOString().split('T')[0];
}

function setupScrollNavbar() {
  window.addEventListener('scroll', () => {
    const nav = document.getElementById('navbar');
    if (window.scrollY > 50) nav.classList.add('scrolled');
    else nav.classList.remove('scrolled');
  });
}

// ─── PAGE ROUTING ──────────────────────────────────
function showPage(page) {
  // Auth guards
  if (['dashboard', 'profile'].includes(page) && !currentUser) {
    showToast('Please login first', 'error'); showPage('login'); return;
  }
  if (page === 'admin') {
    if (!currentUser || currentUser.role !== 'admin') { showToast('Admin access required', 'error'); return; }
  }

  document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
  const target = document.getElementById(`page-${page}`);
  if (target) {
    target.classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // Page-specific loaders
  if (page === 'home') renderHomeServices();
  if (page === 'services') renderServicesPage();
  if (page === 'blog') loadBlog();
  if (page === 'dashboard') loadDashboard();
  if (page === 'profile') loadProfile();
  if (page === 'admin') loadAdmin();

  // Close mobile menu
  document.getElementById('navLinks').style.display = '';
}

// ─── SESSION CHECK ─────────────────────────────────
async function checkSession() {
  try {
    const res = await fetch(`${API}/api/me`, { credentials: 'include' });
    const data = await res.json();
    if (data.success) setCurrentUser(data.user);
  } catch {}
}

function setCurrentUser(user) {
  currentUser = user;
  // Update navbar
  document.getElementById('navAuth').classList.add('hidden');
  document.getElementById('navUser').classList.remove('hidden');
  const avatar = document.getElementById('userAvatar');
  avatar.textContent = user.name.charAt(0).toUpperCase();
  document.getElementById('dropdownName').textContent = user.name;
  document.getElementById('dropdownRole').textContent = user.role === 'admin' ? '🔧 Administrator' : '👤 Customer';
  if (user.role === 'admin') document.getElementById('adminLink').classList.remove('hidden');
}

function clearUser() {
  currentUser = null;
  document.getElementById('navAuth').classList.remove('hidden');
  document.getElementById('navUser').classList.add('hidden');
  document.getElementById('adminLink').classList.add('hidden');
}

// ─── AUTH ──────────────────────────────────────────
async function doLogin() {
  const email = document.getElementById('loginEmail').value.trim();
  const pw = document.getElementById('loginPw').value;
  const msg = document.getElementById('loginMsg');
  if (!email || !pw) { showMsg(msg, 'Please fill all fields', 'error'); return; }

  const res = await fetch(`${API}/api/login`, {
    method: 'POST', credentials: 'include',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ email, password: pw })
  });
  const data = await res.json();
  if (data.success) {
    setCurrentUser(data.user);
    showToast(`Welcome back, ${data.user.name}! ✦`, 'success');
    showPage(data.user.role === 'admin' ? 'admin' : 'dashboard');
  } else {
    showMsg(msg, data.message, 'error');
  }
}

async function doSignup() {
  const name = document.getElementById('signupName').value.trim();
  const email = document.getElementById('signupEmail').value.trim();
  const phone = document.getElementById('signupPhone').value.trim();
  const address = document.getElementById('signupAddress').value.trim();
  const pw = document.getElementById('signupPw').value;
  const msg = document.getElementById('signupMsg');

  if (!name || !email || !phone || !pw) { showMsg(msg, 'Please fill all required fields', 'error'); return; }
  if (pw.length < 6) { showMsg(msg, 'Password must be at least 6 characters', 'error'); return; }

  const res = await fetch(`${API}/api/signup`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ name, email, phone, address, password: pw })
  });
  const data = await res.json();
  if (data.success) {
    showMsg(msg, '✓ Account created! Redirecting to login...', 'success');
    setTimeout(() => showPage('login'), 1500);
  } else {
    showMsg(msg, data.message, 'error');
  }
}

async function logout() {
  await fetch(`${API}/api/logout`, { method: 'POST', credentials: 'include' });
  clearUser();
  showToast('Logged out successfully', 'success');
  showPage('home');
  toggleUserMenu(true);
}

// ─── SERVICES ─────────────────────────────────────
async function loadServices() {
  const res = await fetch(`${API}/api/services`);
  const data = await res.json();
  if (data.success) allServices = data.services;
  populateOrderServiceSelect();
}

function renderHomeServices() {
  const grid = document.getElementById('homeServicesGrid');
  if (!grid) return;
  const preview = allServices.slice(0, 6);
  grid.innerHTML = preview.map(s => `
    <div class="service-preview-card">
      <div class="sp-cat">${s.category}</div>
      <div class="sp-name">${s.name}</div>
      <div class="sp-desc">${s.description.substring(0, 80)}...</div>
      <div class="sp-rate">₹${s.rate.toLocaleString()}<span class="sp-unit">/${s.unit}</span></div>
    </div>
  `).join('');
}

function renderServicesPage() {
  // Filter buttons
  const categories = ['All', ...new Set(allServices.map(s => s.category))];
  const filterDiv = document.getElementById('servicesFilter');
  filterDiv.innerHTML = categories.map(c => `
    <button class="filter-btn ${c === activeServiceFilter ? 'active' : ''}" onclick="filterServices('${c}', this)">${c}</button>
  `).join('');

  renderServiceCards();
}

function filterServices(cat, btn) {
  activeServiceFilter = cat;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderServiceCards();
}

function renderServiceCards() {
  const grid = document.getElementById('servicesGrid');
  const filtered = activeServiceFilter === 'All' ? allServices : allServices.filter(s => s.category === activeServiceFilter);
  grid.innerHTML = filtered.map(s => `
    <div class="service-card">
      <div class="sc-cat">${s.category}</div>
      <div class="sc-name">${s.name}</div>
      <div class="sc-desc">${s.description}</div>
      <div class="sc-footer">
        <div>
          <div class="sc-rate">₹${s.rate.toLocaleString()}</div>
          <div class="sc-unit">per ${s.unit}</div>
          <div class="sc-min">Min: ${s.min_order} ${s.unit}</div>
        </div>
        <button class="sc-order-btn" onclick="handleOrderFromService(${s.id}, '${s.name}', ${s.rate}, '${s.unit}')">Order Now</button>
      </div>
    </div>
  `).join('');
}

function handleOrderFromService(id, name, rate, unit) {
  if (!currentUser) { showToast('Please login to place an order', 'error'); showPage('login'); return; }
  showPage('dashboard');
  setTimeout(() => {
    switchDashTab('new-order', document.querySelector('[onclick="switchDashTab(\'new-order\', this)"]'));
    const sel = document.getElementById('orderService');
    sel.value = id;
    updateOrderCost();
  }, 100);
}

function populateOrderServiceSelect() {
  const sel = document.getElementById('orderService');
  if (!sel) return;
  sel.innerHTML = '<option value="">-- Choose a service --</option>';
  allServices.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = `${s.name} — ₹${s.rate}/${s.unit}`;
    opt.dataset.rate = s.rate;
    opt.dataset.unit = s.unit;
    sel.appendChild(opt);
  });
}

function updateOrderCost() {
  const sel = document.getElementById('orderService');
  const qty = parseFloat(document.getElementById('orderQty').value) || 0;
  const ce = document.getElementById('costEstimate');
  const ceAmt = document.getElementById('ceAmount');
  const unitLabel = document.getElementById('orderUnit');

  if (sel.value) {
    const opt = sel.options[sel.selectedIndex];
    const rate = parseFloat(opt.dataset.rate);
    const unit = opt.dataset.unit;
    unitLabel.textContent = `(${unit})`;
    if (qty > 0) {
      ce.style.display = 'block';
      ceAmt.textContent = `₹${(rate * qty).toLocaleString('en-IN')}`;
    }
  }
}

// ─── BLOG ──────────────────────────────────────────
async function loadBlog() {
  const res = await fetch(`${API}/api/blog`);
  const data = await res.json();
  const grid = document.getElementById('blogGrid');
  const icons = ['🪟', '🏢', '🚪', '✨', '🔧', '💎'];
  if (data.success && data.posts.length > 0) {
    grid.innerHTML = data.posts.map((p, i) => `
      <div class="blog-card">
        <div class="blog-img">${icons[i % icons.length]}</div>
        <div class="blog-body">
          <div class="blog-date">${new Date(p.created_at).toLocaleDateString('en-IN', {year:'numeric',month:'long',day:'numeric'})}</div>
          <div class="blog-title">${p.title}</div>
          <div class="blog-excerpt">${p.content.substring(0, 120)}...</div>
        </div>
      </div>
    `).join('');
  }
}

// ─── CONTACT ──────────────────────────────────────
async function submitContact() {
  const name = document.getElementById('contactName').value.trim();
  const email = document.getElementById('contactEmail').value.trim();
  const phone = document.getElementById('contactPhone').value.trim();
  const msg = document.getElementById('contactMsg').value.trim();
  const fmsg = document.getElementById('contactFormMsg');
  if (!name || !email || !msg) { showMsg(fmsg, 'Please fill required fields', 'error'); return; }

  const res = await fetch(`${API}/api/contact`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ name, email, phone, message: msg })
  });
  const data = await res.json();
  if (data.success) {
    showMsg(fmsg, '✓ ' + data.message, 'success');
    document.getElementById('contactName').value = '';
    document.getElementById('contactEmail').value = '';
    document.getElementById('contactPhone').value = '';
    document.getElementById('contactMsg').value = '';
  }
}

// ─── DASHBOARD ─────────────────────────────────────
function loadDashboard() {
  loadMyOrders();
  loadMyAppointments();
  populateOrderServiceSelect();
}

function switchDashTab(tab, btn) {
  document.querySelectorAll('.dash-panel').forEach(p => p.classList.add('hidden'));
  document.querySelectorAll('.dash-tab').forEach(b => b.classList.remove('active'));
  document.getElementById(`dash-${tab}`).classList.remove('hidden');
  if (btn) btn.classList.add('active');
}

async function loadMyOrders() {
  const res = await fetch(`${API}/api/orders/my`, { credentials: 'include' });
  const data = await res.json();
  const container = document.getElementById('ordersContainer');
  if (!data.success || data.orders.length === 0) {
    container.innerHTML = `<div class="loading">No orders yet. Place your first order! →</div>`; return;
  }
  container.innerHTML = `<div class="orders-list">${data.orders.map(o => `
    <div class="order-item">
      <div class="order-info">
        <h4>${o.service}</h4>
        <p>Qty: ${o.quantity} ${o.unit} • ${o.description || 'No description'}</p>
        <div class="order-meta">
          <span class="badge badge-${o.status}">⬟ ${o.status.toUpperCase()}</span>
          ${o.admin_note ? `<div class="admin-note">📌 Admin Note: ${o.admin_note}</div>` : ''}
        </div>
        ${o.status === 'done' ? `<button class="feedback-btn" onclick="openFeedback(${o.id})">⭐ Rate This Work</button>` : ''}
      </div>
      <div class="order-right">
        <div class="order-cost">₹${parseInt(o.estimated_cost).toLocaleString('en-IN')}</div>
        <div class="order-date">${new Date(o.created_at).toLocaleDateString('en-IN')}</div>
      </div>
    </div>
  `).join('')}</div>`;
}

async function loadMyAppointments() {
  const res = await fetch(`${API}/api/appointments/my`, { credentials: 'include' });
  const data = await res.json();
  const container = document.getElementById('apptsContainer');
  if (!data.success || data.appointments.length === 0) {
    container.innerHTML = `<div class="loading">No appointments booked yet.</div>`; return;
  }
  container.innerHTML = `<div class="orders-list">${data.appointments.map(a => `
    <div class="order-item">
      <div class="order-info">
        <h4>${a.service}</h4>
        <p>📅 ${a.date} &nbsp;⏰ ${a.time_slot}</p>
        <p>${a.message || ''}</p>
        <div class="order-meta">
          <span class="badge badge-${a.status}">⬟ ${a.status.toUpperCase()}</span>
        </div>
      </div>
      <div class="order-right">
        <div class="order-date">${new Date(a.created_at).toLocaleDateString('en-IN')}</div>
      </div>
    </div>
  `).join('')}</div>`;
}

async function placeOrder() {
  const sel = document.getElementById('orderService');
  const qty = document.getElementById('orderQty').value;
  const desc = document.getElementById('orderDesc').value;
  const msg = document.getElementById('orderMsg');

  if (!sel.value || !qty) { showMsg(msg, 'Please select a service and enter quantity', 'error'); return; }

  const service = allServices.find(s => s.id == sel.value);
  const res = await fetch(`${API}/api/orders`, {
    method: 'POST', credentials: 'include',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      service_id: parseInt(sel.value),
      service: service.name,
      quantity: parseFloat(qty),
      unit: service.unit,
      description: desc
    })
  });
  const data = await res.json();
  if (data.success) {
    showMsg(msg, `✓ Order placed! Estimated: ₹${data.estimated_cost.toLocaleString('en-IN')}`, 'success');
    sel.value = ''; document.getElementById('orderQty').value = '';
    document.getElementById('orderDesc').value = '';
    document.getElementById('costEstimate').style.display = 'none';
    setTimeout(() => { switchDashTab('orders', document.querySelector('.dash-tab')); loadMyOrders(); }, 1500);
  } else {
    showMsg(msg, data.message, 'error');
  }
}

async function bookAppointment() {
  const date = document.getElementById('apptDate').value;
  const time = document.getElementById('apptTime').value;
  const service = document.getElementById('apptService').value.trim();
  const msg2 = document.getElementById('apptMsg2');
  const note = document.getElementById('apptMsg').value;

  if (!date || !service) { showMsg(msg2, 'Please fill date and service fields', 'error'); return; }

  const res = await fetch(`${API}/api/appointments`, {
    method: 'POST', credentials: 'include',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ date, time_slot: time, service, message: note })
  });
  const data = await res.json();
  if (data.success) {
    showMsg(msg2, '✓ ' + data.message, 'success');
    document.getElementById('apptDate').value = '';
    document.getElementById('apptService').value = '';
    document.getElementById('apptMsg').value = '';
  }
}

// ─── PROFILE ──────────────────────────────────────
function loadProfile() {
  if (!currentUser) return;
  document.getElementById('profileAvatarBig').textContent = currentUser.name.charAt(0).toUpperCase();
  document.getElementById('profileName').textContent = currentUser.name;
  document.getElementById('profileBadge').textContent = currentUser.role === 'admin' ? '🔧 Administrator' : '👤 Customer';
  document.getElementById('editName').value = currentUser.name;
  document.getElementById('editEmail').value = currentUser.email;
  document.getElementById('editPhone').value = currentUser.phone || '';
  document.getElementById('editAddress').value = currentUser.address || '';
}

async function updateProfile() {
  const name = document.getElementById('editName').value.trim();
  const phone = document.getElementById('editPhone').value.trim();
  const address = document.getElementById('editAddress').value.trim();
  const msg = document.getElementById('profileMsg');
  if (!name) { showMsg(msg, 'Name is required', 'error'); return; }

  const res = await fetch(`${API}/api/profile`, {
    method: 'PUT', credentials: 'include',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ name, phone, address })
  });
  const data = await res.json();
  if (data.success) {
    currentUser.name = name; currentUser.phone = phone; currentUser.address = address;
    document.getElementById('userAvatar').textContent = name.charAt(0).toUpperCase();
    document.getElementById('dropdownName').textContent = name;
    loadProfile();
    showMsg(msg, '✓ Profile updated!', 'success');
    showToast('Profile updated!', 'success');
  }
}

// ─── FEEDBACK ─────────────────────────────────────
function openFeedback(orderId) {
  feedbackOrderId = orderId;
  selectedRating = 0;
  updateStars(0);
  document.getElementById('feedbackComment').value = '';
  document.getElementById('feedbackMsg').textContent = '';
  document.getElementById('feedbackModal').classList.remove('hidden');
}

function closeFeedback() {
  document.getElementById('feedbackModal').classList.add('hidden');
}

function setRating(r) {
  selectedRating = r;
  updateStars(r);
}

function updateStars(r) {
  document.querySelectorAll('.star').forEach((s, i) => {
    s.classList.toggle('active', i < r);
  });
}

async function submitFeedback() {
  if (!selectedRating) { showMsg(document.getElementById('feedbackMsg'), 'Please select a rating', 'error'); return; }
  const comment = document.getElementById('feedbackComment').value;

  const res = await fetch(`${API}/api/orders/${feedbackOrderId}/feedback`, {
    method: 'POST', credentials: 'include',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ rating: selectedRating, comment })
  });
  const data = await res.json();
  if (data.success) {
    showMsg(document.getElementById('feedbackMsg'), '✓ Thank you for your feedback!', 'success');
    setTimeout(closeFeedback, 1500);
    showToast('Feedback submitted! ⭐', 'success');
  }
}

// ─── ADMIN ────────────────────────────────────────
async function loadAdmin() {
  loadAdminStats();
  loadAdminOrders();
}

async function loadAdminStats() {
  const res = await fetch(`${API}/api/admin/dashboard`, { credentials: 'include' });
  const data = await res.json();
  if (!data.success) return;
  const s = data.stats;
  document.getElementById('adminStats').innerHTML = `
    <div class="admin-stat"><div class="as-num">${s.total_users}</div><div class="as-label">Users</div></div>
    <div class="admin-stat"><div class="as-num">${s.total_orders}</div><div class="as-label">Total Orders</div></div>
    <div class="admin-stat"><div class="as-num">${s.pending_orders}</div><div class="as-label">Pending</div></div>
    <div class="admin-stat"><div class="as-num">${s.running_orders}</div><div class="as-label">Running</div></div>
    <div class="admin-stat"><div class="as-num">₹${parseInt(s.total_revenue).toLocaleString('en-IN')}</div><div class="as-label">Revenue</div></div>
  `;
}

function switchAdminTab(tab, btn) {
  document.querySelectorAll('[id$="Panel"]').forEach(p => {
    if (p.id.startsWith('admin')) p.classList.add('hidden');
  });
  document.querySelectorAll('.admin-tab').forEach(b => b.classList.remove('active'));
  document.getElementById(`admin${capitalize(tab)}Panel`).classList.remove('hidden');
  if (btn) btn.classList.add('active');

  if (tab === 'orders') loadAdminOrders();
  if (tab === 'appointments') loadAdminAppointments();
  if (tab === 'users') loadAdminUsers();
  if (tab === 'contacts') loadAdminContacts();
  if (tab === 'feedback') loadAdminFeedback();
}

async function loadAdminOrders() {
  const res = await fetch(`${API}/api/admin/orders`, { credentials: 'include' });
  const data = await res.json();
  const div = document.getElementById('adminOrdersTable');
  if (!data.success) return;
  div.innerHTML = `<div class="admin-table-wrap"><table class="admin-table">
    <thead><tr><th>#</th><th>Client</th><th>Service</th><th>Qty</th><th>Estimate</th><th>Status</th><th>Admin Note</th><th>Date</th><th>Action</th></tr></thead>
    <tbody>${data.orders.map(o => `
      <tr id="order-row-${o.id}">
        <td>${o.id}</td>
        <td><strong>${o.user_name}</strong><br/><small>${o.user_phone}</small></td>
        <td>${o.service}</td>
        <td>${o.quantity} ${o.unit}</td>
        <td>₹${parseInt(o.estimated_cost).toLocaleString('en-IN')}</td>
        <td>
          <select class="status-select" id="status-${o.id}">
            ${['pending','running','hold','done','cancelled'].map(s => `<option value="${s}" ${o.status===s?'selected':''}>${s.toUpperCase()}</option>`).join('')}
          </select>
        </td>
        <td><input type="text" class="note-input" id="note-${o.id}" value="${o.admin_note||''}" placeholder="Add note..."/></td>
        <td><small>${new Date(o.created_at).toLocaleDateString('en-IN')}</small></td>
        <td><button class="save-btn" onclick="updateOrder(${o.id})">Save</button></td>
      </tr>
    `).join('')}</tbody>
  </table></div>`;
}

async function updateOrder(id) {
  const status = document.getElementById(`status-${id}`).value;
  const note = document.getElementById(`note-${id}`).value;
  const res = await fetch(`${API}/api/admin/orders/${id}`, {
    method: 'PUT', credentials: 'include',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ status, admin_note: note })
  });
  const data = await res.json();
  if (data.success) showToast('Order updated!', 'success');
}

async function loadAdminAppointments() {
  const res = await fetch(`${API}/api/admin/appointments`, { credentials: 'include' });
  const data = await res.json();
  const div = document.getElementById('adminApptsTable');
  if (!data.success) return;
  div.innerHTML = `<div class="admin-table-wrap"><table class="admin-table">
    <thead><tr><th>#</th><th>Client</th><th>Date</th><th>Time</th><th>Service</th><th>Status</th><th>Action</th></tr></thead>
    <tbody>${data.appointments.map(a => `
      <tr>
        <td>${a.id}</td>
        <td><strong>${a.user_name}</strong><br/><small>${a.user_phone}</small></td>
        <td>${a.date}</td>
        <td>${a.time_slot}</td>
        <td>${a.service}</td>
        <td>
          <select class="status-select" id="appt-status-${a.id}">
            ${['pending','confirmed','completed','cancelled'].map(s => `<option value="${s}" ${a.status===s?'selected':''}>${s.toUpperCase()}</option>`).join('')}
          </select>
        </td>
        <td><button class="save-btn" onclick="updateAppt(${a.id})">Save</button></td>
      </tr>
    `).join('')}</tbody>
  </table></div>`;
}

async function updateAppt(id) {
  const status = document.getElementById(`appt-status-${id}`).value;
  const res = await fetch(`${API}/api/admin/appointments/${id}`, {
    method: 'PUT', credentials: 'include',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ status })
  });
  if ((await res.json()).success) showToast('Appointment updated!', 'success');
}

async function loadAdminUsers() {
  const res = await fetch(`${API}/api/admin/users`, { credentials: 'include' });
  const data = await res.json();
  const div = document.getElementById('adminUsersTable');
  if (!data.success) return;
  div.innerHTML = `<div class="admin-table-wrap"><table class="admin-table">
    <thead><tr><th>#</th><th>Name</th><th>Email</th><th>Phone</th><th>Role</th><th>Address</th><th>Joined</th><th>Last Login</th></tr></thead>
    <tbody>${data.users.map(u => `
      <tr>
        <td>${u.id}</td>
        <td><strong>${u.name}</strong></td>
        <td>${u.email}</td>
        <td>${u.phone||'-'}</td>
        <td><span class="badge ${u.role==='admin'?'badge-running':'badge-done'}">${u.role.toUpperCase()}</span></td>
        <td>${u.address||'-'}</td>
        <td><small>${u.created_at ? new Date(u.created_at).toLocaleDateString('en-IN') : '-'}</small></td>
        <td><small>${u.last_login ? new Date(u.last_login).toLocaleString('en-IN') : 'Never'}</small></td>
      </tr>
    `).join('')}</tbody>
  </table></div>`;
}

async function loadAdminContacts() {
  const res = await fetch(`${API}/api/admin/contacts`, { credentials: 'include' });
  const data = await res.json();
  const div = document.getElementById('adminContactsTable');
  if (!data.success) return;
  div.innerHTML = `<div class="admin-table-wrap"><table class="admin-table">
    <thead><tr><th>#</th><th>Name</th><th>Email</th><th>Phone</th><th>Message</th><th>Date</th></tr></thead>
    <tbody>${data.contacts.map(c => `
      <tr>
        <td>${c.id}</td>
        <td>${c.name}</td>
        <td>${c.email}</td>
        <td>${c.phone||'-'}</td>
        <td><small>${c.message}</small></td>
        <td><small>${new Date(c.created_at).toLocaleDateString('en-IN')}</small></td>
      </tr>
    `).join('')}</tbody>
  </table></div>`;
}

async function loadAdminFeedback() {
  const res = await fetch(`${API}/api/admin/feedback`, { credentials: 'include' });
  const data = await res.json();
  const div = document.getElementById('adminFeedbackTable');
  if (!data.success) return;
  div.innerHTML = `<div class="admin-table-wrap"><table class="admin-table">
    <thead><tr><th>#</th><th>User</th><th>Order</th><th>Rating</th><th>Comment</th><th>Date</th></tr></thead>
    <tbody>${data.feedback.map(f => `
      <tr>
        <td>${f.id}</td>
        <td>${f.user_name}</td>
        <td>${f.order_service||'-'}</td>
        <td>${'★'.repeat(f.rating)}${'☆'.repeat(5-f.rating)}</td>
        <td><small>${f.comment||'-'}</small></td>
        <td><small>${new Date(f.created_at).toLocaleDateString('en-IN')}</small></td>
      </tr>
    `).join('')}</tbody>
  </table></div>`;
}

// ─── UI HELPERS ───────────────────────────────────
function showMsg(el, msg, type) {
  el.textContent = msg;
  el.className = `form-msg ${type}`;
  setTimeout(() => { el.textContent = ''; el.className = 'form-msg'; }, 4000);
}

function showToast(msg, type = 'success') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast ${type}`;
  t.classList.remove('hidden');
  setTimeout(() => t.classList.add('hidden'), 3000);
}

function toggleUserMenu(forceClose = false) {
  const dd = document.getElementById('userDropdown');
  if (forceClose) { dd.classList.remove('open'); return; }
  dd.classList.toggle('open');
}

document.addEventListener('click', (e) => {
  const navUser = document.getElementById('navUser');
  if (navUser && !navUser.contains(e.target)) {
    document.getElementById('userDropdown').classList.remove('open');
  }
});

function toggleMobileMenu() {
  const links = document.getElementById('navLinks');
  links.style.display = links.style.display === 'flex' ? '' : 'flex';
  if (links.style.display === 'flex') {
    links.style.flexDirection = 'column';
    links.style.position = 'absolute';
    links.style.top = '68px';
    links.style.left = '0'; links.style.right = '0';
    links.style.background = 'var(--bg2)';
    links.style.padding = '16px';
    links.style.borderBottom = '1px solid var(--border)';
  }
}

function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
