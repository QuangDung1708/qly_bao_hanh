from flask import Flask, request, jsonify, render_template, session, g, Response
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import calendar, csv, sqlite3, secrets, hashlib, hmac, json, os, re
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from ai_engine import diagnose, norm, Knowledge

BASE=Path(__file__).resolve().parent
STATES={'APPROVED_STP':'Đã duyệt tự động', 'PENDING_MANUAL_REVIEW':'Chờ kỹ thuật viên xem xét', 'FLAGGED_FRAUD':'Tạm dừng — bất thường', 'RECEIVED':'Đã tiếp nhận', 'IN_DIAGNOSIS':'Đang chẩn đoán', 'REPAIRING':'Đang sửa chữa', 'COMPLETED':'Hoàn tất', 'RETURNED':'Đã giao lại khách'}

LEGACY_DISPLAY_NAMES = {
    'Bàn phím demo 12 tháng': 'Bàn phím cơ 12 tháng',
    'Trung tâm mẫu Hà Nội': 'Trung tâm bảo hành Hà Nội',
    'Trung tâm mẫu Thái Nguyên': 'Trung tâm bảo hành Thái Nguyên',
    'Trung tâm mẫu TP.HCM': 'Trung tâm bảo hành TP.HCM',
    'KTV Hà Nội (mẫu)': 'KTV Hà Nội',
    'KTV Thái Nguyên (mẫu)': 'KTV Thái Nguyên',
    'KTV TP.HCM (mẫu)': 'KTV TP.HCM',
}

def display_name(value):
    return LEGACY_DISPLAY_NAMES.get(value, value)

def create_app(config=None):
    app=Flask(__name__,template_folder='Templates')
    instance=BASE/'instance';instance.mkdir(exist_ok=True)
    keyfile=instance/'local.key'
    if not keyfile.exists():
        fd=os.open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(secrets.token_bytes(32))
    key=keyfile.read_bytes()
    app.config.update(SECRET_KEY=key, DATABASE=str(BASE/'warranty.db'), MAX_CONTENT_LENGTH=32768, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE')=='1')
    if config:app.config.update(config)
    aes=AESGCM(key);kb=Knowledge(BASE/'knowledge.json')
    def encrypt(value):
        nonce=secrets.token_bytes(12);return (nonce+aes.encrypt(nonce,value.encode(),None)).hex()
    def decrypt(value):
        if not value:return ''
        b=bytes.fromhex(value);return aes.decrypt(b[:12],b[12:],None).decode()
    def digest(value):return hmac.new(key,value.encode(),hashlib.sha256).hexdigest()
    def db():
        if 'db' not in g:
            g.db=sqlite3.connect(app.config['DATABASE'],timeout=10);g.db.row_factory=sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db
    @app.teardown_appcontext
    def close(error):
        c=g.pop('db',None)
        if c:c.close()
    def init_db():
        c=db()
        c.executescript('''CREATE TABLE IF NOT EXISTS products(serial TEXT PRIMARY KEY, model TEXT, status TEXT, exp_date TEXT);
        CREATE TABLE IF NOT EXISTS rma_requests(rma_code TEXT PRIMARY KEY,serial TEXT,issue_desc TEXT,status TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS centers(center_id TEXT PRIMARY KEY,name TEXT,location TEXT,stock_status TEXT);
        CREATE TABLE IF NOT EXISTS inventory(center_id TEXT,part TEXT,quantity INTEGER,lead_days INTEGER,PRIMARY KEY(center_id,part));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,serial TEXT,event TEXT,created_at TEXT);
        ''')
        additions={'products':{'purchase_date':'TEXT','customer_name':'TEXT','phone_cipher':'TEXT','phone_hash':'TEXT','owner_hash':'TEXT','activated_at':'TEXT','months':'INTEGER DEFAULT 12'},'rma_requests':{'phone_hash':'TEXT','address_cipher':'TEXT','delivery':'TEXT','center_id':'TEXT','technician':'TEXT','expected_date':'TEXT','approval':'TEXT','diagnosis':'TEXT','flags':'TEXT DEFAULT \'[]\''},'centers':{'technician':'TEXT'}}
        for table,cols in additions.items():
            existing={r['name'] for r in c.execute('PRAGMA table_info('+table+')')}
            for name,typ in cols.items():
                if name not in existing:c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {typ}')
        if not c.execute('SELECT 1 FROM products LIMIT 1').fetchone():
            with (BASE/'products.csv').open(encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):c.execute('INSERT INTO products(serial,model,status,exp_date) VALUES (?,?,?,?)',tuple(row[k] for k in ['serial','model','status','exp_date']))
        # An explicit demo product does not alter the supplied 15 original products.
        c.execute("INSERT OR IGNORE INTO products(serial,model,status,months) VALUES ('SN-DEMO-001','Bàn phím cơ 12 tháng','Chưa kích hoạt',12)")
        c.execute("UPDATE products SET months=24 WHERE serial LIKE 'SN-VGA-%' OR serial LIKE 'SN-CPU-%'")
        for center in [('CT-HN','Trung tâm bảo hành Hà Nội','Cầu Giấy, Hà Nội','IN_STOCK','KTV Hà Nội'),('CT-TN','Trung tâm bảo hành Thái Nguyên','Quyết Thắng, Thái Nguyên','IN_STOCK','KTV Thái Nguyên'),('CT-HCM','Trung tâm bảo hành TP.HCM','Quận 1, TP.HCM','LOW_STOCK','KTV TP.HCM')]:
            c.execute('INSERT OR IGNORE INTO centers VALUES (?,?,?,?,?)',center)
            c.execute('UPDATE centers SET technician=COALESCE(technician,?) WHERE center_id=?',(center[4],center[0]))
            for part,qty,lead in [('Bàn phím',8,0),('Màn hình',0,5),('Chuột',2,0)]:c.execute('INSERT OR IGNORE INTO inventory VALUES (?,?,?,?)',(center[0],part,qty,lead))
        c.commit()
    with app.app_context():init_db()
    def fail(message,status=400,**extra):return dict(success=False,message=message,**extra),status
    def valid_serial(s):return bool(re.fullmatch(r'[A-Z0-9]+(?:-[A-Z0-9]+)*',s)) and 5<=len(s)<=40
    def owned(p):return p['serial'] in session.get('owned',[])
    def require_owner(p):
        if not owned(p):raise PermissionError('Vui lòng định danh bằng mã truy cập được cấp khi kích hoạt. SĐT/seri không phải mật khẩu.')
    def warranty(p):
        active=bool(p['purchase_date']) or p['status']=='Đã kích hoạt'
        expired=bool(p['exp_date']) and p['exp_date']<date.today().isoformat()
        return dict(serial=p['serial'],model=display_name(p['model']),status='Đã hết hạn' if expired else 'Đã kích hoạt — Còn hạn' if active else 'Chưa kích hoạt',purchase_date=p['purchase_date'],exp_date=p['exp_date'],genuine=True)
    def locate(data):
        q=norm(str(data.get('location','')).strip())
        if not q:return fail('Vui lòng nhập tỉnh/thành hoặc quận/huyện.')
        centers=list(db().execute('SELECT * FROM centers'))
        candidates=[c for c in centers if q in norm(c['location']) or any(alias in q and alias in norm(c['location']) for alias in ['ha noi','thai nguyen','hcm']) or ('ho chi minh' in q and c['center_id']=='CT-HCM')]
        if not candidates:return fail('Chưa tìm thấy trung tâm trong khu vực này. Bạn có thể gửi bưu điện tới trung tâm Hà Nội hoặc TP.HCM.',404)
        c=candidates[0]
        return dict(success=True,center_id=c['center_id'],center_name=display_name(c['name']),address=c['location'],technician=display_name(c['technician']),phone='1900-8888',hours='08:00–17:30, Thứ 2–Thứ 7',directions='Đến địa chỉ trên và cung cấp mã RMA.')
    def check(data):
        q=str(data.get('query',data.get('serial',''))).strip().upper()
        if re.fullmatch(r'0\d{9}',q):
            rows=db().execute('SELECT * FROM products WHERE phone_hash=?',(digest(q),)).fetchall()
            rows=[p for p in rows if owned(p)]
            if not rows:raise PermissionError('Không có sản phẩm đã định danh trong phiên này gắn với SĐT.')
            return dict(success=True,products=[warranty(p) for p in rows])
        if not valid_serial(q):return fail('Mã seri không đúng định dạng.')
        p=db().execute('SELECT * FROM products WHERE serial=?',(q,)).fetchone()
        if not p:return fail('Mã seri không có trong hệ thống. Vui lòng kiểm tra lại.',404)
        return dict(success=True,**warranty(p))
    def activate(data):
        text=str(data.get('text',''))
        matches=re.findall(r'\bSN-?[A-Z0-9]+(?:-[A-Z0-9]+)*\b',text.upper())
        serial=str(data.get('serial') or (matches[0] if len(matches)==1 else '')).strip().upper()
        m=re.search(r'\b(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b',text)
        raw=str(data.get('purchase_date') or (m.group(1) if m else ''))
        try:buy=datetime.strptime(raw,'%d/%m/%Y').date() if '/' in raw else date.fromisoformat(raw)
        except ValueError:return fail('Không nhận diện được ngày mua. Nhập ngày YYYY-MM-DD hoặc DD/MM/YYYY.')
        if buy>date.today():return fail('Ngày mua không được lớn hơn ngày hiện tại.')
        phone=str(data.get('phone','')).strip();name=str(data.get('name','')).strip()
        if not valid_serial(serial) or not re.fullmatch(r'0\d{9}',phone) or not name:return fail('Cần một seri hợp lệ, họ tên và SĐT 10 chữ số.')
        c=db();c.execute('BEGIN IMMEDIATE')
        p=c.execute('SELECT * FROM products WHERE serial=?',(serial,)).fetchone()
        if not p:return fail('Seri không tồn tại.',404)
        if p['owner_hash'] or p['status']=='Đã kích hoạt':return fail('Seri đã kích hoạt trước đó. Ngày kích hoạt: '+str(p['purchase_date'] or 'dữ liệu cũ chưa có ngày'),409)
        if data.get('model') and norm(data['model'].strip())!=norm(p['model']):return fail('Model không khớp dữ liệu sản phẩm.')
        count=c.execute("SELECT count(*) FROM products WHERE phone_hash=? AND activated_at>=?",(digest(phone),(datetime.now(timezone.utc)-timedelta(days=1)).isoformat())).fetchone()[0]
        if count>=5:
            c.execute('INSERT INTO audit(serial,event,created_at) VALUES (?,?,?)',(serial,'FLAGGED_FRAUD_ACTIVATION',datetime.now(timezone.utc).isoformat()));c.commit()
            return fail('SĐT đã kích hoạt 5 seri trong 24 giờ. Cần kiểm tra thủ công.',409)
        total=buy.year*12+buy.month-1+(p['months'] or 12);year,month=divmod(total,12);month+=1
        end=date(year,month,min(buy.day,calendar.monthrange(year,month)[1]))
        token=secrets.token_urlsafe(24)
        c.execute('UPDATE products SET purchase_date=?,exp_date=?,status=?,customer_name=?,phone_cipher=?,phone_hash=?,owner_hash=?,activated_at=? WHERE serial=?',(buy.isoformat(),end.isoformat(),'Đã kích hoạt',encrypt(name),encrypt(phone),digest(phone),digest(token),datetime.now(timezone.utc).isoformat(),serial));c.commit()
        session['owned']=list(set(session.get('owned',[])+[serial]))
        return dict(success=True,serial=serial,model=display_name(p['model']),purchase_date=buy.isoformat(),exp_date=end.isoformat(),access_token=token,message='Đã kích hoạt. Lưu mã truy cập riêng để định danh trên trình duyệt khác; không chia sẻ mã này.')
    def identify(data):
        serial=str(data.get('serial','')).upper().strip();token=str(data.get('access_token',''))
        p=db().execute('SELECT * FROM products WHERE serial=?',(serial,)).fetchone()
        if not p or not p['owner_hash'] or not hmac.compare_digest(p['owner_hash'],digest(token)):
            return fail('Thông tin định danh không hợp lệ.',403)
        session['owned']=list(set(session.get('owned',[])+[serial]));return dict(success=True,message='Đã định danh sản phẩm trong phiên.')
    def submit(data):
        serial=str(data.get('serial','')).upper().strip();issue=str(data.get('issue_desc','')).strip()
        if not valid_serial(serial) or not 8<=len(issue)<=2000:return fail('Cần seri hợp lệ và mô tả lỗi từ 8 đến 2.000 ký tự.')
        c=db();c.execute('BEGIN IMMEDIATE');p=c.execute('SELECT * FROM products WHERE serial=?',(serial,)).fetchone()
        if not p:return fail('Seri không tồn tại.',404)
        require_owner(p)
        delivery=data.get('delivery','');address=str(data.get('address','')).strip()
        if delivery not in ('Trực tiếp','Bưu điện') or len(address)<5:return fail('Cần hình thức gửi/nhận và địa chỉ liên hệ.')
        center=c.execute('SELECT * FROM centers WHERE center_id=?',(data.get('center_id'),)).fetchone()
        if not center:return fail('Vui lòng chọn trung tâm tiếp nhận hợp lệ.')
        now=datetime.now(timezone.utc);flags=[]
        previous=c.execute("SELECT rma_code FROM rma_requests WHERE serial=? AND status NOT IN ('COMPLETED','RETURNED') AND created_at>=?",(serial,(now-timedelta(days=7)).date().isoformat())).fetchone()
        if previous:return fail('Đã có hồ sơ đang xử lý trong 7 ngày; hãy tra cứu tiến độ.',409,rma_code=previous['rma_code'])
        count=c.execute('SELECT count(*) FROM rma_requests WHERE serial=? AND created_at>=?',(serial,(now-timedelta(days=30)).date().isoformat())).fetchone()[0]
        phonecount=c.execute('SELECT count(DISTINCT serial) FROM rma_requests WHERE phone_hash=? AND created_at>=?',(p['phone_hash'],(now-timedelta(days=1)).isoformat())).fetchone()[0]
        if count>=2:flags.append('Vượt ngưỡng 2 đơn/seri/30 ngày')
        if phonecount>=5:flags.append('Tần suất SĐT bất thường trong 24 giờ')
        d=diagnose(issue);paid=data.get('paid_consent') is True
        expired=not p['exp_date'] or p['exp_date']<date.today().isoformat()
        needs_paid=expired or d['category']=='USER_FAULT'
        if needs_paid and not paid:return fail('Ngoài điều kiện bảo hành miễn phí. Xác nhận sửa chữa có phí nếu muốn gửi hồ sơ; chưa thu tiền.',422,diagnosis=d)
        approval='FLAGGED_FRAUD' if flags else 'PENDING_MANUAL_REVIEW' if d['category'] in ('UNKNOWN','MIXED') else 'APPROVED_STP'
        for _ in range(50):
            code=f'RMA-{now.year}-{secrets.randbelow(90000)+10000}'
            if not c.execute('SELECT 1 FROM rma_requests WHERE rma_code=?',(code,)).fetchone():break
        else:return fail('Chưa cấp được mã hồ sơ, vui lòng thử lại.',503)
        eta=(date.today()+timedelta(days=2)).isoformat()
        c.execute('''INSERT INTO rma_requests(rma_code,serial,issue_desc,status,created_at,phone_hash,address_cipher,delivery,center_id,technician,expected_date,approval,diagnosis,flags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(code,serial,issue,approval,now.isoformat(),p['phone_hash'],encrypt(address),delivery,center['center_id'],center['technician'],eta,approval,json.dumps(d,ensure_ascii=False),json.dumps(flags,ensure_ascii=False)))
        c.commit()
        return dict(success=True,rma_code=code,status=approval,diagnosis=d,flags=flags,expected_date=eta,message=STATES[approval]+'. Ghi mã RMA bên ngoài kiện hàng.')
    def track(data):
        q=str(data.get('query',data.get('rma_code',''))).upper().strip()
        if re.fullmatch(r'RMA-\d{4}-\d{5}',q):rows=db().execute('SELECT * FROM rma_requests WHERE rma_code=?',(q,)).fetchall()
        elif re.fullmatch(r'0\d{9}',q):rows=db().execute('SELECT * FROM rma_requests WHERE phone_hash=?',(digest(q),)).fetchall()
        else:return fail('Nhập SĐT 10 chữ số hoặc mã RMA-YYYY-XXXXX.')
        allowed=set(session.get('owned',[]));rows=[r for r in rows if r['serial'] in allowed]
        if not rows:return fail('Không tìm thấy hồ sơ thuộc sản phẩm đã định danh trong phiên này.',404)
        return dict(success=True,requests=[dict(rma_code=r['rma_code'],serial=r['serial'],status=r['status'],status_text=STATES.get(r['status'],r['status']),created_at=r['created_at'],technician=display_name(r['technician']),expected_date=r['expected_date'],center_id=r['center_id'],timeline=[dict(status=r['status'],at=r['created_at'])]) for r in rows])
    def stock(data):
        center=str(data.get('center_id','CT-TN'));part=norm(str(data.get('part','')).strip())
        if not part:return fail('Cần nhập tên linh kiện.')
        rows=db().execute('SELECT * FROM inventory WHERE center_id=?',(center,)).fetchall()
        rows=[r for r in rows if part in norm(r['part']) or norm(r['part']) in part]
        if not rows:return fail('Không tìm thấy linh kiện này trong kho.',404)
        return dict(success=True,inventory=[dict(part=r['part'],center_id=r['center_id'],quantity=r['quantity'],stock_status='OUT_OF_STOCK' if r['quantity']==0 else 'LOW_STOCK' if r['quantity']<=2 else 'IN_STOCK',estimate='3–5 ngày làm việc' if r['quantity']==0 else '24–48 giờ',reservation=False) for r in rows])
    operations={'check_warranty':check,'activate':activate,'identify':identify,'submit_rma':submit,'track_rma':track,'locate_center':locate,'stock':stock,'diagnose':lambda d:dict(success=True,diagnosis=diagnose(str(d.get('issue_desc',''))))}
    def chat(data):
        msg=str(data.get('message','')).strip();t=norm(msg)
        if not msg:return fail('Vui lòng nhập tin nhắn.')
        rma=re.search(r'RMA-\d{4}-\d{5}',msg.upper());sn=re.search(r'\bSN-?[A-Z0-9]+(?:-[A-Z0-9]+)*\b',msg.upper());phone=re.search(r'\b0\d{9}\b',msg)
        result=None
        if rma:result=track({'query':rma.group()})
        elif sn and any(k in t for k in ['kiem tra','bao hanh','tra cuu']):result=check({'serial':sn.group()})
        elif phone and 'tien do' in t:result=track({'query':phone.group()})
        elif phone and 'tra cuu' in t:result=check({'query':phone.group()})
        elif any(k in t for k in ['trung tam','dia chi']):result=locate({'location':msg})
        elif any(k in t for k in ['linh kien','con hang','ton kho']):
            part=next((p for p in ['Bàn phím','Màn hình','Chuột'] if norm(p) in t),'')
            result=stock({'part':part,'center_id':'CT-HCM' if 'hcm' in t else 'CT-HN' if 'ha noi' in t else 'CT-TN'})
        elif any(k in t for k in ['liet','hong','khong len','rung lac','chop tat']):result=operations['diagnose']({'issue_desc':msg})
        if result is not None:
            if isinstance(result,tuple):result=result[0]
            if isinstance(result.get('diagnosis'),dict):
                result={**result,'diagnosis':{k:v for k,v in result['diagnosis'].items() if k!='disclaimer'}}
            return dict(success=True,reply=json.dumps(result,ensure_ascii=False,indent=2),sources=['Hệ thống bảo hành'])
        return dict(success=True,**kb.query(msg))
    operations['chat']=chat
    @app.get('/')
    def home():return render_template('index.html')
    @app.get('/api/session')
    def session_info():
        if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(24)
        return jsonify(csrf=session['csrf'],owned=session.get('owned',[]))
    @app.before_request
    def protect():
        if request.method=='POST':
            if not request.is_json:return jsonify(success=False,message='Yêu cầu JSON UTF-8.'),415
            if not session.get('csrf') or not hmac.compare_digest(str(request.headers.get('X-CSRF-Token','')),session['csrf']):return jsonify(success=False,message='Phiên hết hạn, tải lại trang.'),403
    @app.post('/api/<operation>')
    def api(operation):
        if operation not in operations:return jsonify(success=False,message='API không tồn tại.'),404
        payload=request.get_json(silent=True)
        if not isinstance(payload,dict):return jsonify(success=False,message='JSON phải là object.'),400
        if any(not isinstance(v,(str,bool,int,float,type(None))) for v in payload.values()):return jsonify(success=False,message='Trường dữ liệu sai kiểu.'),400
        # Prevent type confusion and pathological payloads before business logic.
        for k,v in payload.items():
            if k=='paid_consent' and not isinstance(v,bool):return jsonify(success=False,message='paid_consent phải là boolean.'),400
            if k!='paid_consent' and not isinstance(v,str):return jsonify(success=False,message='Các trường văn bản phải là chuỗi.'),400
        try:
            result=operations[operation](payload)
            if isinstance(result,tuple):return jsonify(result[0]),result[1]
            return jsonify(result)
        except PermissionError as e:return jsonify(success=False,message=str(e)),403
    @app.after_request
    def headers(response):
        response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'"})
        return response
    return app

if __name__=='__main__':create_app().run(host='127.0.0.1',port=int(os.getenv('PORT','5000')),debug=False)
