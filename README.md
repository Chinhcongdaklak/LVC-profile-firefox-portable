# LVC Manager Profile

Tool desktop quản lý nhiều acc trên Firefox Portable: mỗi acc một profile riêng biệt,
mỗi profile một proxy và múi giờ riêng, mở đúng profile bằng một cú đúp chuột.

## Chạy tool

```bat
pip install -r requirements.txt
run.bat
```

Hoặc `py main.py`. Đóng gói thành một file `.exe` duy nhất: chạy `build.bat`.

## Bố cục thư mục

Tool đặt mỗi acc vào một thư mục con **đặt tên theo ID acc**:

```
tool\                                        <- tool này (hoặc file .exe đã đóng gói)
├─ FirefoxPortable_154.0.1_English.paf.exe   <- installer gốc
├─ logo.png                                  <- logo nguồn, sinh ra assets\logo.ico
├─ dataccounts.json                        <- danh sách acc (không đưa lên git)
└─ profile\                                  <- "Thư mục chứa profile" (đổi được)
    └─ 100000000000001\                      <- một acc = một thư mục, tên theo ID acc
        └─ FirefoxPortable            ├─ FirefoxPortable.exe            <- tool mở đúng file này cho acc này
            ├─ FirefoxPortable.ini            <- tool ghi, bật mở nhiều acc cùng lúc
            ├─ App\Firefox64            │   ├─ mozilla.cfg                <- tool khoá proxy + ngôn ngữ
            │   └─ tz_shim.js / tz_patch.js   <- lớp vá múi giờ
            └─ Data\profile\cookies.sqlite    <- nơi tool nạp cookie
```

## Tạo profile

Bấm **🧩 Tạo profile**. Với mỗi acc được chọn, tool sẽ:

1. Tạo thư mục theo ID acc.
2. Chép `FirefoxPortable_*.paf.exe` vào thư mục đó.
3. Chạy installer và **tự bấm Next / Install / Finish** — cửa sổ được đẩy ra ngoài
   màn hình nên không làm phiền. Mất khoảng **25 giây/acc**.
4. Ghi `FirefoxPortable.ini` với `AllowMultipleInstances=true` để mở song song nhiều acc.
5. Chạy Firefox ẩn một lần để profile sinh đủ file (bắt buộc trước khi nạp cookie).
6. Nạp sẵn cookie đã lưu của acc (nếu có).
7. **Xoá bản sao installer** trong thư mục acc — tiết kiệm ~181 MB mỗi acc. Chỉ xoá khi
   profile đã cài xong; nếu cài lỗi thì file được giữ lại để cài lại.

> Installer bản này **không hỗ trợ `/SILENT`** nên bắt buộc phải điều khiển wizard
> bằng Win32 API. Nếu muốn nhanh hơn: vào **Cài đặt**, trỏ *Thư mục FirefoxPortable mẫu*
> tới một thư mục đã giải nén rồi bật *Nhân bản từ thư mục mẫu* — chỉ mất vài giây/acc.

Tool tạo nhiều profile cùng lúc — **Cài đặt → Số luồng tạo profile**, mặc định **3**
(chọn được 1–8). Đã đo: hai installer `paf.exe` chạy song song không đâm nhau, 2 profile
mất 28 giây thay vì ~50 giây khi làm lần lượt. Acc nào lỗi thì không làm hỏng cả mẻ —
chạy hết rồi báo gộp danh sách lỗi ở cuối.

Nếu thư mục trùng tên với ID acc đã có sẵn Firefox, tool **dùng luôn thư mục đó** thay vì
cài lại, giữ nguyên cookie và đăng nhập bên trong. Nhận được cả các bố cục lệch chuẩn hay
gặp khi tự chép thư mục vào (`FirefoxPortable.exe` nằm thẳng trong thư mục acc, hoặc thư
mục bị đổi tên) và tự dọn về đúng chuẩn.

Với các thư mục tạo từ trước còn sót `*.paf.exe`: chọn acc → chuột phải →
**🧹 Xoá file cài đặt thừa**. Tool cho biết sẽ giải phóng bao nhiêu MB trước khi xoá.

## Proxy

Ô proxy nhận nhiều định dạng:

```
1.2.3.4:8080
1.2.3.4:8080:user:pass
user:pass@1.2.3.4:8080
socks5://user:pass@1.2.3.4:1080
```

Proxy được **khoá cứng vào thư mục app của Firefox** bằng AutoConfig (`mozilla.cfg`),
không phải qua relay — nhờ vậy mở profile lúc tool đang tắt vẫn ăn proxy.

Firefox không cho nhúng `user:pass` vào pref proxy, nên `mozilla.cfg` nạp sẵn user/pass
vào Password Manager dưới dạng `moz-proxy://host:port` kèm đúng `realm` mà proxy khai báo
(tool tự hỏi proxy để lấy realm — sai realm là Firefox vẫn hiện hộp thoại đòi mật khẩu).

Pref được `lockPref` nên không tắt nhầm được, và `network.proxy.failover_direct=false`
để proxy chết thì **không** âm thầm rơi về mạng thật. WebRTC bị tắt, DNS do proxy phân
giải, nên không rò rỉ IP gốc.

> Không dùng addon vì bản Firefox Portable là kênh `mozilla-release`, bắt buộc addon phải
> được Mozilla ký số — addon tự viết không cài được. AutoConfig là đường duy nhất.

### Đổi proxy

Chuột phải vào dòng acc → **🌐 Đổi proxy...** Hộp thoại có sẵn proxy hiện tại, nút
**Kiểm tra** đi thật ra Internet và trả về IP thoát cùng độ trễ trước khi bạn lưu.

Bấm Lưu thì:

| Tình huống | Kết quả |
|---|---|
| Trình duyệt đang mở | Firefox chỉ đọc cấu hình proxy lúc khởi động, nên tool hỏi có mở lại không — đồng ý là xong |
| Trình duyệt đang đóng | Lưu lại, áp dụng ở lần mở sau |

Bỏ trống ô proxy rồi Lưu để gỡ proxy.

Chọn nhiều dòng rồi bấm **🌐 Proxy hàng loạt** (hoặc chuột phải → Đổi proxy) để gán cho
cả loạt: dán một dòng thì tất cả dùng chung, dán nhiều dòng thì gán lần lượt theo thứ tự
acc trong bảng.

## Múi giờ & ngôn ngữ theo IP proxy

IP ở Đức mà trình duyệt báo giờ Việt Nam là dấu hiệu bị soi rõ nhất. Chuột phải →
**🌍 Khớp múi giờ + ngôn ngữ theo proxy**: tool đi ra Internet *qua chính proxy đó*,
lấy về quốc gia và múi giờ thật, rồi đặt cho profile khớp theo.

Chạy tự động khi đổi proxy (bỏ tick trong hộp thoại sửa acc nếu không muốn) và khi
tạo profile mới. Chuột phải → **🌍 Bỏ khớp múi giờ** để trả về mặc định của máy.

### Ngôn ngữ

Đặt `intl.accept_languages` (khoá cứng trong `mozilla.cfg`). Pref này đổi cả header
`Accept-Language` lẫn `navigator.language` / `navigator.languages` — đã đo trên
Firefox 154 — nên không cần cài gói ngôn ngữ nào.

### Múi giờ

Firefox trên Windows **chỉ nhận biến `TZ` với đúng 5 giá trị**: `UTC`, `EST5EDT`,
`CST6CDT`, `MST7MDT`, `PST8PDT` (danh sách trắng cứng trong mã nguồn Firefox — đã
kiểm chứng bằng cách thử 40 giá trị khác nhau, kể cả `Asia/Tokyo` và `CET`, đều bị
bỏ qua). Vì vậy cách đó chỉ phục vụ được proxy Mỹ.

Tool dùng cách khác: AutoConfig nạp một *process script* vào mọi tiến trình nội dung,
script này bơm `tz_patch.js` vào từng trang **trước khi script của trang chạy**, ghi đè:

* `Date.prototype.getTimezoneOffset` và toàn bộ hàm đọc/đặt giờ địa phương
* Hàm dựng `Date` từ thành phần giờ địa phương, `Date.parse`
* `toString` / `toDateString` / `toTimeString` / `toLocale*String`
* `Intl.DateTimeFormat` (mặc định dùng múi giờ đích)
* `Temporal.Now.*` (Firefox 154 đã bật Temporal)

Giờ của vùng đích được tính bằng **chính ICU của trình duyệt** (`Intl.DateTimeFormat`
với `timeZone` chỉ định), nên DST tự đúng mà không cần nhúng bảng dữ liệu múi giờ nào.
`Function.prototype.toString` được che để các hàm đã vá vẫn báo `[native code]`.

Hai file `tz_shim.js` và `tz_patch.js` nằm cạnh `firefox.exe`, tự xoá khi bỏ khớp.

> Định vị (`navigator.geolocation`) **không** bị đụng tới: đo thực tế cho thấy Firefox
> không hề gọi tới `geo.provider.network.url`, nên giả lập ở đó là vô nghĩa.


## Giao diện & icon

**Cài đặt → Giao diện**: Sáng hoặc Tối, mặc định **Sáng**. Đổi xong bấm Lưu là ăn ngay,
không cần khởi động lại.

Icon lấy từ `logo.png` đặt trong thư mục `tool`. Chạy lại lệnh dưới đây mỗi khi đổi logo:

```py
from PIL import Image
src = Image.open("logo.png").convert("RGBA")
src.save("assets/logo.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
src.resize((128, 128), Image.LANCZOS).save("assets/logo.png")
src.resize((256, 256), Image.LANCZOS).save("assets/logo_256.png")
```

`assets/logo.ico` dùng cho icon cửa sổ và icon của file `.exe`; `assets/logo.png` hiện
cạnh tiêu đề trong tool. Đổi logo xong nhớ chạy lại `build.bat` để bản `.exe` cập nhật theo.


## Cookie

Ô cookie nhận:

* JSON xuất từ Cookie-Editor / EditThisCookie
* File `cookies.txt` định dạng Netscape
* Chuỗi ngắn `c_user=...; xs=...` (khai báo thêm *Domain mặc định*)

Cookie được ghi thẳng vào `cookies.sqlite` của profile, giữ nguyên `httpOnly`, `secure`,
`sameSite` và hạn dùng. Profile phải đang **đóng** khi nạp — tool sẽ hỏi để đóng giúp.
Chuột phải → *Xuất cookie từ profile* để lấy ngược cookie hiện tại ra file JSON.

## 2FA

Nhập secret Base32 hoặc dán nguyên `otpauth://...`. Tool tự sinh mã TOTP; nút **🔑 Mã 2FA**
chép mã hiện tại vào clipboard. Ô nhập 2FA hiển thị mã kèm số giây còn lại.

## Nhập hàng loạt

Mỗi dòng một acc:

```
id | mật_khẩu | mail_khôi_phục | 2fa | proxy | nhóm
```

Các trường phía sau có thể bỏ trống. Dấu phân cách chọn được (`|`, `,`, `;`, Tab).

## Phím tắt & thao tác

| Thao tác | Kết quả |
|---|---|
| Đúp chuột vào dòng | Mở profile |
| Chuột phải | Đổi proxy, test proxy, khớp múi giờ, chép ID / mật khẩu / mail / 2FA / cookie, mở thư mục, dọn file cài đặt, xuất cookie |
| Chọn nhiều dòng (Ctrl/Shift) | Mọi nút đều chạy hàng loạt |
| Bấm tiêu đề cột | Sắp xếp |

Dòng nền xanh = profile đang chạy. Dòng chữ xám = chưa tạo profile.

## Dữ liệu lưu ở đâu

`tool\data\accounts.json` và `tool\data\settings.json`. **File acc chứa mật khẩu và cookie
dạng thô** — `.gitignore` đã loại thư mục `data/` khỏi git; nhớ tự sao lưu chỗ an toàn.
