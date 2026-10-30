"""Local, extractive vector retrieval. No claim of an LLM or semantic embeddings."""
import re
import unicodedata
from pathlib import Path
import json
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DISCLAIMER = 'Kết quả chẩn đoán mang tính chất tham khảo sơ bộ dựa trên mô tả của bạn; kỹ thuật viên xác nhận khi tiếp nhận.'
def norm(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower().replace('đ','d')) if unicodedata.category(c) != 'Mn')

def diagnose(text):
    t = norm(text)
    if len(t.split()) < 4 or t.strip() in ('may hong roi', 'thiet bi bi hong'):
        return dict(category='UNKNOWN', cause='Bạn có thể mô tả rõ hiện tượng: liệt phím, không lên nguồn, tiếng kêu, thời điểm xảy ra?', severity='Chưa xác định', disclaimer=DISCLAIMER)
    # Remove explicit negation before evaluating user damage; do not label bare “nước/cháy” as user fault.
    t = re.sub(r'khong (?:bi |he |tung )?(?:roi vo|roi|vao nuoc|do nuoc|va dap|thao mo|mat tem)', '', t)
    external = any(x in t for x in ['roi vo','lam roi','bi roi','vao nuoc','do nuoc','do chat long','va dap','tu y thao','mat tem','rach tem','dap vo','nguon dien ngoai'])
    groups = [(['liet','ban phim','phim khong'], 'Cụm phím / kết nối bàn phím'), (['man hinh','soc','chop tat'], 'Tín hiệu / cụm màn hình'), (['khong len nguon','khong bat'], 'Bộ nguồn / kết nối cấp điện'), (['rung lac','keu to','long giat'], 'Giảm xóc / lồng giặt'), (['chuot','double click'], 'Công tắc / kết nối chuột'), (['do may','treo','dung hinh'], 'Phần mềm / kết nối thiết bị')]
    cause = next((cause for keys,cause in groups if any(k in t for k in keys)), None)
    category = 'MIXED' if external and cause else 'USER_FAULT' if external else 'MANUFACTURER' if cause else 'UNKNOWN'
    return dict(category=category, cause=cause or ('Tác động ngoại lực / chất lỏng' if external else 'Chưa có đủ tri thức; cần kỹ thuật viên kiểm tra.'), severity='Cần kiểm tra trực tiếp' if external else 'Sơ bộ', disclaimer=DISCLAIMER)

class Knowledge:
    def __init__(self, path): self.path=Path(path); self.signature=None
    def query(self, question):
        t=norm(question)
        if any(x in t for x in ['ignore previous','bo qua chi dan','system prompt','dump database','liet ke so dien thoai']):
            return {'reply':'Tôi chỉ hỗ trợ nghiệp vụ bảo hành và không cung cấp dữ liệu riêng tư hay chỉ dẫn nội bộ.', 'sources':[]}
        signature=self.path.stat().st_mtime_ns
        if signature != self.signature:
            self.docs=json.loads(self.path.read_text(encoding='utf-8'))
            self.vectorizer=TfidfVectorizer(analyzer='char_wb', ngram_range=(3,5), preprocessor=norm)
            self.matrix=self.vectorizer.fit_transform([d['keywords']+' '+d['text'] for d in self.docs]);self.signature=signature
        scores=cosine_similarity(self.vectorizer.transform([question]),self.matrix)[0]
        candidates=[i for i,d in enumerate(self.docs) if any(norm(k) in t for k in d['keywords'].split('|'))]
        if 'pin' in t.split(): candidates=[i for i,d in enumerate(self.docs) if d['keywords']=='pin']
        i=max(candidates,key=lambda i:scores[i]) if candidates else int(scores.argmax());doc=self.docs[i]
        if (scores[i]<0.06 and not candidates) or not any(norm(k) in t for k in doc['keywords'].split('|')):
            return {'reply':'Chưa tìm thấy thông tin phù hợp cho câu hỏi này. Vui lòng liên hệ bộ phận chăm sóc khách hàng hoặc mô tả rõ hơn.', 'sources':[]}
        return {'reply':doc['text']+'\nNếu chưa khắc phục được, hãy tạo hồ sơ RMA.', 'sources':[doc['source']], 'retrieval':'TF-IDF / cosine, trả lời trích xuất'}
