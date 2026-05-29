import re

with open('templates/staff_unified.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Pending Orders (Manager)
html = re.sub(
    r'<div class="order-name">#\$\{o\.order_id\} \$\{o\.customer_name\}</div>',
    '<div class="order-name">${o.customer_name || "Guest Order"}</div>',
    html
)
html = re.sub(
    r'<td style="font-weight:700">\$\{o\.customer_name \|\| \'Guest\'\} \$\{o\.is_vip \? \'🌟\' : \'\'\}</td>',
    '<td style="font-weight:700">${o.customer_name || "Guest Order"} ${o.is_vip ? "🌟" : ""}</td>',
    html
)

# 2. Order History (Manager)
html = re.sub(
    r'async function loadOrderHistory\(\) \{',
    '''let isHistoryLoading = false;
    async function loadOrderHistory(force = false) {
      if (!force && window.lastHistoryData) { renderOrderHistory(window.lastHistoryData); return; }
      if (isHistoryLoading) return;
      isHistoryLoading = true;''',
    html
)
html = html.replace(
    "const tbody = document.getElementById('history-table-body');",
    '''window.lastHistoryData = orders;
        renderOrderHistory(orders);
      } catch (e) { console.error(e); }
      isHistoryLoading = false;
    }
    function renderOrderHistory(orders) {
      const tbody = document.getElementById('history-table-body');'''
)
html = html.replace('<th>Order ID</th>', '<th>Customer</th>')
html = re.sub(
    r'<td><span class="status-pill \$\{statusMap\[o\.status\]\.cls\}">.*?</span></td>',
    '<td><span class="status-pill ${statusMap[o.status].cls}">${o.customer_name || "Guest"}</span></td>',
    html
)

# 3. Kitchen Kanban
html = re.sub(
    r'<div class="ticket-id">#\$\{String\(o\.order_id\)\.slice\(-4\)\}</div>',
    '<div class="ticket-id">${o.customer_name || "Guest Order"}</div>',
    html
)

# 4. Kitchen Stack
html = re.sub(
    r'<div class="stack-count">#\$\{String\(o\.order_id\)\.slice\(-4\)\}</div>',
    '<div class="stack-count" style="font-size:18px;">${(o.customer_name || "Guest").substring(0,6)}</div>',
    html
)

# 5. Kitchen Compact -> Also impacts Manager Kitchen (next step)
html = html.replace('<th>Order</th>', '<th>Customer</th>')
html = re.sub(
    r'<td><span class="compact-id \$\{idClass\}">···\$\{String\(o\.order_id\)\.slice\(-6\)\}</span></td>',
    '<td><span class="compact-id ${idClass}">${o.customer_name || "Guest"}</span></td>',
    html
)

# 6. Manager Kitchen View -> Use exact same compact renderer!
html = html.replace('id="mgr-kitchen-cols"', 'id="mgr-kitchen-compact" class="compact-wrap"')
html = re.sub(
    r'<div class="kitchen-cols" id="mgr-kitchen-compact".*?</div>',
    '<div class="compact-wrap"><table class="compact-table"><thead><tr><th>Customer</th><th>Status</th><th>Items</th><th>Wait</th></tr></thead><tbody id="mgr-kitchen-body"><tr><td colspan="4" style="text-align:center;padding:24px">Loading...</td></tr></tbody></table></div>',
    html,
    flags=re.DOTALL
)

mgr_kitchen_replacement = '''let isMgrKitchenLoading = false;
    async function loadMgrKitchen(force = false) {
      if(!force && window.lastManagerKitchenData) { _renderMgrKitchen(window.lastManagerKitchenData); return; }
      if(isMgrKitchenLoading) return;
      isMgrKitchenLoading = true;
      try {
        const res = await fetch('/api/kitchen/orders/active', { headers: { 'Authorization': `Bearer ${localStorage.getItem('authToken')}` } });
        if (res.ok) { window.lastManagerKitchenData = await res.json(); _renderMgrKitchen(window.lastManagerKitchenData); }
      } catch(e) {}
      isMgrKitchenLoading = false;
    }
    async function loadMgrKitchenSilent() { try { const res = await fetch('/api/kitchen/orders/active', { headers: { 'Authorization': `Bearer ${localStorage.getItem('authToken')}` } }); if(res.ok) { window.lastManagerKitchenData = await res.json(); if(document.getElementById('section-kitchen-view').classList.contains('active')) _renderMgrKitchen(window.lastManagerKitchenData); } } catch(e){} }
    async function _renderMgrKitchen(orders) {
      const tbody = document.getElementById('mgr-kitchen-body');
      if(!tbody) return;
      if(!orders || orders.length === 0) { tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:24px">No active kitchen orders.</td></tr>'; return; }
      let html = '';
      orders.forEach(o => {
        const isRush = o.is_vip || o.is_important;
        let itemsTxt = (o.items || []).map(i => `${i.quantity}x ${i.name}`).join(', ') || '—';
        let timeClass = ''; let diffMins = '';
        if (o.created_at) {
          const min = Math.floor((new Date() - new Date(o.created_at)) / 60000);
          diffMins = `${min}m`;
          if (min > 15) timeClass = 'crit';
          else if (min > 8) timeClass = 'warn';
        }
        let idClass = ''; let chipClass = '';
        if(o.status === 'accepted') { idClass = 's-accepted'; chipClass = 'c-chip-accepted'; }
        else if(o.status === 'preparing') { idClass = 's-preparing'; chipClass = 'c-chip-preparing'; }
        else if(o.status === 'ready') { idClass = 's-ready'; chipClass = 'c-chip-ready'; }
        html += `<tr>
          <td><span class="compact-id ${idClass}">${o.customer_name || "Guest"} ${isRush ? "🌟" : ""}</span></td>
          <td><span class="compact-chip ${chipClass}">${o.status}</span></td>
          <td class="compact-items">${itemsTxt}</td>
          <td><span class="compact-time ${timeClass}">${diffMins}</span></td>
        </tr>`;
      });
      tbody.innerHTML = html;
    }'''
html = re.sub(
    r'async function loadMgrKitchen\(\) \{.*?async function _renderMgrKitchen\(orders\) \{.*?\}',
    mgr_kitchen_replacement,
    html,
    flags=re.DOTALL
)

# 7. REMOVE DASHBOARD GRID CONTAINER placeholder
html = re.sub(
    r'<div class="dashboard-grid" id="dashboard-grid-container">\s*<div.*?Loading\s*dashboard...</div>\s*</div>',
    '<div class="dashboard-grid" id="dashboard-grid-container" style="display:none"></div>',
    html
)

with open('templates/staff_unified.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("done")
