# Kiến trúc — LVC Manager Profile, đường "Quét bài nhóm" (v1, 2026-09-05)

Tài liệu này mô tả phần kiến trúc mà sprint congcode2 "quét nhóm ra đủ số bài"
chạm tới. Phần còn lại của tool (đăng bài, tạo page, proxy...) có ghi nhớ riêng.

## Kiến trúc & công nghệ
Monolith desktop. Python 3.13 [BIET `py -V`], customtkinter [BIET import],
websockets [BIET import] nói chuyện WebDriver BiDi với Firefox Portable 154
[BIET: Firefox 154 bỏ CDP, chỉ còn BiDi]. Bóc bài bằng JS chạy **trong trang**
nhóm (không gọi API FB, không mbasic — mbasic/m.facebook đã chết cho nhóm).

## Module theo tầng (đường quét)
```
ui/posts_window.py   ScanDialog (acc, link nhóm, Số bài, tải media, thư mục)
                     PostsWindow.scan_new(): luồng nền gọi core theo HOP-DONG
ui/ai_lab_tab.py     tab Thử nghiệm AI: cùng chuỗi gọi (launch_debug -> extract_via_bidi)
      │
core/profiles.py     ProfileManager.launch_debug(account, url, port)  — mở Firefox
                     kèm --remote-debugging-port (chỉ 127.0.0.1)
core/fbgroup.py      wait_bidi_ready · extract_via_bidi · posts_from_raw
                     · download_all · read_fb_cookies · group_id_from_url
core/assets/fbgroup_dom.js   bộ quét DOM (nhúng __TARGET__), chạy qua
                     script.evaluate, trả JSON {count, posts[]} | {error}
      │
core/posts.py        Post, PostStore -> data/posts.json (add_many replace_group)
data/post_media/     ảnh/video tải về (hoặc settings.scan_save_dir)
```
Ràng buộc: `core/` không import tkinter; `ui/` không mở websocket/subprocess
trực tiếp mà qua `core.fbgroup` / `manager` (kc/kien_truc.py kiểm).

## Nguyên tắc bền — đã áp dụng đến đâu
- Tách UI/nghiệp vụ: ✔ (ui chỉ gọi 6 hàm trong HOP-DONG.md).
- i18n: ✘ chữ hiển thị hard-code tiếng Việt khắp `ui/` (nợ, ghi DANH-GIA).
- Versioning hợp đồng: HOP-DONG.md v1 (băm sha256 lúc khoi-tao).
- Test tự động: `.congcode2/kc/tatca.ps1` = biên dịch + kiến trúc + quét thật.
- Feature flag: không có; bộ quét DOM là đường duy nhất (ADR-001).
- Chống FB đổi giao diện: bộ quét nhận diện theo `role=feed`, `dir=auto`,
  href mẫu — không theo class; lỗi trả `{error}` có chữ để người dùng đọc.

## Hạ tầng (DevOps)
dev: `py main.py` trong `tool/` · staging: chạy từ mã nguồn bằng kịch bản
`.congcode2/kc/*.py` trên **acc + nhóm thật** · prod: `LVC Manager Profile.exe`
(PyInstaller onefile, `build.py`, phiên `-82` build). Rollback: `git checkout
<tag trước> -- core/fbgroup.py core/assets/fbgroup_dom.js` rồi build lại.
Làm việc chung cây với phiên Claude khác: chỉ commit đúng file mình sửa.

## Bảo mật (soát thiết kế)
Đầu vào ngoài: link nhóm (lọc bằng regex `group_id_from_url`), số bài (int,
chặn trên trong UI). Cổng BiDi 9333 chỉ bind 127.0.0.1. JS bóc bài không nhận
chuỗi từ người dùng ngoài `__TARGET__` (int). Cookie đọc từ profile, không ghi
ra log. Media tải về theo URL do FB trả, lưu trong thư mục người dùng chọn.

## ADR
### ADR-001 — Giữ bộ quét DOM qua BiDi, không phát lại GraphQL (2026-09-05)
Bối cảnh: `fbgroup_graphql.js` phát lại truy vấn feed nhưng phân trang chập
chờn; mbasic chết. Lựa chọn: DOM là nền (đủ bài, ổn), GraphQL chỉ để làm giàu
media khi có. Hệ quả: số bài lấy được phụ thuộc vào **cách cuộn** — đây là
nguyên nhân REQ-001 sprint này.

### ADR-002 — timeout quét theo số bài, JS tự trả kết quả trước hạn (2026-09-05)
Bối cảnh: `extract_via_bidi(timeout=200.0)` cứng; cuộn theo tiến độ để lấy 50
bài nặng có thể quá 200s, và `asyncio.wait_for` hết giờ thì mất trắng. Lựa
chọn: `timeout: float | None = None` → None = max(200, 60 + 4·count); JS nhận
`__BUDGET_MS__` = (timeout − 15)s để tự dừng và trả phần đã gom. Bác: giữ 200s
và cắt count (người dùng nhập 50 phải ra ~50). Hệ quả: người gọi cũ (UI không
truyền timeout) chạy như thường; HOP-DONG.md v1 sửa một dòng, không cần v2.

### ADR-004 — Lý do dừng quét + câu tóm tắt đặt ở core (2026-09-05, IDEA-003)
Bối cảnh: UI báo "Quét xong: 6 bài" khi người dùng nhập 50 → tưởng tool hỏng;
UI không biết vì sao dừng. Lựa chọn: JS trả `stop` ∈ du|het_feed|het_gio|tran,
`LAST_SCAN_INFO` mang theo; câu chữ tóm tắt do `core.fbgroup.tom_tat_quet(info,
count)` sinh — UI chỉ hiện (nguyên tắc UI không chứa nghiệp vụ). Bác: sinh câu
trong `ui/posts_window.py` (tab Thử nghiệm AI sẽ lặp lại logic). Hệ quả: thêm
1 hàm, 1 khoá — không phá vỡ, không cần v2.

---
# Đường "Tạo fanpage" (v1, 2026-09-05 — sprint congcode2 "tạo page theo đợt/vòng")

## Module theo tầng
```
ui/create_page_tab.py  CreatePageTab: acc, tên (nhiều dòng), Số page muốn tạo, Hạng mục
                       (mặc định Blogger), mô tả, ảnh, Cách nhau (phút nghỉ sau vòng),
                       Số luồng (acc mỗi đợt), TXT, bảng kết quả, nhật ký.
                       _run(): luồng nền gọi core.page_batch.chay_theo_dot, nhận su_kien
                       để vẽ bảng/nhật ký/xoá tên. KHÔNG lập lịch, KHÔNG sleep.
      │
core/page_batch.py     chay_theo_dot (đợt/vòng/nghỉ/loại acc/tên) · tao_mot_page
                       (bật pro + create_one + close, dịch exception → loi)
core/fbcreatepage.py   create_one · enable_professional · search_categories ·
                       expand_names · parse_names  (điều khiển trình duyệt qua BiDi)
core/profiles.py       ProfileManager (mở/đóng Firefox theo acc)
      │
data/create_page.json  cấu hình gần nhất của tab · <txt_path> id|link mỗi page
```
Ràng buộc (kc/kien_truc_page.py): `core/page_batch.py` không import tkinter/
websockets; `ui/create_page_tab.py` không chứa bộ lập lịch (MAX_FAIL, wait_delay,
run_all…) và phải gọi `core.page_batch`.

## Hiện trạng trước sprint [BIET]
- HEAD 9dbbe8f: `_run` trong ui/ mỗi luồng ôm 1 acc chạy liên tục hết tên, delay
  tính theo từng acc — sai quy trình người dùng (REQ-001..005).
- Trong phiên (chưa commit): đã viết lại `_run` theo đợt/vòng nhưng **nằm trong
  ui/** (closure run_all/one_page/wait_delay) → vi phạm "UI không chứa nghiệp vụ",
  không đo được nếu không dựng cửa sổ. Sprint 1 chuyển xuống core/page_batch.py.
- Bố cục 9 hàng dọc đòi 870px > minsize 600 → nút Tạo bị che (REQ-006); đã gộp
  còn 5 hàng (chưa commit). Hạng mục mặc định Blogger, ô Số page: đã có trong ui/
  (chưa commit), thước tp06–tp08 chấm lại.

## Nguyên tắc bền — áp dụng đến đâu
- Tách UI/nghiệp vụ: sprint 1 đưa bộ lập lịch xuống core (ADR-005); core phát
  sự kiện có cấu trúc, UI dịch thành chữ.
- i18n: ✘ vẫn nợ (chữ hiển thị trong ui/ và ghi chú lỗi trong core hard-code).
- Versioning hợp đồng: HOP-DONG.md v1 bổ sung mục page_batch (không phá vỡ).
- Test tự động: tp01–tp08 chạy không cần trình duyệt (<10s); tp09 + req001 đo thật.
- Feature flag: không — quy trình đợt/vòng là hành vi người dùng yêu cầu, thay hẳn cũ.

## Bảo mật (soát thiết kế, đường tạo page)
Đầu vào ngoài: tên page (chuỗi, cắt trắng, không đưa vào shell), hạng mục (gõ vào
form FB, khớp gợi ý), số page/số luồng/phút (int, chặn dưới), đường dẫn TXT/ảnh
(người dùng chọn; ghi TXT bằng open() có khoá luồng; mở TXT bằng os.startfile /
subprocess list-args, không shell=True). Cookie đọc từ profile để xác minh danh
sách page — không ghi log. Không secret trong .congcode2/.

## ADR
### ADR-005 — Bộ lập lịch tạo page ở core/page_batch.py, phát sự kiện có cấu trúc (2026-09-05)
Bối cảnh: quy trình đợt/vòng/nghỉ/loại acc/lấy lại tên là nghiệp vụ có nhiều ca
biên (checkpoint giữa đợt, hỏng 3 lần, dừng giữa lúc nghỉ); nằm trong closure của
`ui/create_page_tab.py` thì chỉ chấm được bằng cách dựng cửa sổ và không tái dùng.
Lựa chọn: `core.page_batch.chay_theo_dot(accs, names, tao=..., ngu=..., su_kien=...)`
— nhận hàm tạo, hàm ngủ, hàm phát sự kiện → thước đo tiêm giả lập, chạy <1s; UI
chỉ dịch sự kiện thành chữ/bảng. Bác: (a) giữ trong UI + test bằng cửa sổ (chậm,
gãy khi đổi layout); (b) lớp `BatchRunner` với callback theo tên (nhiều API hơn
cần). Hệ quả: HOP-DONG.md thêm mục page_batch (không phá vỡ); `ui/` mỏng đi ~150
dòng; chữ nhật ký chuyển sang UI (core không có chuỗi hiển thị trừ ghi_chu lỗi
từ fbcreatepage — nợ i18n cũ).

---
# Tab "Thử nghiệm AI" (v1, 2026-09-05 — congcode2 lần 3: quét → xào text → chọn → đăng nhóm)

## Module theo tầng
```
ui/ai_lab_tab.py     AiLabTab: cấu hình AI (provider, key, prompt, mẫu), nút Quét/Thêm tay/
                     Xào lại/Xoá, ô Nhóm + Acc, bảng (☑ chọn · nguồn · trạng thái xào ·
                     caption · ảnh/video · ghi chú · đăng), 3 nút đăng (đã chọn / đã xào / tất cả).
                     Luồng nền chỉ gọi core.ai_lab; UI dịch kết quả thành ô bảng/trạng thái.
      │
core/ai_lab.py       quet_nhom · xao_bai (chỉ text) · chon_bai_dang · media_de_dang · dang_bai
                     · AiLabStore  (ADR-006)
core/ai.py           AiConfig, transform_text (Gemini nhiều key, xoay model), transform_image (không dùng)
core/fbgroup.py      quét + tải media (đường quét, HOP-DONG mục 1)
core/fbbusiness.py   upload_group (agent JS trong trang nhóm; publish=False dừng ở composer)
core/profiles.py     ProfileManager (launch_debug cổng 9337 cho tab này, launch để đăng)
      │
data/ai_lab.json     cfg (có API key) + rows + templates · data/ai_lab_media/ ảnh/video
```
Ràng buộc (kc/kien_truc_ai.py): `core/ai_lab.py` không import tkinter; `ui/ai_lab_tab.py`
không gọi thẳng fbgroup/fbbusiness/ai.transform_* — đi qua core.ai_lab.

## Hiện trạng trước sprint [BIET] (chạy thật 2026-09-05)
- Tab do phiên `-82` viết (b2edfcf): quét → tự xào caption + ẢNH → "Chỉ đăng bài đã xào"
  / "Đăng tất cả". Người dùng chạy thật: 1 bài `xao=loi`, detail = "Tất cả key đều không
  xào ảnh được. HTTP 429 quota" trên `gemini-2.5-flash-image` (cả 7 key) → ảnh là điểm hỏng.
- Xào TEXT bằng Gemini với key thật: OK 12s (key 1: `gemini-2.0-flash` 404 đã gỡ + ~20 model
  giới hạn phút; key 2 xào được). Quét 3 bài qua chuỗi tab (cổng 9337): OK 9s, ảnh tải về.
- Chưa có "chọn bài để đăng" (Treeview selectmode extended nhưng post() không dùng);
  bài lỗi bị lọc nhưng không đánh dấu "bỏ qua"; detail lỗi chỉ xem qua double-click.
- Nghiệp vụ (xào, lọc, đăng) nằm trong ui/ai_lab_tab.py → không đo được nếu không dựng cửa sổ.

## Nguyên tắc bền — áp dụng đến đâu
- Tách UI/nghiệp vụ: sprint 1 đưa xuống core/ai_lab.py (ADR-006).
- i18n: ✘ vẫn nợ. Versioning hợp đồng: HOP-DONG v1 bổ sung mục ai_lab (không phá vỡ).
- Test tự động: al02/al04–al07 không cần mạng (<10s); al01/al02_gemini/al03 đo thật.
- Feature flag: `cfg.do_image` giữ trong AiConfig (tương thích file cũ) nhưng xao_bai không
  dùng — ảnh giữ nguyên theo yêu cầu; bật lại là quyết định ADR sau.

## Bảo mật (soát thiết kế, tab AI)
- API key Gemini nằm trong data/ai_lab.json (plaintext, đã có từ trước) — không commit
  (.gitignore data/?), thước/log chỉ in `...6 ký tự cuối` như core/ai. Thước al02_gemini
  không in key. Đầu vào ngoài: caption từ FB (đưa vào body JSON Gemini — không shell),
  link/id nhóm (parse_group_id), id acc; media là file tải về theo URL fbcdn.
- Đăng nhóm là hành động ra ngoài: thước chỉ chạy publish=False (nạp composer, không bấm
  Đăng). Đăng thật do người dùng bấm.

## ADR
### ADR-006 — Tab AI: chỉ xào text, ảnh/video giữ nguyên; nghiệp vụ ở core/ai_lab.py (2026-09-05)
Bối cảnh: người dùng nói "AI xử lý thay đổi text, ảnh, video thì giữ nguyên"; đo thật
cho thấy xào ảnh Gemini hết quota trên mọi key → toàn bộ bài "xào lỗi" dù text xào được.
Lựa chọn: xao_bai chỉ gọi transform_text; imgs_moi = imgs_goc; không gọi transform_image
(giữ hàm trong core/ai cho tương lai). Toàn bộ quét/xào/chọn/đăng chuyển sang core/ai_lab.py
với Row dict rõ khoá, UI chỉ hiển thị → thước chạy không cần cửa sổ, hàm đăng tiêm được.
Bác: (a) giữ xào ảnh có bật/tắt — người dùng đã nói giữ nguyên, và quota ảnh không có;
(b) sửa tại chỗ trong ui/ — không đo được, lặp lại lỗi kiến trúc của tab tạo page.
Hệ quả: HOP-DONG v1 thêm mục ai_lab (không phá vỡ); Row thêm khoá "chon" (file cũ đọc
được); "Xào ảnh" checkbox bỏ khỏi UI; cột Ghi chú thêm vào bảng.

### ADR-007 — quet_nhom bỏ bài trống (2026-09-05, sprint 1 lần 3)
Bối cảnh: quét thật 3 bài ra 1 mục `Khác` không chữ, không ảnh, không video, không
link (thẻ quảng cáo/gợi ý lọt vào bộ quét DOM). Với tab AI dòng đó không xào, không
đăng được. Lựa chọn: `quet_nhom` lọc bỏ, log "bỏ N bài trống". Bác: giữ dòng để người
dùng tự xoá (rác); sửa fbgroup_dom.js (đường quét đã chốt lần 1, ngoài phạm vi sprint).
Hệ quả: HOP-DONG mục ai_lab thêm 2 dòng, không phá vỡ; `adr --hop-dong` đã ghi hash.

### ADR-008 — media_de_dang chỉ nhận ảnh/video theo đuôi; dang_bai xoá .txt tạm (2026-09-05, sprint 2 lần 3)
Bối cảnh: pentest sprint 1: media_de_dang nhận mọi file tồn tại (kể cả .exe) nếu lọt
vào Row; file `<id>.txt` của bài chỉ chữ tồn lại sau khi đăng. Lựa chọn: lọc bằng
`fbupload.is_image/is_video`; xoá .txt trong `finally`. Bác: đọc header MIME (thêm phụ
thuộc; đuôi đủ vì file do tool tải hoặc người dùng chọn). Hệ quả: HOP-DONG sửa 2 dòng,
không phá vỡ. Cùng sprint: core/ai.py đổi model text mặc định `gemini-2.0-flash` (đã bị
gỡ, 404) → `gemini-flash-latest`, chỉ thử model người dùng chọn khi API còn liệt kê, và
nhớ model vừa xào được theo key trong phiên (IDEA-011) — không đổi hợp đồng.

---
# Lần 4 — tab "Quét bài" mới (ex Thử nghiệm AI) → Auto đăng nhóm (2026-09-06)

## Luồng người dùng (nguyên văn → thiết kế)
"bỏ tab quét bài" → gỡ "🔎 Quét bài nhóm" (PostsTab). "tab thử nghiệm AI đổi tên quét bài" →
"🔎 Quét bài" = AiLabTab. "setup ở tab quét bài mới" → khối cấu hình AI ở đó = data/ai_lab.json
= cấu hình dùng chung mà JobPanel đọc. "kịch bản sau khi quét xong thì gửi vào tab nhóm đăng
bài" → công tắc + chọn job + nút gửi. "gửi vào nhóm đăng bài thì mới chạy xào tự động lấy api
key ở tab quét bài" → tab không xào sau quét; gửi xong → core.xao_hang_doi trên hàng đợi job.

## Module theo tầng
```
ui/app.py             tabs: acc · fanpage · nhóm · 🔎 Quét bài (AiLabTab) · tạo page ; open_posts → Quét bài
ui/ai_lab_tab.py      cấu hình AI · quét · bảng · kịch bản (kich_ban_var, job_menu) · gửi → core
ui/autoup_tab.py      JobPanel: hàng đợi, cột Xào AI, "Tự xào AI", "Xào lại" → core.ai_lab.xao_hang_doi
      │
core/ai_lab.py        quet_nhom · xao_bai · AiLabStore · gui_sang_nhom · xao_hang_doi
core/autoup.py        AutoUploader.add_to_queue / queue / config.queue_dir ; AutoUpManager.by_kind
core/ai.py            AiConfig, load_shared_config (= data/ai_lab.json), transform_text
      │
data/ai_lab.json      cấu hình AI (key) + rows tab Quét bài · data/bai_cho_dang/job-<id>/ file bài + <base>_xao/
```
Ràng buộc (kc/kien_truc_qb.py): ai_lab_tab không add_to_queue/shutil/transform_*/dang_bai;
autoup_tab không transform_*; app không PostsTab; core không import UI.

## Hiện trạng trước sprint [BIET]
- app.py:160-181: 6 tab; PostsTab (posts_window.py 712 dòng) có send_to_autoup ghi file vào
  job.config.queue_dir + add_to_queue, rồi gt.panel._xao_pending() (chỉ xào khi job.auto_xao).
- autoup_tab.py:560-607 JobPanel._xao_queue: load_shared_config() → transform_text + transform_image
  (ảnh) — trái ADR-006; ghi <base>_xao/caption.txt; item xao/xao_detail.
- ai_lab_tab.py (lần 3): tự xào sau quét, cột ☑, 3 nút đăng, dang_bai — sẽ gỡ theo yêu cầu mới.
- Toolbar acc "📰 Bài viết nhóm" → open_posts → tab cũ.

## Nguyên tắc bền
- Tách UI/nghiệp vụ: gửi + xào hàng đợi xuống core (ADR-009). i18n: nợ. Hợp đồng v1 sửa mục
  ai_lab (gỡ 3 hàm chết, thêm 2 hàm) — phá vỡ với ai gọi dang_bai: không còn ai gọi → không cần v2.
- Test: qb03–qb05 không mạng (AutoUpManager thật trên thư mục tạm); qb01/qb02 mở App thật ~3s.
- Feature flag: kich_ban_var (mặc định BẬT) lưu trong ai_lab.json cfg? → lưu vào rows-store
  khoá "kich_ban" (AiLabStore giữ nguyên chữ ký: templates/cfg/rows; kịch bản lưu trong cfg? Không —
  AiConfig là dataclass cố định) → lưu ở data/ai_lab_ui.json? Quyết định: lưu trong file
  ai_lab.json khoá phụ "ui": {"kich_ban": bool, "job": id} — AiLabStore.load/save đọc/ghi thêm
  (chữ ký không đổi: trả thêm qua thuộc tính store.ui).

## Bảo mật
Không đầu vào ngoài mới. File bài được COPY vào queue_dir (thư mục trong data/), tên file từ
base an toàn (regex [^0-9A-Za-z._-] → _). API key vẫn trong data/ai_lab.json (.gitignore).

## ADR
### ADR-009 — Quét bài mới: xào ở hàng đợi Auto đăng nhóm, gửi/xào xuống core/ai_lab (2026-09-06)
Bối cảnh: người dùng đổi luồng: quét → gửi vào job nhóm → xào ở đó (dùng key tab Quét bài) →
đăng theo lịch của job. Tab AI lần 3 tự xào + tự đăng không còn đúng. Lựa chọn: (1) gỡ tab
Quét bài nhóm cũ, giữ ScanDialog; (2) AiLabTab thành "🔎 Quét bài": bỏ tự xào, bỏ ☑/nút đăng,
thêm kịch bản gửi; (3) core.gui_sang_nhom (port send_to_autoup, copy file) + core.xao_hang_doi
(chỉ chữ) dùng chung cho JobPanel — JobPanel bỏ transform_image (ADR-006 áp cho cả hàng đợi);
(4) gỡ chon_bai_dang/media_de_dang/dang_bai + 7 thước của chúng (al03, al04–07, bug002,
idea013, idea015) — tính năng bị người dùng bỏ, giữ thước là giữ code chết. Bác: giữ song song
hai đường đăng (rối, hai nơi xào); giữ xào ảnh ở JobPanel (quota ảnh không có, người dùng đã
chốt giữ ảnh). Hệ quả: HOP-DONG mục ai_lab sửa; posts_window.py chỉ còn ScanDialog + _JobPickDialog
(không xoá file, tránh đụng import của phiên khác); hàng đợi job: bài từ tab Quét bài luôn xao="cho".

---
# Check live UID (v1, 2026-09-06) — nhanh qua HTTP, khong mo trinh duyet

## Module theo tang
```
ui/checklive_tab.py   CheckLiveTab: token, acc lay token, workers, danh sach UID, bang live/die, xuat
      │  (chi goi core.checklive; KHONG mo trinh duyet de check)
core/checklive.py     parse_uids · phan_loai · check_uid · check_batch (song song) · kiem_token · derive_token
      │  HTTP: graph.facebook.com/<uid>?fields=id,name&access_token=...
(khong file du lieu; token khong ghi ra dia)
```
Rang buoc (kc/kien_truc_cl.py): core/checklive khong import tkinter; phan check khong mo
trinh duyet (chi derive_token); ui goi core.checklive.

## Hien trang truoc sprint [BIET] (probe that 2026-09-06)
- Anonymous graph /{uid}/picture KHONG phan biet live/die: moi UID redirect ve cung 1 anh
  mac dinh 1112 byte khi khong token; chi UID sai dinh dang ra 400.
- Token luu trong acc (extra.token, EAA 208 ky tu) DA CHET (code 190 "session invalidated").
- Mint token tu cookie song: HTTP business/adsmanager -> 400; scrape HTML in-page -> 0 token
  (FB moi khong lo EAA token). => derive_token la BEST-EFFORT, chua chac ra.
- => Nguon token chac chan = NGUOI DUNG DAN (app token APPID|SECRET hoac access token) — dung
  nhu timuid.com (co app token rieng). Chon "ca hai" (REQ-004): dan; trong thi tu lay.

## Nguyen tac ben
- Tach UI/nghiep vu: toan bo check o core.checklive, UI chi hien. i18n: no.
- Hop dong v1 bo sung muc checklive (khong pha vo). Test: cl01/cl02/cl04/cl05 fetch tiem gia
  (khong mang, <2s); check that can token that -> bang chung thu cong khi nguoi dung dan token.
- Bao mat: token khong ghi ra dia/log; UID la so; HTTP GET graph, khong shell.

## ADR
### ADR-010 — Check live UID qua graph HTTP + token nguoi dung dan (2026-09-06)
Boi canh: user muon check live nhanh kieu timuid, khong mo trinh duyet. Probe: anonymous
khong phan biet duoc; token luu chet; mint token tu cookie that bai (HTTP 400 / HTML khong lo
token). Lua chon: check bang graph /{uid}?fields=name voi MOT access token con song, chay song
song; token uu tien nguoi dung DAN (chac chan, giong timuid dung app token), thieu thi
derive_token best-effort tu acc da dang nhap. Bac: (a) dung anh dai dien (khong phan biet
duoc); (b) mo trinh duyet tung UID (cham, trai yeu cau); (c) bịa app secret (khong the/khong
duoc). He qua: HOP-DONG them muc checklive; derive_token co the that bai voi FB moi -> ghi ro
la best-effort, nguoi dung dan token la duong chinh.

---
# Dang nhap web id|pass|2fa (v1, 2026-09-06)

## Module theo tang
```
ui/app.py (menu chuot phai)  login_web_selected -> core.fblogin.login_web (lan luot)
core/fblogin.py              driver: ghi lenh, mo Firefox BINH THUONG, poll ket qua, lam moi 2FA, verify
core/assets/fblogin_agent.js process script (content): dien form + 2FA bang su kien nguoi that
core/autoconfig.py           _LOGIN_LOADER_JS nap agent (qlfpwl:*), install chep agent
core/totp.py                 sinh 2FA offline · core/profiles.py verify_cookie_login (qlfp-login.json)
```
Rang buoc (kc/kien_truc_login.py): core/fblogin khong import UI, KHONG launch_debug (dung manager.launch),
file bridge qlfp-weblogin* khac qlfp-login*; ui co login_web_selected.

## Hien trang truoc sprint [BIET] (probe that 2026-09-06)
- Form login: input[name=email] (dien UID), input[name=pass], nut div[role=button] "Log in"; clickReal POST duoc.
- Duoi automation (--remote-debugging-port/BiDi): trang 2FA bi FB chan bang reCAPTCHA enterprise (context rong).
- => Phai dung process-script agent + mo Firefox BINH THUONG (nhu fbcreate_agent.js) de navigator.webdriver=false.
- Ma 2FA sinh offline OK bang core.totp (khong can 2fa.live).

## ADR
### ADR-011 — Dang nhap web bang process-script agent, mo Firefox binh thuong (2026-09-06)
Boi canh: user muon dang nhap id|pass|2fa tu dong hoan toan qua chuot phai. Probe: BiDi dien duoc
form nhung buoc 2FA bi reCAPTCHA chan (do --remote-debugging-port lam navigator.webdriver=true).
Lua chon: nhan ban kien truc fbcreate_agent.js — agent process script trong content process, dien
bang setHandlingUserInput (isTrusted), mo Firefox binh thuong (manager.launch, khong debug port) ->
FB khong chan; cha lam moi ma 2FA (TOTP offline) va verify bang phien that. Bac: (a) BiDi (dinh reCAPTCHA);
(b) nhap 2FA tay (user muon tu dong). He qua: HOP-DONG them muc fblogin; autoconfig them loader qlfpwl
+ chep agent; file rieng qlfp-weblogin* (khong dam qlfp-login* cua probe). Rui ro: FB co the doi DOM 2FA ->
agent dump 2FA DOM ra ket qua de sua selector; nhieu lan dang nhap that co the dinh checkpoint.

---
# Bo sung 2026-09-07 — Tab kich ban nhan tin (Gemini tra loi ban be)

## Kien truc (ADR-012)
- Tach tang: ui/chat_tab.py (chi UI) -> core/fbchat.py (nghiep vu: kich ban + sinh cau tra loi +
  dieu khien phien) -> core/assets/fbchat_agent.js (thao tac DOM messenger trong trang).
- Gemini: TAI DUNG core/ai.py (ApiKeyPool, xoay model, phan loai loi). fbchat.tra_loi() goi
  ai.transform_text() voi caption_prompt = prompt sinh tu KichBan -> khong lap logic goi mang.
- FB messenger qua PROCESS-SCRIPT AGENT (mo Firefox binh thuong nhu fblogin/fbcreate) — KHONG BiDi:
  messenger can su kien tin cay (clickReal/setNative), va BiDi/remote-debug kich chong bot.
- Bridge RIENG: message "qlfpm:*", file <profile>/qlfp-msg.json (lenh) + qlfp-msg-result.json (bao),
  KHAC han qlfp-upload/qlfp-create/qlfp-weblogin -> 4 agent song chung khong dam nhau.
- Kich ban luu data/fbchat.json (khong commit — .gitignore da co data/). API key dung chung ai_lab.json.

## Bao mat (SECURITY)
- Tin nhan ban be la DAU VAO KHONG TIN CAY -> chi dua vao Gemini lam noi dung, khong eval/thuc thi.
- Gui tin la HANH DONG RA NGOAI (toi nguoi that): thuoc that gui chi chay tay tren acc duoc phep,
  KHONG nam trong CI tu dong (giong req001/al01). CI chi kiem logic offline + kien truc.
- API key khong ghi log; khong gui email nguoi dung di dau.

---
# Bo sung 2026-09-08 — Add fanpage vao BM (ADR-013)
- Tang: ui/create_page_tab (o ID BM + goi) -> core/fbbm.py (nghiep vu add + doc ten BM) ->
  core/assets/fbbm_agent.js (thao tac business.facebook.com). Mo Firefox BINH THUONG (khong BiDi):
  business.facebook.com can su kien tin cay (clickReal) va tranh chong bot.
- Bridge RIENG qlfpbm:* / qlfp-bm*.json -> agent thu 5 song chung khong dam 4 agent kia.
- Add page vao BM la HANH DONG THAT (doi acc admin ca BM lan page); thuoc that GATED, CI offline.

---
# Bo sung 2026-09-08 — Auto dang fanpage: doi acc khi loi, bo acc loi 2 lan, checkpoint tung acc (ADR-014)
- Boi canh: mot trang co the co NHIEU acc dang (account_ids, luan phien). Truoc day: acc checkpoint -> tat CA trang;
  hong -> thu lai 3 lan CUNG acc; nhat ky khong ghi acc nao dang.
- Quyet dinh: nghiep vu chon acc/du phong/dem loi nam TRON trong core/autoup.AutoUploader (acc_states, accounts_usable,
  upload_now thu tung acc). UI (ui/autoup_tab) chi hien trang thai + nut mo lai + goi core. Uploader/factory giu
  nguyen chu ky (path, caption) va doc job.pick_account() -> acc dang thu (khong doi HOP-DONG uploader).
- Khoa acc: manager cai job.acc_lock de acc du phong cung duoc khoa (2 trang cung acc khong chay chong nhau);
  acquire co timeout de khong deadlock (A giu acc1 cho acc2, B giu acc2 cho acc1).
- He qua: acc checkpoint chi dung acc do; trang chi dung khi HET acc dung duoc. Trang thai acc luu trong file job
  (khoa acc_states) de tat/mo tool van nho; nguoi dung "Mo lai acc" hoac bat lai job de reset.
- Bao mat: khong doi (khong secret moi; nhat ky chi ghi id acc + ten file).
- Thuoc: kc/ap01-ap06 (offline, uploader gia), kien_truc_ap (core khong tkinter; ui khong dem loi).

---
# Bo sung 2026-09-08 — Luong dung chung tab Quan ly acc (ADR-015)
- Boi canh: co 2 o luong (Luong cookie tren bang; So profile tao cung luc trong Cai dat) + bat chuyen nghiep chay
  tuan tu + dang nhap web kep cung 3. Nguoi dung muon MOT o "Luong" dung chung cho 4 viec.
- Quyet dinh: App._so_luong() la NGUON DUY NHAT cua so luong (settings.login_threads, 1..8). 4 luong dung no.
  enable_professional_selected chuyen tu vong for tuan tu sang ThreadPoolExecutor (moi acc mot profile rieng,
  fbcreatepage.enable_professional da chay song song on trong page_batch). fblogin.MAX_SONG_SONG nang 3 -> 8
  (= max o Luong) — tran an toan van co. Khoa cau hinh giu ten (login_threads) de file cu doc duoc.
- Bo o "So profile tao cung luc" khoi Cai dat (tranh 2 cho dat luong). create_threads giu trong dataclass.
- Thuoc: kc/lc01 (chuyen nghiep theo luong, do song song), lc02 (4 viec cung mot nguon luong), kien_truc_lc.

---
# Bo sung 2026-09-09 — Tim nhieu UID trong hop Chon tai khoan (ADR-016)
- Boi canh: 4 tab (auto fanpage, auto nhom, tao fanpage, nhan tin) deu dung ui/dialogs.AccountPickerDialog; o tim
  chi nhan 1 chuoi con. Nguoi dung co san danh sach UID (copy tu file) muon dan vao mot luc.
- Quyet dinh: logic loc tach ra ham thuan (tach_tu_khoa / loc_acc / uid_khong_thay) trong ui/dialogs.py de thuoc
  offline chay khong can cua so; dialog chi goi ham. Sua MOT cho -> 4 tab cung huong. Khong doi chu ky dialog.
- Thuoc: kc/pk01 (ham thuan), pk02 (dialog: dan nhieu UID -> hien dung dong, chon tat ca chi dong hien, bao khong thay).

---
# Bo sung 2026-09-09 — Tab Doi ten file (ADR-017)
- Tang: ui/rename_tab.RenameTab (chon thu muc, dung chuoi buoc, bang xem truoc) -> core/rename_title (thuan: tung phep
  bien doi + ke hoach + doi ten + hoan tac). Khong mang, khong trinh duyet.
- Quyet dinh: (1) moi phep bien doi la ham thuan tren PHAN TEN de thuoc offline; (2) "xoa cum cung kieu khac so lieu"
  dung MOT vi du -> regex (so -> SO_RE, chu giu, khoang trang co gian) thay vi bat nguoi dung viet regex;
  (3) doi ten qua ten TAM de hoan doi vong khong de nhau + file hoan tac trong thu muc; (4) file cung phan ten khac duoi
  (video + .txt caption cua Auto dang) doi theo nhau, mac dinh bat.
- Bao mat: chi thao tac trong thu muc nguoi dung chon; chan ky tu cam trong ten; khong xoa file, chi doi ten; co hoan tac.
- Thuoc: kc/rn01 (phep bien doi + mau), rn02 (xem truoc/doi ten that trong tmp/hoan tac/trung), rn03 (tab UI qua core),
  kien_truc_rn (core khong tkinter; ui khong os.rename/re).

---
# Bo sung 2026-09-09 — Phien cookie (ADR-018)
- Boi canh (xem .congcode2/NGHIEN-CUU-OUT-COOKIE.md): relogin_cookie xoa SACH cookie profile roi ghi cookie luu (cu);
  FB da xoay xs -> ghi de = tu giet phien -> "out", cookie luu chet han. 5/33 profile dang o tinh trang do.
- Quyet dinh: (1) logic so phien tach ra core/phien.py (thuan, thuoc offline); (2) uu tien PHIEN DANG SONG trong
  profile, cookie luu chi la du phong; (3) vao duoc thi dong bo cookie tuoi ve bang (nguon su that = trinh duyet);
  (4) write_to_profile khong xoa cookie domain khac; (5) bao ly do chet theo probe.why.
- Khong doi: _ensure_login_cookies (chi nap khi profile trong) da dung; login web v1.1 da luu cookie tuoi.
- Bao mat: cookie khong in log/thuoc (chi ten + so sanh); van khong ghi cookie ra ngoai data/.
- Thuoc: kc/ck01 (phien + write_to_profile domain), ck02 (relogin voi manager gia: giu phien / nap / thu lai / bao ly do
  / luu cookie tuoi), kien_truc_ck (bao cao + kien truc).

---
# Bo sung 2026-09-09 — Man dang nhap nho profile (ADR-019)
- Boi canh: FB huy phien nhung nho profile -> www.facebook.com/?stype=lo&flo=1 hien ten + "Tiep tuc" + "Dung trang ca
  nhan khac"; bam Tiep tuc -> chi con o mat khau. Agent login cu chi dien khi co CA email + pass -> ke.
- Quyet dinh: nhan dang kieu man bang ham thuan (qlfpKieuMan) trong fblogin_agent (export node de thuoc); 3 nhanh full /
  pass-only / saved-profile. Dang nhap cookie chet (khong checkpoint) + co mat khau -> tu noi sang login_web (ADR-011),
  dung lai toan bo 2FA/verify/luu cookie tuoi. Thuoc wl01 (node + cau truc), wl02 (App + fblogin gia).

---
# Bo sung 2026-09-09 — Check tuong khong mo browser (ADR-020)
- Boi canh (probe that 2026-09-09): UID tran khong phan biet live/die (acc Live & Die tra ket qua giong het o graph
  picture; www/mbasic an danh 400; token rut tu trinh duyet la client-token vo hieu err190). NHUNG cookie RIENG cua tung
  acc goi mbasic/me thi phan biet duoc: con phien -> /me (Live), bi da ve login -> Die, /checkpoint -> Checkpoint.
- Quyet dinh: Check tuong = HTTP bang cookie tung acc (core/checkwall.py thuan, get() tiem duoc de thuoc chay khong mang),
  song song theo o Luong, KHONG mo Firefox (bo launch_debug/BiDi cho chuc nang nay). Nhanh hon nhieu lan.
- Khong lam duoc: check UID BAT KY khong token (da chung minh vo phuong tren may nay) -> de backlog (can token/app-token
  dan vao nhu dongvanfb). Check tuong chi cho acc CO cookie trong tool.
- Bao mat: cookie khong in log/thuoc; get() qua HTTPS; proxy cua acc dung neu co.
- Thuoc: cw01 (phan_loai thuan + check_nhieu song song, get gia), cw02 (App that thay check_walls, khong launch_debug),
  kien_truc_cw (core khong tkinter; ui khong con launch_debug trong check_walls).

---
# Bo sung 2026-09-09 — Tao page xac minh cookie tuoi (ADR-021)
- Boi canh: nguoi dung phan anh "nhieu cai tao duoc fanpage nhung facebook van bao loi". Nguyen nhan: xac minh page moi
  (_managed_page_ids) chay TRONG LUC Firefox con mo nen phai dung account.cookie CU (cookies.sqlite bi khoa) -> cookie cu
  chua thay page vua tao -> bao "khong tao duoc" oan; batch con tao lai -> trung.
- Quyet dinh: sau khi DONG browser (cookies.sqlite doc duoc), doc cookie TUOI (_cookie_tuoi) roi liet ke lai managed pages;
  van khong ra id ma da bam Tao -> coi la DA TAO (khong loi oan, khong tao trung), note ro de nguoi dung kiem. list_managed_pages
  qua requests business.facebook.com CHAY DUOC tren may nay (da kiem, khac endpoint token bi 400).
- Thuoc: tp12 (4 ca: cookie tuoi ra id / khong ra id van coi da tao / create-blocked / hong truoc bam van loi), tp13 (tao xong
  tu quet BM add), tp14_that (4 acc that, gated).

---
# Bo sung 2026-09-09 — Quet nhieu acc + tu join nhom + xoa link (ADR-022)
- Quet bai nhieu acc: ai_lab.quet_nhieu song song, moi acc CONG BiDi rieng (port_dau+i) tranh dung; UI MultiScanDialog ghep
  acc-link theo hang. Nhanh gap nhieu lan quet tung acc.
- Auto dang nhom tu join: agent runGroup khi khong co o soan -> tim nut "Tham gia nhom" bam truoc; vao cong khai -> dang ngay;
  can duyet -> group-join-pending (fbbusiness bao ro, khong tao trung). Theo yeu cau nguoi dung.
- Xoa link: core.bo_link (thuan, regex) + nut o queue tab dang nhom. Thuoc ql01/ql02/gj01/bl01.

---
# Bo sung 2026-09-10 — Tao BM cho acc chua co BM (ADR-024)
- Tang: ui/create_page_tab._bm_hoac_quet -> core/fbbm.tao_bm -> agent taoBM (business.facebook.com). Ten BM = ten acc FB
  (agent doc CurrentUserInitialData/aria-label), Email = recovery_mail, Ten/Ho tach tu ten.
- Luong (theo anh nguoi dung): dong tooltip onboarding -> switcher goc tren-trai -> "Tạo trang quản lý tài sản doanh nghiệp"
  -> dialog dien theo thu tu o -> Tạo. Step-machine nhe (1 thao tac/~2-3s) tranh crash tab business.
- LIVE CHUA XAC NHAN END-TO-END: da chay that acc <acc test> — agent doc dung ten "Hoàng Khánh Vy", dong duoc tooltip;
  DOM business thay doi (luc tooltip luc dialog) + tab business de bat on khi chay lien tuc. DUNG hammer acc (risk checkpoint).
  Can 1 lan chay sach tren acc on dinh de chot selector switcher->menu->dialog. Offline mb01/mb02 xanh.

---
# Bo sung 2026-09-10 — Tu dang nhap lai khi logout (ADR-025)
- Boi canh: acc bi logout giua luc tao fanpage / dang fanpage / dang nhom -> viec that bai (LOI_KHOA / BusinessError).
  Nguoi dung muon: logout -> tu dang nhap COOKIE; cookie khong duoc -> WEB (id|pass|2fa); roi lam tiep.
- Quyet dinh: core/reauth (thuan) tap trung logic; chay_lai_neu_logout boc TUNG viec o tang caller (page_batch,
  ui/app) — bat loi co "ĐĂNG XUẤT" (fbcreatepage/fbbusiness deu bao chuoi nay) roi dang nhap lai + chay lai 1 lan.
  Khong sua ruot cac ham viec lon. Dung lai fblogin.login_web + cookie_module + verify_cookie_login san co.
- Thuoc ra01 (core: cookie->web, chay lai), ra02 (tao fanpage), ra03 (dang fanpage+nhom qua App).

---
# Bo sung 2026-09-15 — Acc tao page loi nghi 3 ngay (ADR-027)
- Boi canh: tao page TU BM, 1 acc loi (agent khong bam duoc nut) lam ca dot loay hoay; nguoi dung muon acc loi bi
  loai khoi list chay, bao ro "dung 3 ngay roi tao lai cho an toan", acc khac van chay, co nut reset, het 3 ngay tu chay.
- Quyet dinh: core/acc_nghi (thuan, dict trang thai + thoi han) — UI chi dich: loc truoc khi chay, danh dau khi
  LOI_HONG (BM) / loai_acc, cot Trang thai, nut Reset, tick 60s. Luu cung create_page.json (khong them file).
  Het han = "cho" theo thoi gian (khong can tien trinh nen) -> tu dong chay lai o lan chay/vong ke tiep.
- He qua: che do BM: 1 lan hong = loai ngay (khac che do acc: hong 2 lan/vong, 3 vong moi loai — ADR-023).
- Thuoc pb06 (core), pb07 (UI).
- Bo sung 2026-09-15 (ADR-027b): hop FB "Không thể tạo Trang" (trung ten page da quan ly...) = LOI tao -> acc nghi 3 ngay
  (truoc: agent doi 30s roi 'create-blocked' -> core coi 'rat co the DA TAO' -> sai). Tao XONG -> acc cho delay "Cách nhau"
  (TT_CHO_DELAY) toi lan tiep: thanh cong hay loi deu qua delay, ca khi dung/mo lai tool. Thuoc pb08 + pb06/pb07 mo rong.

---
# Kiến trúc MÔ-ĐUN (ADR-028, 2026-09-15) — mỗi chức năng là một mô-đun riêng, tool điều khiển theo mã

## Vì sao
`ui/app.py` (3.2k dòng) ôm cả nghiệp vụ: đăng nhập cookie ~100 dòng logic nằm trong `work()` của UI;
mỗi lệnh chuột phải là một hàm riêng với luồng nền, khoá, thông báo lặp lại. Thêm/sửa chức năng phải
sửa UI; không tái dùng được từ tab khác; khó kiểm thử. Người dùng yêu cầu: **tất cả chức năng là mô-đun
riêng lẻ, tool gọi đúng mô-đun khi bấm lệnh** (đăng nhập cookie, đăng nhập web, thêm proxy, tạo profile,
tạo fanpage bằng acc, tạo fanpage bằng BM, đăng bài fanpage tự động...).

## Bố cục
```
core/modun/__init__.py   registry: dang_ky · lay · danh_sach · chay  +  Modun · NguCanh · KetQua (base)
core/modun/<ma>.py       MỘT mô-đun = MỘT file, tự đăng ký khi import (dang_ky(Modun(ma=..., chay=...)))
                         chỉ gọi core/* hiện có (fblogin, profiles, checkwall, page_batch, autoup...);
                         KHÔNG import tkinter/customtkinter/ui.
core/modun/tat_ca.py     import mọi mô-đun (nạp registry một lần khi App khởi động)
ui/app.py                App.goi_modun(ma, accs, **tham_so): dựng NguCanh, chạy ở luồng nền qua _run_async
                         (khoá per-acc), dịch KetQua -> status/hộp thoại. Lệnh menu = 1 dòng goi_modun(...).
```
Nhóm mô-đun (`Modun.nhom`): `acc` (đăng nhập cookie/web, tạo profile, mở/đóng, bật chuyên nghiệp, đổi UA,
check tường/cookie) · `proxy` (thêm/đổi proxy, check proxy, khớp múi giờ) · `fanpage` (tạo fanpage bằng acc,
tạo fanpage bằng BM, add page vào BM, tạo BM) · `dang_bai` (đăng fanpage tự động, đăng nhóm, quét bài,
nhắn tin AI) · `khac` (đổi tên file, extension, cache).

## Nguyên tắc
- Mô-đun **thuần nghiệp vụ**: nhận `NguCanh` (manager/store/settings/log/post/so_luong) + `accs` + `tham_so`,
  trả `KetQua` (ok/loi/ghi_chu/du_lieu). Không mở hộp thoại; báo qua `log` và KetQua.
- Registry là nguồn duy nhất: menu/phím tắt/tab sinh từ `danh_sach(nhom)`; thêm mô-đun mới = thêm 1 file
  + 1 dòng import trong `tat_ca.py`, KHÔNG sửa App.
- Chuyển dần (strangler): giữ tên hàm App cũ (`relogin_cookie`, `login_web_selected`...) để thước cũ xanh,
  thân hàm rút về `goi_modun`. Mỗi sprint chuyển 2–5 mô-đun, `tatca.ps1` xanh mới sang sprint sau.
- Cổng kiến trúc `kc/kien_truc_modun.py`: (1) core/modun/* không import tkinter/ui; (2) mỗi file mô-đun
  gọi `dang_ky`; (3) App có `goi_modun`; (4) các lệnh đã chuyển không còn nghiệp vụ dài trong UI.

## Lộ trình 10 sprint (trần, dừng sớm nếu xong)
1 registry + base + 3 mô-đun (đăng nhập web, tạo profile, check tường) + App.goi_modun ·
2 đăng nhập cookie (kéo 100 dòng ra khỏi UI), bật chuyên nghiệp, đổi UA, mở/đóng profile ·
3 proxy: thêm/đổi, check, khớp múi giờ · 4 fanpage: tạo bằng acc, tạo bằng BM, add page BM, tạo BM ·
5 đăng bài: fanpage tự động, nhóm (wrap AutoUploader job start/stop) · 6 quét bài, nhắn tin AI, đổi tên ·
7 UI sinh từ registry (menu "Mô-đun" theo nhóm) · 8 dọn App (xoá nghiệp vụ trùng), i18n nhãn mô-đun ·
9–10 dự phòng: backlog, tài liệu, đánh giá lớn.

---
# Bo sung 2026-09-26 — Xoa bai viet fanpage (ADR-029)
- Boi canh: nguoi dung can tab xoa bai fanpage theo khoang ngay + the loai. Khao sat repo 2025-2026: chi co
  Graph API (token) hoac console script trang ca nhan; khong repo nao xoa page qua Business Suite. Duong cookie +
  API noi bo bi loai (khong tai lieu, de vo, nguy co checkpoint, va da bi chan). Nguoi dung chot Graph API chinh thuc.
- Quyet dinh: core/fbxoabai thuan (requests tiem duoc) + mo-dun xoa_bai (registry, can_profile=False, khong mo
  Firefox) + tab XoaBaiTab. Quet truoc (dem) tach khoi Xoa that (xac nhan). Han muc theo header + ma loi, moi bai 1 goi.
- He qua: can token page/user (pages_manage_posts, pages_read_engagement) do nguoi dung dan; token luu data/ (gitignore),
  che khi hien. Khong xoa duoc anh dai dien/anh bia/story highlight (API tu choi -> ghi loi, di tiep).
- Thuoc xb01 (core + mo-dun, Graph gia), xb02 (UI). Live: kc/xb_that.py can token that (gated).
