const $ = (selector, root = document) => root.querySelector(selector);
const state = { role: null, csrf: '', page: 'dashboard', lang: localStorage.getItem('lang') || 'fa', theme: localStorage.getItem('theme') || 'light', sidebarCollapsed: localStorage.getItem('sidebar-collapsed') === '1', dashboardPeriod: localStorage.getItem('dashboard-period') || 'month', pages: {}, unread: 0, connection: navigator.onLine ? 'connecting' : 'offline', realtime: null, realtimeTimer: null, drawer: null, customerFilters: {q:'',activity:'all',product:'',sort:'recent'} };

const copy = {
  fa: {
    loginTitle:'مدیریت حرفه‌ای، بدون شلوغی',loginText:'برای ورود امن، هویت شما با تلگرام بررسی می‌شود.',devLogin:'ورود آزمایشی محلی',secureLogin:'بدون رمز عبور؛ دسترسی فقط برای سنسی و ادمین',connected:'متصل و همگام',connecting:'در حال همگام‌سازی…',offline:'آفلاین',collapseNav:'جمع‌کردن منو',expandNav:'بازکردن منو',
    dashboard:'نمای کلی',orders:'کارها',messages:'پیام‌ها',customers:'شاگردها',sales:'فروش',overview:'تصویر روشن از وضعیت امروز',actions:'کارهای نیازمند اقدام',monthRevenue:'فروش این ماه',totalRevenue:'فروش کل',activeCustomers:'شاگرد فعال',unreadMessages:'پیام خوانده‌نشده',salesTrend:'روند فروش',priority:'اولویت‌های امروز',receipts:'رسیدهای بررسی‌نشده',newOrders:'سفارش‌های جدید',designing:'در حال طراحی',needsInfo:'منتظر اطلاعات',day:'روز',week:'هفته',month:'ماه',all:'کل',quickActions:'اقدام‌های سریع',salesOpen:'فروش باز است',salesClosed:'فروش موقتاً بسته است',closeSales:'بستن فروش',openSales:'باز کردن فروش',closeSalesConfirm:'فروش جدید موقتاً بسته شود؟ کاربران دیگر نمی‌توانند سفارش جدید ثبت کنند.',reviewReceipts:'بررسی کارها',openMessages:'باز کردن پیام‌ها',refresh:'به‌روزرسانی',
    search:'جست‌وجو در همین صفحه…',searchCustomer:'جست‌وجوی شاگرد با نام…',filters:'فیلترها',activityFilter:'وضعیت دوره',allStudents:'همه شاگردها',activeOnly:'دارای دوره فعال',inactiveOnly:'بدون دوره فعال',courseFilter:'دوره خریداری‌شده',allCourses:'همه دوره‌ها',sortBy:'مرتب‌سازی',sortRecent:'آخرین خرید',sortSpend:'بیشترین خرید',sortOrders:'بیشترین سفارش',sortActive:'بیشترین دوره فعال',sortName:'نام (الفبا)',clearFilters:'پاک کردن فیلترها',activeCourses:'دوره فعال',noCustomerResults:'شاگردی با این مشخصات پیدا نشد.',orderCode:'کد سفارش',customer:'شاگرد',course:'دوره',status:'وضعیت',lastMessage:'آخرین پیام',unread:'خوانده‌نشده',ordersCount:'تعداد سفارش',spent:'مجموع خرید',date:'تاریخ',amount:'مبلغ',empty:'هنوز داده‌ای برای نمایش نیست.',previous:'قبلی',next:'بعدی',page:'صفحه',details:'جزئیات',profile:'پروفایل شاگرد',phone:'شماره تماس',age:'سن',gender:'جنسیت',height:'قد',weight:'وزن',goal:'هدف',history:'سابقه تمرین',notes:'توضیحات',payment:'پرداخت',created:'ثبت سفارش',approve:'تأیید رسید',reject:'رد رسید',startDesign:'شروع طراحی',requestInfo:'درخواست اطلاعات',requestText:'دقیقاً چه اطلاعاتی لازم است؟',send:'ارسال',uploadPlan:'تحویل فایل دوره',chooseFile:'انتخاب فایل',conversation:'گفت‌وگو',reply:'پاسخ به شاگرد',commission:'سهم تیم توسعه',net:'سهم سنسی',logout:'خروج',loading:'در حال دریافت اطلاعات…',done:'انجام شد',error:'عملیات انجام نشد؛ دوباره تلاش کنید.',
  },
  en: {
    loginTitle:'Professional management, without clutter',loginText:'Your identity is securely verified by Telegram.',devLogin:'Local development login',secureLogin:'Passwordless; access is limited to Sensi and admins',connected:'Connected and synced',connecting:'Syncing…',offline:'Offline',collapseNav:'Collapse navigation',expandNav:'Expand navigation',
    dashboard:'Overview',orders:'Work queue',messages:'Messages',customers:'Clients',sales:'Revenue',overview:'A clear view of today',actions:'Items requiring action',monthRevenue:'Revenue this month',totalRevenue:'All-time revenue',activeCustomers:'Active clients',unreadMessages:'Unread messages',salesTrend:'Revenue trend',priority:"Today's priorities",receipts:'Receipts to review',newOrders:'New orders',designing:'In design',needsInfo:'Waiting for information',day:'Day',week:'Week',month:'Month',all:'All time',quickActions:'Quick actions',salesOpen:'Sales are open',salesClosed:'Sales are temporarily paused',closeSales:'Pause sales',openSales:'Open sales',closeSalesConfirm:'Pause new sales? Clients will not be able to create a new order.',reviewReceipts:'Review work',openMessages:'Open messages',refresh:'Refresh',
    search:'Search this page…',searchCustomer:'Search clients by name…',filters:'Filters',activityFilter:'Course status',allStudents:'All clients',activeOnly:'Has active course',inactiveOnly:'No active course',courseFilter:'Purchased course',allCourses:'All courses',sortBy:'Sort by',sortRecent:'Latest purchase',sortSpend:'Highest spend',sortOrders:'Most orders',sortActive:'Most active courses',sortName:'Name (A–Z)',clearFilters:'Clear filters',activeCourses:'Active courses',noCustomerResults:'No client matches these filters.',orderCode:'Order',customer:'Client',course:'Course',status:'Status',lastMessage:'Last message',unread:'Unread',ordersCount:'Orders',spent:'Total spent',date:'Date',amount:'Amount',empty:'Nothing to show yet.',previous:'Previous',next:'Next',page:'Page',details:'Details',profile:'Client profile',phone:'Phone',age:'Age',gender:'Gender',height:'Height',weight:'Weight',goal:'Goal',history:'Training history',notes:'Notes',payment:'Payment',created:'Created',approve:'Approve receipt',reject:'Reject receipt',startDesign:'Start design',requestInfo:'Request information',requestText:'What information is needed?',send:'Send',uploadPlan:'Deliver course file',chooseFile:'Choose file',conversation:'Conversation',reply:'Reply to client',commission:'Development team share',net:'Sensi net',logout:'Logout',loading:'Loading data…',done:'Done',error:'The operation failed. Please try again.',
  }
};
const t = key => copy[state.lang][key] || key;
const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"></use></svg>`;
const money = value => `${new Intl.NumberFormat(state.lang === 'fa' ? 'fa-IR' : 'en-US').format(Number(value || 0))} ${state.lang === 'fa' ? 'تومان' : 'Toman'}`;
const formatDate = value => value ? new Intl.DateTimeFormat(state.lang === 'fa' ? 'fa-IR-u-ca-persian' : 'en-US', {dateStyle:'medium',timeStyle:'short'}).format(new Date(value)) : '—';
const displayName = user => user?.name || [user?.first_name,user?.last_name].filter(Boolean).join(' ') || (state.lang === 'fa' ? 'بدون نام' : 'Unnamed');
const statusFa = {awaiting_payment:'منتظر پرداخت',awaiting_receipt:'بررسی رسید',payment_rejected:'رد رسید',paid:'سفارش جدید',needs_info:'منتظر اطلاعات',in_progress:'در حال طراحی',ready:'آماده',delivered:'تحویل‌شده',cancelled:'لغوشده'};
const statusEn = {awaiting_payment:'Awaiting payment',awaiting_receipt:'Receipt review',payment_rejected:'Receipt rejected',paid:'New order',needs_info:'Needs info',in_progress:'In design',ready:'Ready',delivered:'Delivered',cancelled:'Cancelled'};
const statusText = value => (state.lang === 'fa' ? statusFa : statusEn)[value] || value || '—';

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.csrf && !['GET','HEAD'].includes((options.method || 'GET').toUpperCase())) headers.set('X-CSRF-Token', state.csrf);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type','application/json');
  const response = await fetch(path, {...options, headers});
  if (response.status === 401) { showLogin(); throw new Error('unauthorized'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function toast(message, error = false) {
  const node = $('#toast'); node.textContent = message; node.style.background = error ? 'var(--danger)' : '#14213d'; node.classList.remove('hidden');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => node.classList.add('hidden'), 3500);
}
function loading() { $('#content').innerHTML = `<div class="loading">${esc(t('loading'))}</div>`; }
function empty() { return `<div class="empty">${esc(t('empty'))}</div>`; }
function pager(page,total,size){ const pages=Math.max(1,Math.ceil(total/size)); if(pages<=1)return ''; return `<div class="pager"><button class="btn" data-page="${page-1}" ${page<=1?'disabled':''}>${esc(t('previous'))}</button><span class="pill">${esc(t('page'))} ${page} / ${pages}</span><button class="btn" data-page="${page+1}" ${page>=pages?'disabled':''}>${esc(t('next'))}</button></div>`; }
function section(title,subtitle=''){return `<div class="section-head"><div><h2>${esc(title)}</h2>${subtitle?`<p>${esc(subtitle)}</p>`:''}</div></div>`;}
function status(value){return `<span class="status ${esc(value)}">${esc(statusText(value))}</span>`;}
const salesPeriods=['day','week','month','all'];
function salesPeriodTabs(){return `<div class="range-control" role="group" aria-label="${esc(t('sales'))}">${salesPeriods.map(period=>`<button class="range-tab ${state.dashboardPeriod===period?'active':''}" data-sales-period="${period}" aria-pressed="${state.dashboardPeriod===period}">${esc(t(period))}</button>`).join('')}</div>`;}
function trendLabel(value,period){
  const options=period==='day'?{hour:'2-digit',minute:'2-digit',hour12:false}:period==='all'?{month:'short',year:'numeric'}:{day:'numeric',month:'short'};
  return new Intl.DateTimeFormat(state.lang==='fa'?'fa-IR-u-ca-persian':'en-US',options).format(new Date(value));
}
function trendTickIndices(total,period){
  const limit={day:6,week:5,month:4,all:3}[period]||4;
  if(total<=limit)return Array.from({length:total},(_,index)=>index);
  return Array.from({length:limit},(_,slot)=>Math.round(slot*(total-1)/(limit-1)));
}

const navItems = {
  dashboard:['grid','dashboard'],orders:['list','orders'],messages:['chat','messages'],customers:['users','customers'],sales:['chart','sales']
};
function renderNav(){
  const keys=state.role==='admin_team'?['dashboard','customers','sales']:Object.keys(navItems);
  const html=keys.map(key=>{const [i,label]=navItems[key],text=esc(t(label));return `<button class="nav-item ${state.page===key?'active':''}" data-nav="${key}" aria-label="${text}" title="${text}">${icon(i)}<span class="nav-label">${text}</span>${key==='messages'&&state.unread?`<span class="badge">${state.unread}</span>`:''}</button>`}).join('');
  $('#nav').innerHTML=html; $('#mobile-nav').innerHTML=html;
}
function applySidebar(){const app=$('#app'),button=$('#sidebar-toggle'),collapsed=state.sidebarCollapsed;app.classList.toggle('sidebar-collapsed',collapsed);button.setAttribute('aria-expanded',String(!collapsed));button.setAttribute('aria-label',t(collapsed?'expandNav':'collapseNav'));button.title=t(collapsed?'expandNav':'collapseNav');}
function applyLanguage(){
  const rtl=state.lang==='fa'; document.documentElement.lang=state.lang; document.documentElement.dir=rtl?'rtl':'ltr';
  document.querySelectorAll('[data-i18n]').forEach(node=>node.textContent=t(node.dataset.i18n)); $('#lang-toggle').textContent=rtl?'EN':'فا';
  renderNav(); setConnection(state.connection); applySidebar();
}
function applyTheme(){ document.documentElement.dataset.theme=state.theme; $('#theme-toggle use').setAttribute('href',state.theme==='dark'?'#i-sun':'#i-moon'); }

function setConnection(value){
  state.connection=value; document.documentElement.dataset.connection=value;
  document.querySelectorAll('[data-connection-label]').forEach(node=>node.textContent=t(value==='online'?'connected':value));
}
function registerPwa(){
  if('serviceWorker' in navigator) window.addEventListener('load',()=>navigator.serviceWorker.register('/service-worker.js',{scope:'/'}).catch(error=>console.error('Service worker registration failed',error)),{once:true});
}
function disconnectRealtime(){
  state.realtime?.close?.(); state.realtime=null; clearInterval(state.realtimeTimer); state.realtimeTimer=null;
}
const realtimePages={dashboard:['users','orders','support_messages','sales_gate'],orders:['orders','users','products'],messages:['support_messages','users'],customers:['users','orders','user_profile_history'],sales:['orders','users','products']};
const rendererFor=page=>({dashboard:renderDashboard,orders:renderOrders,messages:renderMessages,customers:renderCustomers,sales:renderSales}[page]);
async function refreshOpenDrawer(update){
  const drawer=state.drawer;if(!drawer)return;
  const sameId=!update.id||String(update.id)===drawer.id, sameUser=!update.userId||String(update.userId)===drawer.id;
  if(drawer.type==='thread'&&update.table==='support_messages'&&sameUser){await refreshOpenThread();return;}
  if(drawer.type==='order'&&update.table==='orders'&&sameId){await openOrder(drawer.id);return;}
  if(drawer.type==='customer'&&['users','orders','user_profile_history'].includes(update.table)&&sameUser)await openCustomer(drawer.id);
}
async function refreshRealtimeView(update={table:'all'}){
  if($('#app').classList.contains('hidden'))return;
  const page=state.page,query=$('[data-search]')?.value||'',shouldRefresh=update.table==='all'||realtimePages[page]?.includes(update.table);
  const tasks=[];
  if(shouldRefresh)tasks.push(rendererFor(page)());
  if(update.table!=='all')tasks.push(refreshOpenDrawer(update));
  await Promise.allSettled(tasks);
  if(page===state.page&&query&&$('[data-search]')){$('[data-search]').value=query;$('[data-search]').dispatchEvent(new Event('input'));}
}
function scheduleRealtime(update){
  clearTimeout(scheduleRealtime.timer);scheduleRealtime.timer=setTimeout(()=>refreshRealtimeView(update),180);
}
function connectRealtime(){
  disconnectRealtime();
  if(!window.EventSource){setConnection(navigator.onLine?'connecting':'offline');state.realtimeTimer=setInterval(()=>document.visibilityState==='visible'&&refreshRealtimeView(),15000);return;}
  setConnection(navigator.onLine?'connecting':'offline');
  const source=new EventSource('/api/events');state.realtime=source;
  source.onopen=()=>setConnection('online');
  source.onerror=()=>setConnection(navigator.onLine?'connecting':'offline');
  source.addEventListener('update',event=>{
    let update;try{update=JSON.parse(event.data);}catch(_){return;}
    if(update.table==='support_messages'&&update.direction==='customer'){
      if(update.action==='insert'&&!update.readAt)state.unread+=1;
      if((update.action==='update'&&update.readAt)||(update.action==='delete'&&!update.readAt))state.unread=Math.max(0,state.unread-1);
      renderNav();
    }
    scheduleRealtime(update);
  });
}

async function bootstrap(){
  applyTheme(); applyLanguage();
  try { const session=await api('/api/session'); state.role=session.role; state.csrf=session.csrf; showApp(); }
  catch(error){ if(error.message!=='unauthorized') showLogin(); }
}
async function showLogin(){
  disconnectRealtime();
  $('#app').classList.add('hidden'); $('#login').classList.remove('hidden');
  const cfg=await fetch('/api/config').then(r=>r.json());
  if(cfg.devLogin) $('#dev-login').classList.remove('hidden');
  if(window.Telegram?.WebApp?.initData){
    try{await api('/api/auth/telegram',{method:'POST',body:JSON.stringify({initData:window.Telegram.WebApp.initData})}); location.reload(); return;}catch(_){ }
  }
  if(!$('#telegram-login script') && cfg.botUsername){
    const script=document.createElement('script'); script.async=true; script.src='https://telegram.org/js/telegram-widget.js?22';
    script.dataset.telegramLogin=cfg.botUsername; script.dataset.size='large'; script.dataset.radius='12'; script.dataset.authUrl=`${location.origin}/auth/telegram`; script.dataset.requestAccess='write';
    $('#telegram-login').append(script);
  }
}
function showApp(){ $('#login').classList.add('hidden'); $('#app').classList.remove('hidden'); renderNav(); applySidebar(); connectRealtime(); navigate(state.page); }
async function navigate(page){
  clearTimeout(scheduleRealtime.timer);
  state.page=page; state.pages[page]=state.pages[page]||1; renderNav(); loading();
  const render=rendererFor(page);
  try{await render();}catch(error){console.error(error);$('#content').innerHTML=empty();toast(t('error'),true);}
}

async function renderDashboard(){
  const data=await api(`/api/dashboard?period=${encodeURIComponent(state.dashboardPeriod)}`); state.unread=Number(data.counts.unread||0); renderNav();
  const sales=data.sales, max=Math.max(1,...sales.trend.map(item=>Number(item.revenue))),ticks=trendTickIndices(sales.trend.length,sales.period);
  const chart=sales.trend.map((item,index)=>{const revenue=Number(item.revenue),label=trendLabel(item.bucket,sales.period),level=revenue?Math.max(1,Math.round(revenue/max*20)):0,show=ticks.includes(index);return `<div class="chart-col" role="listitem" aria-label="${esc(`${label}: ${money(revenue)}، ${item.orders} ${t('orders')}`)}" title="${esc(`${label} · ${money(revenue)}`)}"><div class="chart-bar" data-level="${level}"></div><span class="chart-label ${show?'':'is-hidden'}">${show?esc(label):''}</span></div>`;}).join('');
  const supporting=data.role==='admin_team'?`<article class="card kpi"><span class="kpi-label">${icon('chart')}${esc(t('commission'))}</span><strong>${money(data.commission)}</strong></article>`:'';
  const priorityTotal=Number(data.counts.actionable||0)+Number(data.counts.unread||0);
  const quick=data.role==='sensi'?`<article class="card panel quick-actions"><div class="panel-title"><h3>${esc(t('quickActions'))}</h3><span class="sales-state ${data.salesOpen?'open':'closed'}"><i></i>${esc(data.salesOpen?t('salesOpen'):t('salesClosed'))}</span></div><div class="action-grid">
      <button class="action-tile ${data.salesOpen?'danger':'primary'}" data-sales-gate="${data.salesOpen?'close':'open'}">${icon(data.salesOpen?'lock':'unlock')}<span>${esc(data.salesOpen?t('closeSales'):t('openSales'))}</span></button>
      <button class="action-tile" data-dashboard-nav="orders">${icon('list')}<span>${esc(t('reviewReceipts'))}</span></button>
      <button class="action-tile" data-dashboard-nav="messages">${icon('chat')}<span>${esc(t('openMessages'))}</span></button>
      <button class="action-tile" data-dashboard-refresh>${icon('refresh')}<span>${esc(t('refresh'))}</span></button>
    </div></article>`:'';
  $('#content').innerHTML=`${section(t('overview'))}<div class="kpi-grid dashboard-kpis ${data.role==='sensi'?'sensi-kpis':''}">
    <article class="card kpi sales-kpi"><div class="kpi-head"><span class="kpi-label">${icon('chart')}${esc(t('sales'))}</span>${salesPeriodTabs()}</div><strong>${money(sales.revenue)}</strong></article>
    <article class="card kpi"><span class="kpi-label">${icon('users')}${esc(t('activeCustomers'))}</span><strong>${data.counts.active}</strong></article>${supporting}</div>
    <div class="dashboard-grid ${data.role==='admin_team'?'admin-dashboard':''}"><article class="card panel trend-panel"><div class="panel-title"><h3>${esc(t('salesTrend'))}</h3>${salesPeriodTabs()}</div><div class="chart chart-${esc(sales.period)}" role="list" aria-label="${esc(`${t('salesTrend')}: ${money(sales.revenue)}`)}">${chart||empty()}</div></article>
    ${data.role==='sensi'?`<article class="card panel"><div class="panel-title"><h3>${esc(t('priority'))}</h3><span class="pill">${priorityTotal}</span></div><div class="priority-list">
      <div class="priority message"><i></i><span>${esc(t('unreadMessages'))}</span><strong>${data.counts.unread}</strong></div><div class="priority receipt"><i></i><span>${esc(t('receipts'))}</span><strong>${data.counts.receipts}</strong></div><div class="priority new"><i></i><span>${esc(t('newOrders'))}</span><strong>${data.counts.new_orders}</strong></div><div class="priority design"><i></i><span>${esc(t('designing'))}</span><strong>${data.counts.designing}</strong></div><div class="priority info"><i></i><span>${esc(t('needsInfo'))}</span><strong>${data.counts.needs_info}</strong></div>
    </div></article>`:''}${quick}</div>`;
}

function attachSearch(){
  const input=$('[data-search]'); if(!input)return; input.addEventListener('input',()=>{const q=input.value.trim().toLocaleLowerCase();document.querySelectorAll('.data-row').forEach(row=>row.classList.toggle('hidden',!row.textContent.toLocaleLowerCase().includes(q)));});
}
async function renderOrders(){
  const page=state.pages.orders,data=await api(`/api/orders?page=${page}`);
  const rows=data.items.map(item=>`<div class="data-row" data-order="${item.id}"><strong>ORD-${String(item.id).padStart(6,'0')}</strong><span>${esc(item.name||item.first_name||'—')}</span><span>${esc(item.product_title)}</span>${status(item.status)}<button class="row-link" aria-label="${esc(t('details'))}">${icon('arrow')}</button></div>`).join('');
  $('#content').innerHTML=`${section(t('orders'),`${data.total} ${t('actions')}`)}<div class="toolbar"><label class="search">${icon('search')}<input data-search placeholder="${esc(t('search'))}"></label></div><div class="card data-list"><div class="data-head"><span>${t('orderCode')}</span><span>${t('customer')}</span><span>${t('course')}</span><span>${t('status')}</span><span></span></div>${rows||empty()}</div>${pager(page,data.total,data.pageSize)}`;attachSearch();
}
async function renderMessages(){
  const page=state.pages.messages,data=await api(`/api/threads?page=${page}`);
  const rows=data.items.map(item=>`<div class="data-row" data-thread="${item.user_id}"><strong>${esc(displayName(item))}</strong><span>${esc(formatDate(item.last_message_at))}</span><span>${item.message_count} ${esc(t('messages'))}</span><span class="pill">${item.unread_count} ${esc(t('unread'))}</span><button class="row-link" aria-label="${esc(t('conversation'))}">${icon('arrow')}</button></div>`).join('');
  $('#content').innerHTML=`${section(t('messages'),`${data.total} ${t('conversation')}`)}<div class="toolbar"><label class="search">${icon('search')}<input data-search placeholder="${esc(t('search'))}"></label></div><div class="card data-list"><div class="data-head"><span>${t('customer')}</span><span>${t('lastMessage')}</span><span>${t('messages')}</span><span>${t('unread')}</span><span></span></div>${rows||empty()}</div>${pager(page,data.total,data.pageSize)}`;attachSearch();
}
function customerFilter(key,label,current,options){
  const selected=options.find(([value])=>String(value)===String(current))||options[0],labelId=`customer-filter-${key}`;
  return `<div class="filter-field custom-select" data-customer-filter="${key}"><span id="${labelId}" class="filter-label">${esc(label)}</span><button type="button" class="filter-trigger" data-filter-trigger aria-haspopup="listbox" aria-expanded="false" aria-labelledby="${labelId} customer-filter-${key}-value"><span id="customer-filter-${key}-value">${esc(selected[1])}</span>${icon('arrow')}</button><div class="filter-menu" role="listbox" aria-labelledby="${labelId}">${options.map(([value,text])=>`<button type="button" class="filter-option" role="option" data-filter-option data-value="${esc(value)}" aria-selected="${String(value)===String(current)}"><span>${esc(text)}</span>${icon('check')}</button>`).join('')}</div></div>`;
}
function closeCustomerFilters(except=null){
  document.querySelectorAll('.custom-select.open').forEach(field=>{if(field===except)return;field.classList.remove('open');field.querySelector('[data-filter-trigger]')?.setAttribute('aria-expanded','false');});
}
async function renderCustomers(focusSearch=false){
  const requestId=renderCustomers.requestId=(renderCustomers.requestId||0)+1,shouldFocus=focusSearch||document.activeElement?.matches('[data-customer-search]'),page=state.pages.customers,filters=state.customerFilters;
  const params=new URLSearchParams({page,q:filters.q,activity:filters.activity,sort:filters.sort});if(filters.product)params.set('product',filters.product);
  const data=await api(`/api/customers?${params}`);if(state.page!=='customers'||requestId!==renderCustomers.requestId)return;
  const products=[['',t('allCourses')],...data.products.map(item=>[String(item.id),item.title])];
  const rows=data.items.map(item=>{const name=displayName(item),initial=name.match(/[\p{L}\p{N}]/u)?.[0]||'S';return `<article class="card customer-card" data-customer="${item.user_id}" role="button" tabindex="0" aria-label="${esc(`${t('profile')}: ${name}`)}">
    <div class="customer-avatar"><span aria-hidden="true">${esc(initial)}</span><img src="/media/customers/${item.user_id}/avatar" alt="" width="72" height="72" loading="lazy" decoding="async"></div>
    <div class="customer-body"><div class="customer-name"><strong>${esc(name)}</strong>${item.username?`<span dir="ltr">@${esc(item.username)}</span>`:''}</div><div class="customer-metrics">
      <div class="customer-metric"><span>${esc(t('ordersCount'))}</span><strong>${item.orders_count}</strong></div>
      <div class="customer-metric"><span>${esc(t('spent'))}</span><strong>${money(item.total_spend)}</strong></div>
      <div class="customer-metric"><span>${esc(t('activeCourses'))}</span><strong>${item.active_courses}</strong></div>
    </div></div></article>`;}).join('');
  const filtered=filters.q||filters.activity!=='all'||filters.product||filters.sort!=='recent';
  $('#content').innerHTML=`${section(t('customers'),`${data.total} ${t('customers')}`)}<div class="card customer-tools"><label class="search customer-search">${icon('search')}<input data-customer-search value="${esc(filters.q)}" placeholder="${esc(t('searchCustomer'))}" aria-label="${esc(t('searchCustomer'))}" autocomplete="off"></label><div class="filter-grid">
    ${customerFilter('activity',t('activityFilter'),filters.activity,[['all',t('allStudents')],['active',t('activeOnly')],['inactive',t('inactiveOnly')]])}
    ${customerFilter('product',t('courseFilter'),filters.product,products)}
    ${customerFilter('sort',t('sortBy'),filters.sort,[['recent',t('sortRecent')],['spend',t('sortSpend')],['orders',t('sortOrders')],['active',t('sortActive')],['name',t('sortName')]])}
    <button class="btn filter-reset" data-reset-customer-filters ${filtered?'':'disabled'}>${esc(t('clearFilters'))}</button>
  </div></div><div class="customer-cards">${rows||`<div class="card customer-empty"><p>${esc(t('noCustomerResults'))}</p>${filtered?`<button class="btn" data-reset-customer-filters>${esc(t('clearFilters'))}</button>`:''}</div>`}</div>${pager(page,data.total,data.pageSize)}`;
  document.querySelectorAll('.customer-avatar img').forEach(image=>image.addEventListener('error',()=>image.remove(),{once:true}));
  if(shouldFocus){const input=$('[data-customer-search]');input?.focus();input?.setSelectionRange(input.value.length,input.value.length);}
}
async function renderSales(){
  const page=state.pages.sales,data=await api(`/api/sales?page=${page}`);
  const extras=data.commission!==undefined?`<article class="card kpi"><span class="kpi-label">${icon('chart')}${esc(t('commission'))}</span><strong>${money(data.commission)}</strong></article><article class="card kpi"><span class="kpi-label">${icon('chart')}${esc(t('net'))}</span><strong>${money(data.net)}</strong></article>`:'';
  const rows=data.items.map(item=>`<div class="data-row"><strong>ORD-${String(item.order_id).padStart(6,'0')}</strong><span>${esc(item.name||'—')} · ${esc(item.product_title)}</span><span>${money(item.amount)}</span><span>${esc(formatDate(item.paid_at))}</span></div>`).join('');
  $('#content').innerHTML=`${section(t('sales'))}<div class="kpi-grid"><article class="card kpi"><span class="kpi-label">${icon('chart')}${esc(t('monthRevenue'))}</span><strong>${money(data.month.revenue)}</strong><small>${data.month.orders} ${esc(t('orders'))}</small></article><article class="card kpi"><span class="kpi-label">${icon('chart')}${esc(t('totalRevenue'))}</span><strong>${money(data.total.revenue)}</strong><small>${data.total.orders} ${esc(t('orders'))}</small></article>${extras}</div><div class="card data-list sales spaced"><div class="data-head"><span>${t('orderCode')}</span><span>${t('customer')}</span><span>${t('amount')}</span><span>${t('date')}</span></div>${rows||empty()}</div>${pager(page,data.count,data.pageSize)}`;
}

function detail(label,value){return `<div class="detail"><label>${esc(label)}</label><strong>${esc(value??'—')}</strong></div>`;}
function openDrawer(html,drawer){state.drawer=drawer;$('#drawer').innerHTML=html;$('#drawer-wrap').classList.remove('hidden');setTimeout(()=>$('#drawer [data-close]')?.focus(),0);}
function closeDrawer(){state.drawer=null;$('#drawer-wrap').classList.add('hidden');$('#drawer').innerHTML='';}
function drawerHead(title){return `<div class="drawer-head"><h2 id="drawer-title">${esc(title)}</h2><button class="icon-btn" data-close aria-label="Close">${icon('close')}</button></div>`;}
async function openOrder(id){
  const o=await api(`/api/orders/${id}`),f=o.form_snapshot||{};
  const actionButtons=state.role==='sensi'?`${o.status==='awaiting_receipt'?`<button class="btn success" data-order-action="approve_receipt">${icon('check')}${t('approve')}</button><button class="btn danger" data-order-action="reject_receipt">${t('reject')}</button>`:''}${['paid','needs_info'].includes(o.status)?`<button class="btn primary" data-order-action="in_progress">${t('startDesign')}</button>`:''}${['paid','in_progress'].includes(o.status)?`<button class="btn" data-toggle-info>${t('requestInfo')}</button>`:''}`:'';
  const plan=['paid','in_progress','needs_info'].includes(o.status)&&state.role==='sensi'?`<div class="drawer-section"><h3>${t('uploadPlan')}</h3><form id="plan-form"><label class="btn">${icon('upload')}${t('chooseFile')}<input name="file" type="file" accept=".pdf,.doc,.docx,.xlsx,.jpg,.jpeg,.png" hidden required></label><button class="btn primary" type="submit">${t('uploadPlan')}</button></form></div>`:'';
  openDrawer(`${drawerHead(`ORD-${String(o.id).padStart(6,'0')}`)}<div class="detail-grid">${detail(t('customer'),o.name)}${detail(t('course'),o.product_title)}${detail(t('status'),statusText(o.status))}${detail(t('amount'),money(o.amount))}${detail(t('phone'),o.phone)}${detail(t('created'),formatDate(o.created_at))}${detail(t('age'),f.age)}${detail(t('weight'),f.weight_kg?`${f.weight_kg} kg`:'—')}${detail(t('height'),f.height_cm?`${f.height_cm} cm`:'—')}${detail(t('goal'),f.goal)}</div><div class="actions" data-order-id="${o.id}">${actionButtons}</div><div id="info-box" class="field hidden"><label>${t('requestText')}</label><textarea maxlength="1000"></textarea><button class="btn primary" data-send-info>${t('send')}</button></div>${plan}`,{type:'order',id:String(id)});
}
const threadMessages=items=>items.map(item=>`<div class="bubble ${item.direction==='sensi'?'sensi':''}">${esc(item.content_text||`[${item.content_type}]`)}<time>${esc(formatDate(item.created_at))}</time></div>`).join('');
async function openThread(id){
  const data=await api(`/api/threads/${id}`),messages=threadMessages(data.items);
  openDrawer(`${drawerHead(displayName(data.user))}<div class="chat" data-chat-thread="${id}" aria-live="polite">${messages||empty()}</div><form id="reply-form" data-user-id="${id}" class="field"><label>${t('reply')}</label><textarea name="message" maxlength="4000" required></textarea><button class="btn primary" type="submit">${t('send')}</button></form>`,{type:'thread',id:String(id)}); $('#drawer').scrollTop=$('#drawer').scrollHeight;
}
async function refreshOpenThread(){
  const drawer=state.drawer,node=drawer?.type==='thread'?$(`[data-chat-thread="${drawer.id}"]`):null;if(!node)return;
  const data=await api(`/api/threads/${drawer.id}`);if(state.drawer!==drawer)return;
  node.innerHTML=threadMessages(data.items)||empty();$('#drawer').scrollTop=$('#drawer').scrollHeight;
}
async function openCustomer(id){
  const d=await api(`/api/customers/${id}`),u=d.user;
  const orders=d.orders.slice(0,10).map(o=>`<div class="priority"><span>ORD-${String(o.id).padStart(6,'0')} · ${esc(o.product_title)}</span><strong>${esc(statusText(o.status))}</strong></div>`).join('');
  openDrawer(`${drawerHead(t('profile'))}<div class="detail-grid">${detail(t('customer'),displayName(u))}${detail(t('phone'),u.phone)}${detail('Telegram ID',u.telegram_id)}${detail(t('age'),u.age)}${detail(t('gender'),u.gender)}${detail(t('height'),u.height_cm?`${u.height_cm} cm`:'—')}${detail(t('weight'),u.weight_kg?`${u.weight_kg} kg`:'—')}${detail(t('goal'),u.goal)}${detail(t('history'),u.training_history)}${detail(t('notes'),u.notes)}</div><div class="drawer-section"><h3>${t('orders')}</h3><div class="priority-list">${orders||empty()}</div></div>`,{type:'customer',id:String(id)});
}

document.addEventListener('click',async event=>{
  if(!event.target.closest('.custom-select'))closeCustomerFilters();
  const filterTrigger=event.target.closest('[data-filter-trigger]');if(filterTrigger){const field=filterTrigger.closest('.custom-select'),opening=!field.classList.contains('open');closeCustomerFilters(field);field.classList.toggle('open',opening);filterTrigger.setAttribute('aria-expanded',String(opening));if(opening)field.querySelector('[data-filter-option][aria-selected="true"]')?.focus();return;}
  const filterOption=event.target.closest('[data-filter-option]');if(filterOption){const field=filterOption.closest('[data-customer-filter]');state.customerFilters[field.dataset.customerFilter]=filterOption.dataset.value;state.pages.customers=1;renderCustomers();return;}
  const period=event.target.closest('[data-sales-period]');if(period){state.dashboardPeriod=period.dataset.salesPeriod;localStorage.setItem('dashboard-period',state.dashboardPeriod);renderDashboard();return;}
  const salesGate=event.target.closest('[data-sales-gate]');if(salesGate){const open=salesGate.dataset.salesGate==='open';if(!open&&!confirm(t('closeSalesConfirm')))return;try{await api('/api/sales-gate',{method:'POST',body:JSON.stringify({open})});toast(t('done'));renderDashboard();}catch(error){console.error(error);toast(t('error'),true);}return;}
  const quickNav=event.target.closest('[data-dashboard-nav]');if(quickNav){navigate(quickNav.dataset.dashboardNav);return;}
  if(event.target.closest('[data-dashboard-refresh]')){renderDashboard();return;}
  const nav=event.target.closest('[data-nav]');if(nav){navigate(nav.dataset.nav);return;}
  if(event.target.closest('[data-close]')){closeDrawer();return;}
  if(event.target.closest('[data-reset-customer-filters]')){state.customerFilters={q:'',activity:'all',product:'',sort:'recent'};state.pages.customers=1;renderCustomers();return;}
  const page=event.target.closest('[data-page]');if(page&&!page.disabled){state.pages[state.page]=Number(page.dataset.page);navigate(state.page);return;}
  const order=event.target.closest('[data-order]');if(order){openOrder(order.dataset.order);return;}
  const thread=event.target.closest('[data-thread]');if(thread){openThread(thread.dataset.thread);return;}
  const customer=event.target.closest('[data-customer]');if(customer){openCustomer(customer.dataset.customer);return;}
  if(event.target.closest('[data-toggle-info]')){$('#info-box').classList.toggle('hidden');return;}
  if(event.target.closest('[data-send-info]')){const box=$('#info-box'),message=$('textarea',box).value.trim(),id=$('[data-order-id]').dataset.orderId;if(!message)return;await perform(()=>api(`/api/orders/${id}/action`,{method:'POST',body:JSON.stringify({action:'needs_info',message})}));return;}
  const action=event.target.closest('[data-order-action]');if(action){if(action.dataset.orderAction==='reject_receipt'&&!confirm(t('reject')))return;const id=$('[data-order-id]').dataset.orderId;await perform(()=>api(`/api/orders/${id}/action`,{method:'POST',body:JSON.stringify({action:action.dataset.orderAction})}));return;}
});
document.addEventListener('input',event=>{const input=event.target.closest('[data-customer-search]');if(!input)return;state.customerFilters.q=input.value;clearTimeout(renderCustomers.searchTimer);renderCustomers.searchTimer=setTimeout(()=>{state.pages.customers=1;renderCustomers(true);},280);});
async function perform(task){try{await task();toast(t('done'));closeDrawer();navigate(state.page);}catch(error){console.error(error);toast(t('error'),true);}}
document.addEventListener('submit',async event=>{
  if(event.target.id==='reply-form'){event.preventDefault();const form=event.target,id=form.dataset.userId,message=form.message.value.trim(),button=$('[type="submit"]',form);if(!message)return;button.disabled=true;try{await api(`/api/threads/${id}/reply`,{method:'POST',body:JSON.stringify({message})});form.reset();await refreshOpenThread();if(state.page==='messages')await renderMessages();toast(t('done'));}catch(error){console.error(error);toast(t('error'),true);}finally{button.disabled=false;form.message.focus();}}
  if(event.target.id==='plan-form'){event.preventDefault();const id=$('[data-order-id]').dataset.orderId,form=new FormData(event.target);await perform(()=>api(`/api/orders/${id}/plan`,{method:'POST',body:form}));}
});
$('#theme-toggle').addEventListener('click',()=>{state.theme=state.theme==='dark'?'light':'dark';localStorage.setItem('theme',state.theme);applyTheme();});
$('#lang-toggle').addEventListener('click',()=>{state.lang=state.lang==='fa'?'en':'fa';localStorage.setItem('lang',state.lang);applyLanguage();navigate(state.page);});
$('#sidebar-toggle').addEventListener('click',()=>{state.sidebarCollapsed=!state.sidebarCollapsed;localStorage.setItem('sidebar-collapsed',state.sidebarCollapsed?'1':'0');applySidebar();});
$('#logout').addEventListener('click',async()=>{disconnectRealtime();await api('/api/logout',{method:'POST'});location.reload();});
$('#dev-login').addEventListener('click',async()=>{await fetch('/api/auth/dev',{method:'POST'});location.reload();});
document.addEventListener('keydown',event=>{
  const field=event.target.closest?.('.custom-select');
  if(event.key==='Escape'&&field?.classList.contains('open')){event.preventDefault();closeCustomerFilters();field.querySelector('[data-filter-trigger]')?.focus();return;}
  if(field&&['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();const trigger=field.querySelector('[data-filter-trigger]'),options=[...field.querySelectorAll('[data-filter-option]')];if(!field.classList.contains('open')){closeCustomerFilters(field);field.classList.add('open');trigger.setAttribute('aria-expanded','true');}const current=options.indexOf(document.activeElement),next=event.key==='Home'?0:event.key==='End'?options.length-1:event.key==='ArrowDown'?Math.min(current+1,options.length-1):Math.max(current<0?options.length:current-1,0);options[next]?.focus();return;}
  if(event.key==='Escape'){closeDrawer();return;}const customer=event.target.closest?.('[data-customer][role="button"]');if(customer&&['Enter',' '].includes(event.key)){event.preventDefault();openCustomer(customer.dataset.customer);}
});
window.addEventListener('online',()=>state.realtime?setConnection('connecting'):connectRealtime());
window.addEventListener('offline',()=>setConnection('offline'));
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&state.role)refreshRealtimeView();});
registerPwa();
bootstrap();
