# Hướng dẫn phát hành bản mới — LVC Manager Profile

Viết cho **người phát hành**. Người dùng cuối không cần đọc file này.

Bản phát hành nằm ở **Releases** của kho https://github.com/Chinhcongdaklak/congprofile
(kho mã nguồn là `LVC-profile-firefox-portable`, còn file `.exe` chỉ nằm ở kho phát hành này).

---

## Chuẩn bị MỘT LẦN

**Cách A — token RIÊNG cho kho này (khuyên dùng):**

1. Mở https://github.com/settings/personal-access-tokens/new (tài khoản `Chinhcongdaklak`).
2. **Token name**: `phat hanh congprofile` · **Expiration**: chọn thời hạn dài nhất bạn chấp nhận
   (hết hạn thì tạo lại, dán đè file).
3. **Repository access** → **Only select repositories** → chọn **`congprofile`**.
4. **Permissions → Repository permissions → Contents** → **Read and write**
   (Metadata tự bật Read-only). Không cần quyền nào khác.
5. **Generate token**, chép chuỗi `github_pat_...` (chỉ hiện một lần).

**Cách B — dùng chung một token cho mọi tool:** https://github.com/settings/tokens →
**Generate new token (classic)** → tích **`repo`**. Token này đẩy được lên **mọi kho** của tài
khoản, nên token của Video Slide (`video slide\setup\github_token.txt`) dùng được luôn.

Cuối cùng: dán chuỗi token vào file **`setup\github_token.txt`** trong thư mục tool.

> Token là **mật khẩu của kho phát hành**: ai có nó thì đẩy được `.exe` giả lên, và mọi người
> bấm cập nhật sẽ tải đúng bản giả đó. Thư mục `setup\` đã nằm trong `.gitignore`. Đừng gửi token
> qua chat/Zalo/email. Lộ thì vào trang tokens bấm **Delete** rồi tạo cái mới.
> Token của tool Video Slide (cùng tài khoản, quyền `repo`) dùng được cho kho này.

---

## Mỗi lần phát hành

Bấm đôi **`phat_hanh.bat`** (hoặc nút **🚀 Phát hành** trên tool khi chạy từ mã nguồn). Cửa sổ hiện:

- **Bản trong tool** và **các bản đã có trên GitHub**.
- **Phiên bản phát hành** — chọn một gợi ý hoặc tự gõ:
  - `1.0.1 (sửa lỗi)` · `1.1.0 (thêm tính năng)` · `2.0.0 (thay đổi lớn)`
  - lần đầu còn có `1.0.0 (giữ số hiện tại, chưa phát hành)`.
  Số **trùng** bản đã có hoặc **không lớn hơn** bản mới nhất sẽ bị chặn (máy người dùng sẽ không coi là bản mới).
- **Có gì mới** — hiện cho người dùng khi tool báo cập nhật.
- **Đóng gói + đẩy lại bộ cập nhật** — chỉ cần lần đầu hoặc khi sửa chính `capnhat.py`.

Bấm **🚀 Phát hành** → tool tự làm theo thứ tự:

1. ghi số bản vào `core\phien_ban.py` (trước khi đóng gói → `.exe` mang đúng số bản)
2. `python build.py` → `dist\LVC Manager Profile.exe`
3. `python build_capnhat.py` → `dist\LVCProfileUpdate.exe` (khi tích)
4. `python phat_hanh.py --ban X` → đẩy lên Releases kèm `capnhat.json` (mã kiểm tra sha256)

Bước nào hỏng thì dừng, **chưa đẩy gì lên**, số bản trong code trả về như cũ.

Dòng lệnh (khi muốn kiểm từng bước): `python phat_hanh.py --thu` (xem trước, không đẩy).

---

## Máy người dùng nhận bản mới thế nào

1. **Tool tự báo**: mở tool, vài giây sau góc trên bên phải hiện nút vàng
   **🎉 Có bản mới X — Cập nhật** → bấm → tool đóng lại → `LVCProfileUpdate.exe` tải, kiểm sha256,
   thay file → bấm **Mở tool**. Không có bản mới / mất mạng thì không thấy gì.
2. **Bấm tay `LVCProfileUpdate.exe`** cạnh tool — dùng khi tool đang hỏng không mở được.

Lần đầu gửi tool cho người mới: gửi `LVC Manager Profile.exe` **và** `LVCProfileUpdate.exe`,
cùng các thư mục `data\`, `profile\`, `extension\` (các thư mục này KHÔNG nằm trong `.exe`
và KHÔNG được cập nhật tự động).

---

## Quy tắc số bản `X.Y.Z`

X đổi lớn · Y thêm tính năng · Z sửa lỗi. **Số mới phải lớn hơn số cũ**. So theo từng số:
`1.10.0` mới hơn `1.9.0`.

## Khi có trục trặc

| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| `Chưa có mã truy cập GitHub` | thiếu `setup\github_token.txt` |
| `401` / `403` khi đẩy | token sai, hết hạn, hoặc thiếu quyền `repo` |
| Người dùng không thấy nút báo bản mới | số bản mới không lớn hơn bản họ đang dùng |
| Cập nhật báo *"đang chạy"* | tool chưa đóng hẳn — đóng rồi bấm lại |
| *"không khớp mã kiểm tra"* | mạng đứt giữa chừng; bản cũ vẫn nguyên, thử lại |
