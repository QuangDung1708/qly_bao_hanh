'use strict';
let csrf='';const ready=fetch('/api/session').then(r=>r.json()).then(d=>{csrf=d.csrf;});
const labels={serial:'Mã seri',model:'Sản phẩm',status:'Trạng thái',purchase_date:'Ngày mua / kích hoạt',exp_date:'Hạn bảo hành',rma_code:'Mã RMA',status_text:'Tiến độ',created_at:'Ngày tạo',technician:'Kỹ thuật viên',expected_date:'Dự kiến hoàn tất',center_id:'Trung tâm',center_name:'Điểm tiếp nhận',address:'Địa chỉ',phone:'Điện thoại',hours:'Giờ làm việc',directions:'Chỉ dẫn',part:'Linh kiện',quantity:'Tồn kho',stock_status:'Tình trạng kho',estimate:'Thời gian dự kiến',category:'Phân loại sơ bộ',cause:'Nguyên nhân có thể',severity:'Mức độ',disclaimer:'Lưu ý',message:'Thông báo',access_token:'Mã truy cập riêng — hãy lưu lại',flags:'Cảnh báo'};
const stateLabels={MANUFACTURER:'Có dấu hiệu lỗi kỹ thuật — sơ bộ',USER_FAULT:'Có dấu hiệu ngoại lực',MIXED:'Nhiều nguyên nhân — cần kiểm tra',UNKNOWN:'Chưa xác định',APPROVED_STP:'Đã duyệt tự động',PENDING_MANUAL_REVIEW:'Chờ xem xét thủ công',FLAGGED_FRAUD:'Tạm dừng do bất thường',IN_STOCK:'Còn hàng',LOW_STOCK:'Sắp hết',OUT_OF_STOCK:'Hết hàng'};
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
// Keep API timestamps in ISO format; format them only for display.
function formatDate(value) {
    if (typeof value !== 'string' || !value) return value;
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
        const parsed = new Date(value + 'T00:00:00Z');
        if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) return value;
        const [year, month, day] = value.split('-');
        return `${day}/${month}/${year}`;
    }
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)) return value;
    // Legacy timestamps without an offset are interpreted as UTC.
    const timestamp = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : value + 'Z';
    const parsed = new Date(timestamp);
    if (Number.isNaN(parsed.getTime())) return value;
    const parts = new Intl.DateTimeFormat('vi-VN', {
        timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
    }).formatToParts(parsed);
    const fields = Object.fromEntries(parts.map(part => [part.type, part.value]));
    return `${fields.day}/${fields.month}/${fields.year} ${fields.hour}:${fields.minute}:${fields.second}`;
}
function formatValue(key, value) {
    if (['created_at', 'expected_date', 'purchase_date', 'exp_date', 'activated_at'].includes(key)) return formatDate(value);
    if (key === 'technician' && typeof value === 'string') return value.normalize('NFC').replace(/\s*\(\s*mẫu\s*\)\s*$/iu, '').trim();
    return stateLabels[value] || String(value);
}
function render(obj,root){for(const [k,v] of Object.entries(obj)){if(['success','genuine','reservation','timeline','retrieval','disclaimer'].includes(k)||v===null)continue;if(Array.isArray(v)){if(!v.length)continue;for(const item of v){if(typeof item==='object'){const card=el('div');render(item,card);root.append(card,el('hr'));}else root.append(el('p',String(item)));}}else if(typeof v==='object'){render(v,root);}else{const row=el('p');row.append(el('strong',(labels[k]||k)+': '));row.append(el('span',formatValue(k,v),k==='access_token'?'token':''));root.append(row);}}}
async function api(endpoint,payload){await ready;const r=await fetch('/api/'+endpoint,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(payload)});const d=await r.json();return d;}
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.panel').forEach(x=>x.hidden=x.id!==b.dataset.tab);}));
document.querySelectorAll('form[data-api]').forEach(form=>form.addEventListener('submit',async e=>{e.preventDefault();const target=form.parentElement.querySelector('.result');const button=form.querySelector('button');const payload=Object.fromEntries(new FormData(form));if(form.querySelector('[name=paid_consent]'))payload.paid_consent=form.elements.paid_consent.checked;target.replaceChildren(el('p','Đang xử lý...'));target.classList.remove('error');button.disabled=true;try{const d=await api(form.dataset.api,payload);target.replaceChildren();target.classList.toggle('error',!d.success);render(d,target);}catch(err){target.replaceChildren(el('p','Không kết nối được máy chủ. Vui lòng thử lại.'));target.classList.add('error');}finally{button.disabled=false;}}));
function toggleChat(show){const w=document.getElementById('chat-window');w.hidden=!show;document.getElementById('chat-toggle').setAttribute('aria-expanded',String(show));if(show)document.getElementById('chat-input').focus();}
document.getElementById('chat-toggle').onclick=()=>toggleChat(document.getElementById('chat-window').hidden);
document.getElementById('chat-close').onclick=()=>toggleChat(false);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){toggleChat(false);document.getElementById('chat-toggle').focus();}});
document.getElementById('chat-form').addEventListener('submit',async e=>{e.preventDefault();const input=document.getElementById('chat-input');const msg=input.value.trim();if(!msg)return;const body=document.getElementById('chat-body');const button=e.target.querySelector('button');body.append(el('div',msg,'bubble user'));input.value='';const pending=el('div','Trợ lý đang tìm thông tin...','bubble bot');body.append(pending);body.scrollTop=body.scrollHeight;button.disabled=true;try{const d=await api('chat',{message:msg});pending.textContent=d.reply||d.message||'Chưa có câu trả lời.';}catch(err){pending.textContent='Kết nối thất bại. Vui lòng thử lại.';}finally{button.disabled=false;body.scrollTop=body.scrollHeight;input.focus();}});
