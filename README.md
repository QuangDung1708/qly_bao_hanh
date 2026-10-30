# ICTU Warranty Care — bản chỉnh sửa cho Windows / VS Code

## Chạy nhanh
1. Cài **Python 3.12 64-bit** (bật Python Launcher), VS Code và extension Python của Microsoft.
2. Giải nén toàn bộ ZIP; dùng VS Code → File → Open Folder mở thư mục `Qly_Bao_Hanh` có `app.py`.
3. Chạy `run_windows.bat` bằng double-click hoặc gõ `.\run_windows.bat` trong terminal VS Code. Lần đầu cần Internet để cài thư viện.
4. Mở `http://127.0.0.1:5000` trong trình duyệt. Dừng bằng Ctrl+C.

Hoặc PowerShell, không cần thay đổi ExecutionPolicy:
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```
Để dùng F5: chọn interpreter `.venv\Scripts\python.exe`; chọn cấu hình `Warranty Care (Windows)`. Nếu cổng 5000 đang bận: `$env:PORT="5001"`, chạy lại và mở cổng mới.

## Kịch bản trình bày
- Tra cứu `SN-KEY-001`; tra cứu `SN-VGA-003` để thấy hết hạn.
- Kích hoạt `SN-DEMO-001` với ngày mua hiện tại, họ tên bất kỳ và SĐT giả 10 chữ số bắt đầu bằng 0. Lưu mã truy cập được cấp (chỉ hiển thị lần đầu).
- Có thể dán `Hóa đơn SN-DEMO-001 ngày DD/MM/YYYY`; thay ngày bằng ngày hợp lệ, hoặc nhập ngày vào form. Model lấy từ DB theo seri và chính sách tháng mẫu. Các Model VGA/CPU dùng 24 tháng; còn lại 12 tháng: đây là cấu hình demo, PDF chưa cung cấp ánh xạ Model cụ thể.
- Tạo RMA: `Bàn phím bị liệt hàng phím số`, địa chỉ mẫu, chọn trung tâm và hình thức gửi.
- Lưu mã RMA, tra cứu lại bằng mã hoặc SĐT trong cùng phiên. Gửi lại sẽ bị chặn trùng trong 7 ngày.
- Linh kiện: Bàn phím → còn hàng, Chuột → sắp hết, Màn hình → hết hàng.
- Chat: `Kiểm tra bảo hành SN-KEY-001`, `Tìm trung tâm Thái Nguyên`, `Linh kiện màn hình còn hàng không?`, `Pin bảo hành bao lâu?`, `Máy bị đơ xử lý thế nào?`.
- Trên trình duyệt khác, định danh bằng seri + mã truy cập riêng trước khi xem RMA. Không dùng SĐT làm mật khẩu.

## Dữ liệu và sao lưu
Bản GitHub không chứa database hoặc lịch sử khách hàng từ tệp gốc. Khi chạy lần đầu, ứng dụng tự tạo `warranty.db` từ 15 sản phẩm mẫu trong `products.csv`, bổ sung `SN-DEMO-001` và các trung tâm/kho mẫu. Nếu dùng database cũ tại máy của bạn, migration bổ sung schema không xóa hồ sơ; dữ liệu cũ chưa có chủ sở hữu cần đối soát ngoại tuyến trước khi gán quyền.

Sau lần chạy đầu, khóa AES-256 và chữ ký phiên được tạo tại `instance/local.key`. Không gửi khóa cho người khác, không commit khóa lên Git. Sao lưu **cả DB và khóa** khi ứng dụng đã dừng; mất khóa sẽ không giải mã được dữ liệu mới. Khóa cục bộ phục vụ demo, không phải hệ thống quản lý khóa production. Không commit database hoặc khóa mã hóa lên GitHub.

## Kiểm thử
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```
28 kiểm thử nghiệp vụ tự động dùng DB tạm, không ghi đè DB của bạn. Kết quả trên máy kiểm thử Python 3.12: 28 passed. Chưa thực thi trực tiếp trên Windows; các lệnh Windows được cung cấp để bạn chạy bằng VS Code.

Kiểm tra định dạng giao diện (tùy chọn, cần Node.js):
```powershell
node test_display.cjs
```
Chatbot trả kết quả chẩn đoán, tra cứu sản phẩm, tiến độ, trung tâm và linh kiện bằng tiếng Việt thay vì hiển thị JSON. Kiểm thử Python có các tình huống trả lời này và quyền truy cập hồ sơ qua chat.

6 trường hợp kiểm tra chuyển UTC sang giờ Việt Nam, ngày chỉ có ngày/tháng/năm, dữ liệu không hợp lệ và tên kỹ thuật viên cũ. Ngày giờ trên thẻ kết quả hiển thị theo `Asia/Ho_Chi_Minh`; timestamp trong API/database vẫn giữ ISO để bảo toàn thời điểm gốc. Sau khi thay `app.py`, dừng server bằng Ctrl+C rồi chạy lại; thay cả `Templates/index.html` và `static/app.js`, sau đó nhấn Ctrl+F5 trên trình duyệt. Không xóa `warranty.db` hoặc `instance/local.key`.

## Giới hạn trung thực theo SRD
Đây là **prototype chạy offline sau khi cài thư viện**, không đạt toàn bộ đặc tả production trong PDF. Báo cáo đối chiếu được bàn giao riêng trong cuộc trò chuyện, không đưa lên GitHub.
- Trích xuất và chẩn đoán dùng regex/bộ quy tắc, chưa phải NER/LLM học máy; không kết luận chắc chắn lỗi NSX.
- Trợ lý có vector TF-IDF/cosine và nguồn trích dẫn; trả lời trích xuất, chưa phải RAG sinh câu trả lời bằng LLM/embeddings/Chroma. Tri thức mẫu do bản sửa bổ sung và gắn nhãn rõ; chưa được nhà sản xuất phê duyệt.
- `knowledge.json` tự nạp lại khi thay đổi, nhưng chưa có luồng quản trị nhập PDF/DOCX. Không có admin dashboard theo phạm vi PDF.
- Các form thực hiện đầy đủ hơn chatbot. Chat chưa hỗ trợ hội thoại nhiều lượt để kích hoạt/tạo đơn trực tiếp. UI hiển thị trạng thái đang xử lý, chưa streaming token.
- SQLite được giữ để chạy thuận tiện trên Windows, chưa thay sang PostgreSQL/MySQL hoặc tách AI thành service REST/gRPC.
- Định danh bằng token chỉ là bản demo; kích hoạt lần đầu chưa có OTP/đối soát hóa đơn nên chưa bảo đảm người kích hoạt là chủ sở hữu thật. Bộ lọc prompt là biện pháp giới hạn, không cam kết chống mọi tấn công.
- Chưa có cập nhật trạng thái của kỹ thuật viên, giữ hàng, dự báo học máy hay dữ liệu doanh nghiệp thật. Tiến độ đọc DB thật theo request nhưng lịch sự kiện chỉ có trạng thái hiện tại; không giả tạo lịch sử đã sửa chữa.
- Không công bố đạt 500 người đồng thời, SLA 99.9%, TLS 1.3, 2FA, WCAG AA, LLM fallback hoặc RTO/RPO; chưa có kiểm định tương ứng. Flask dev server chỉ dùng cục bộ.
- PDF tự mâu thuẫn giữa “không admin” và NFR yêu cầu 2FA admin; phản hồi 5 giây ở §2.4 nhưng ≤3 giây ở §3.2; sao lưu ngày không bảo đảm RPO <15 phút. Báo cáo đối chiếu nêu hướng làm rõ, không sửa PDF gốc.

## Tải mã nguồn từ GitHub

Chọn **Code → Download ZIP**, giải nén và mở thư mục có `app.py` bằng VS Code, sau đó chạy `run_windows.bat`. Repository chỉ chứa mã nguồn, cấu hình, kiểm thử và dữ liệu sản phẩm mẫu; không chứa báo cáo/slide, lịch sử bảo hành, khóa mã hóa, môi trường ảo hoặc cache.
