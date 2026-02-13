// === NEW FEATURE: ADMIN PORTAL ADVANCED ===
function showAdminSection(section) {
    // Safely handle pages where admin UI is not present
    var tabButtons = document.querySelectorAll('.tab-btn');
    var sections = document.querySelectorAll('.admin-section');
    if (tabButtons && tabButtons.length) {
        tabButtons.forEach(function(b){ b.classList.remove('active'); });
    }
    if (sections && sections.length) {
        sections.forEach(function(s){ s.classList.remove('active'); });
    }
    var tabBtn = document.querySelector(".tab-btn[onclick*='" + section + "']");
    if (tabBtn) { tabBtn.classList.add('active'); }
    var secEl = document.getElementById(section + '-section');
    if (secEl) { secEl.classList.add('active'); }
}
window.onload = function() {
    // Only try switching sections if admin container exists
    if (document.querySelector('.admin-tabs') || document.querySelector('.admin-section')) {
        showAdminSection('dashboard');
    }
    const ctx = document.getElementById('salesChart');
    if(ctx){ new Chart(ctx,{type:'bar',data:{labels:['Today','Yesterday'],datasets:[{label:'Sales',data:[1200,950],backgroundColor:['#34a853','#fbbc05']}]}}); }
    const cx2 = document.getElementById('customerChart');
    if(cx2){ new Chart(cx2,{type:'line',data:{labels:['Week 1','Week 2','Week 3'],datasets:[{label:'New Customers',data:[15,19,25],borderColor:'#4285f4'}]}}); }
}
