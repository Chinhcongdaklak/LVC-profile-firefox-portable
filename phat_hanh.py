# -*- coding: utf-8 -*-
"""
phat_hanh.py — ĐẨY MỘT BẢN MỚI CỦA LVC MANAGER PROFILE LÊN GITHUB (kho congprofile)
(chép từ tool Video Slide; cửa sổ chọn phiên bản: phat_hanh_gui.py / phat_hanh.bat)
══════════════════════════════════════════════════════════════════════════════
Chạy ở MÁY CỦA BẠN (người phát hành), không phát cho người dùng.

    python phat_hanh.py                 # phát hành bản trong core/phien_ban.py
    python phat_hanh.py --ghi-chu "Sửa lỗi cookie"
    python phat_hanh.py --ban 5.2.0     # đặt số bản khác, ghi lại vào phien_ban.py
    python phat_hanh.py --thu           # chỉ xem sẽ làm gì, KHÔNG đẩy lên

VÌ SAO ĐẨY VÀO **RELEASE** CHỨ KHÔNG COMMIT FILE VÀO REPO:
Mỗi bản ~51 MB; nhét .exe vào repo thì repo phình mãi (GitHub chặn file > 100 MB).
Tệp đính kèm Release cho tới 2 GB và có sẵn API "bản mới nhất".

MÃ TRUY CẬP (token) LẤY Ở ĐÂU — và KHÔNG BAO GIỜ nằm trong mã nguồn:
  · biến môi trường `GITHUB_TOKEN`, hoặc
  · file `setup/github_token.txt` (đã nằm trong .gitignore).
Tạo tại  https://github.com/settings/tokens  → "Generate new token (classic)" →
tích quyền **repo**. Token là mật khẩu: lộ ra là người khác đẩy được bản giả
lên kho của bạn, và mọi người dùng sẽ tải đúng bản giả đó. Script này KHÔNG in
token ra màn hình và KHÔNG ghi nó vào đâu.
══════════════════════════════════════════════════════════════════════════════
"""

import hashlib
import io
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

GOC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, GOC)

from core.phien_ban import (KHO_GITHUB, PHIEN_BAN, TEN_EXE, TEN_MO_TA,
                            TEN_FILE_PHIEN_BAN, TEN_TEP_PHAT_HANH, TEN_UPDATER)
import urllib.parse

API = "https://api.github.com"
TEP_TOKEN = os.path.join(GOC, "setup", "github_token.txt")


def doc_token():
    """Token từ biến môi trường hoặc file. Trả "" nếu không có."""
    t = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if t:
        return t
    try:
        with io.open(TEP_TOKEN, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _goi(url, token, data=None, method=None, kieu="application/json",
         doc_json=True):
    """Gọi API GitHub. Lỗi thì NÓI RA GitHub bảo gì, không chỉ trả con số.

    Vì sao phải đọc phần thân lỗi: GitHub trả 422 cho mọi thứ nó không chịu, và
    lý do thật nằm trong JSON kèm theo. Lần đầu chạy thật, script chỉ in được
    "HTTP Error 422: Unprocessable Entity" — đúng nhưng vô dụng; lý do thật là
    "Repository is empty", và biết câu đó thì sửa mất 10 giây. Một thông báo lỗi
    không nói được phải làm gì thì cũng gần như không có thông báo."""
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer %s" % token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "LVCProfilePublish")
    if data is not None:
        req.add_header("Content-Type", kieu)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        than = ""
        try:
            than = e.read().decode("utf-8", "replace")
            d = json.loads(than)
            cau = str(d.get("message") or "")
            for x in (d.get("errors") or []):
                m = x.get("message") or x.get("code") or ""
                if m:
                    cau += " — %s" % m
            than = cau or than
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError("GitHub trả lỗi %s: %s" % (e.code, than or e.reason))
    return json.loads(raw.decode("utf-8")) if doc_json and raw else None


def repo_trong(token):
    """Kho chưa có commit nào? GitHub trả 409 'Git Repository is empty.'"""
    try:
        _goi("%s/repos/%s/commits?per_page=1" % (API, KHO_GITHUB), token)
        return False
    except RuntimeError as e:
        return "empty" in str(e).lower()


def tao_commit_dau(token):
    """Tạo commit đầu tiên (một README) để kho có chỗ cho thẻ tag bám vào.

    KHÔNG tạo được bản phát hành trên kho rỗng: thẻ tag phải trỏ vào một commit.
    Đây là việc làm ĐÚNG MỘT LẦN cho kho mới, nên làm hộ luôn thay vì bắt người
    dùng đi mò — nhưng chỉ tạo README, không đụng gì khác."""
    import base64
    noi_dung = (
        "# Kho phát hành LVC Manager Profile\n\n"
        "Kho này chỉ dùng để **phát hành bản mới**. Mã nguồn không nằm ở đây.\n\n"
        "## Người dùng tải bản mới thế nào\n\n"
        "1. Mở tool lên — nếu có bản mới, góc trên bên phải hiện nút vàng\n"
        "   **🎉 Có bản mới … — Cập nhật**. Bấm vào là xong.\n"
        "2. Hoặc bấm `LVCProfileUpdate.exe` nằm cạnh tool.\n"
        "3. Hoặc tải tay tại **[Releases](../../releases/latest)**.\n\n"
        "## Vì sao file .exe nằm trong Releases chứ không nằm trong kho\n\n"
        "Mỗi bản `LVC Manager Profile.exe` ~51 MB; giữ trong Releases để kho mã không\n"
        "phình ra. Tệp đính kèm trong Releases cho tới 2 GB.\n")
    return _goi(
        "%s/repos/%s/contents/README.md" % (API, KHO_GITHUB), token,
        method="PUT",
        data=json.dumps({
            "message": "Khoi tao kho phat hanh",
            "content": base64.b64encode(noi_dung.encode("utf-8")).decode("ascii"),
        }).encode("utf-8"))


def cac_ban_da_phat_hanh(token=""):
    """[(tag, ngay, du)] cac ban da co tren kho, moi nhat truoc. Khong co mang -> [].

    ``du`` = ban co tep .exe dinh kem. Ban KHONG co (tao release roi day tep hong giua chung,
    nhu lan dau 29/09) la ban DANG DO: duoc phat hanh lai dung so do."""
    try:
        if token:
            ds = _goi("%s/repos/%s/releases?per_page=30" % (API, KHO_GITHUB), token)
        else:
            req = urllib.request.Request("%s/repos/%s/releases?per_page=30" % (API, KHO_GITHUB),
                                         headers={"User-Agent": "LVCProfilePublish",
                                                  "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                ds = json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return []
    ten_exe = {TEN_TEP_PHAT_HANH, TEN_EXE}
    return [(str(d.get("tag_name") or ""), str(d.get("published_at") or "")[:10],
             any(a.get("name") in ten_exe for a in (d.get("assets") or [])))
            for d in (ds or []) if d.get("tag_name")]


def sha256(duong):
    h = hashlib.sha256()
    with open(duong, "rb") as f:
        for khoi in iter(lambda: f.read(1024 * 256), b""):
            h.update(khoi)
    return h.hexdigest()


def dat_phien_ban(ban):
    """Ghi số bản mới vào `core/phien_ban.py` — MỘT nguồn duy nhất."""
    p = os.path.join(GOC, "core", "phien_ban.py")
    s = io.open(p, encoding="utf-8").read()
    cu = 'PHIEN_BAN = "%s"' % PHIEN_BAN
    moi = 'PHIEN_BAN = "%s"' % ban
    if cu not in s:
        raise RuntimeError("Không tìm thấy dòng %r trong core/phien_ban.py" % cu)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s.replace(cu, moi, 1))


def tim_release(token, tag):
    """Bản phát hành mang thẻ `tag`, hoặc None nếu chưa có.

    Bắt `RuntimeError` chứ KHÔNG phải `HTTPError`: từ khi `_goi()` đọc phần thân
    lỗi của GitHub, nó ném `RuntimeError` mang câu đọc được. Để nguyên `except
    HTTPError` ở đây thì "chưa có bản này" (404 — chuyện BÌNH THƯỜNG ở lần phát
    hành đầu) sẽ nổ thành lỗi thật và cả lượt phát hành dừng."""
    try:
        return _goi("%s/repos/%s/releases/tags/%s" % (API, KHO_GITHUB, tag), token)
    except RuntimeError as e:
        if "404" in str(e):
            return None
        raise


def xoa_tep_cu(token, rel, ten):
    """Đẩy lại cùng tên thì GitHub báo lỗi 'đã tồn tại' -> xoá cái cũ trước."""
    for a in (rel.get("assets") or []):
        if a.get("name") == ten:
            _goi("%s/repos/%s/releases/assets/%s" % (API, KHO_GITHUB, a["id"]),
                 token, method="DELETE", doc_json=False)
            return True
    return False


def day_tep(token, rel, duong, ten=None, kieu="application/octet-stream"):
    ten = ten or os.path.basename(duong)
    xoa_tep_cu(token, rel, ten)
    # MA HOA ten: dau cach / ky tu la trong URL -> urllib nem InvalidURL (loi that 29/09).
    url = rel["upload_url"].split("{")[0] + "?name=" + urllib.parse.quote(ten)
    with open(duong, "rb") as f:
        data = f.read()
    return _goi(url, token, data=data, kieu=kieu)


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    thu = "--thu" in argv
    # MẶC ĐỊNH CHỈ ĐẨY FILE TOOL (người dùng chốt 26/09: "chỉ gửi file lvc
    # slide.exe lên thôi"). `--du` thì đẩy kèm bộ cập nhật và mô tả sha256.
    du = "--du" in argv
    ban = PHIEN_BAN
    ghi_chu = ""
    for i, x in enumerate(argv):
        if x == "--ban" and i + 1 < len(argv):
            ban = argv[i + 1].strip().lstrip("vV")
        if x == "--ghi-chu" and i + 1 < len(argv):
            ghi_chu = argv[i + 1]

    exe = os.path.join(GOC, "dist", TEN_EXE)
    if not os.path.isfile(exe):
        print("❌ Chưa có %s.\n   Chạy `python build.py` trước." % exe)
        return 1
    co_lon = os.path.getsize(exe)
    print("📦 Tệp    : %s (%.1f MB)" % (exe, co_lon / 1048576.0))
    print("🏷️ Phiên bản: %s" % ban)
    print("📚 Kho    : %s" % KHO_GITHUB)
    print("🔒 Đang tính sha256...")
    bam = sha256(exe)
    print("   %s" % bam)

    mo_ta = {"phien_ban": ban, "ten_tep": TEN_TEP_PHAT_HANH, "dung_luong": co_lon,
             "sha256": bam}

    if thu:
        print("\n--thu: DỪNG Ở ĐÂY, không đẩy gì lên.")
        print(json.dumps(mo_ta, ensure_ascii=False, indent=2))
        return 0

    token = doc_token()
    if not token:
        print("\n❌ Chưa có mã truy cập GitHub.")
        print("   Cách 1: đặt biến môi trường GITHUB_TOKEN")
        print("   Cách 2: ghi token vào  %s" % TEP_TOKEN)
        print("   Tạo token: https://github.com/settings/tokens "
              "(Generate new token (classic) → tích quyền 'repo')")
        return 1

    if ban != PHIEN_BAN:
        dat_phien_ban(ban)
        print("✍️ Đã ghi phiên bản %s vào core/phien_ban.py" % ban)

    # Ghi `phien_ban.txt` vào dist/ để bản cài biết mình là bản nào.
    io.open(os.path.join(GOC, "dist", TEN_FILE_PHIEN_BAN), "w",
            encoding="utf-8", newline="\n").write(ban)

    # Kho MỚI TINH chưa có commit nào thì không tạo được bản phát hành: thẻ tag
    # phải trỏ vào một commit. Làm hộ đúng một lần, rồi đi tiếp.
    if repo_trong(token):
        print("🌱 Kho còn trống — tạo commit đầu tiên (README) để có chỗ gắn thẻ...")
        tao_commit_dau(token)
        print("   xong.")

    tag = "v" + ban
    rel = tim_release(token, tag)
    if rel is None:
        print("🆕 Tạo bản phát hành %s..." % tag)
        rel = _goi("%s/repos/%s/releases" % (API, KHO_GITHUB), token,
                   data=json.dumps({
                       "tag_name": tag, "name": tag,
                       "body": ghi_chu or "Bản %s" % ban,
                       "draft": False, "prerelease": False,
                   }).encode("utf-8"))
    else:
        print("♻️ Bản phát hành %s đã có — đẩy đè tệp." % tag)
        if ghi_chu:
            _goi("%s/repos/%s/releases/%s" % (API, KHO_GITHUB, rel["id"]), token,
                 data=json.dumps({"body": ghi_chu}).encode("utf-8"), method="PATCH")

    print("⬆️ Đang đẩy %s (%.1f MB)... có thể mất vài phút."
          % (TEN_EXE, co_lon / 1048576.0))
    day_tep(token, rel, exe, TEN_TEP_PHAT_HANH)

    # capnhat.json (~200 byte) LUON day: bo cap nhat dung no kiem sha256 sau khi tai.
    # Bo cap nhat (~10 MB) chi day khi --du hoac khi ban nay chua co no (ban dau tien).
    co_updater = any(a.get("name") == TEN_UPDATER for a in (rel.get("assets") or []))
    if True:
        # `capnhat.json` chỉ ~200 byte nhưng là thứ cho bộ cập nhật KIỂM sha256
        # sau khi tải xong. Không có nó thì vẫn cập nhật được, chỉ còn phép kiểm
        # DUNG LƯỢNG — yếu hơn hẳn: một file hỏng mà đúng cỡ vẫn lọt qua.
        tam_mo_ta = os.path.join(GOC, "dist", TEN_MO_TA)
        io.open(tam_mo_ta, "w", encoding="utf-8", newline="\n").write(
            json.dumps(mo_ta, ensure_ascii=False, indent=1))
        print("⬆️ Đang đẩy %s..." % TEN_MO_TA)
        # Lấy lại release để `assets` có cái vừa đẩy (nếu không, lần đẩy sau
        # không thấy tệp cũ mà xoá -> GitHub báo trùng tên).
        rel = tim_release(token, tag) or rel
        day_tep(token, rel, tam_mo_ta, TEN_MO_TA, kieu="application/json")

        # Bộ cập nhật ~10,5 MB và gần như không bao giờ đổi; ai đã có tool thì
        # đã có sẵn nó. Chỉ đẩy lại khi CHÍNH nó được sửa.
        up = os.path.join(GOC, "dist", TEN_UPDATER)
        if not (du or not co_updater):
            print("ℹ️ Không đẩy lại %s (bản này đã có; thêm --du để đẩy)." % TEN_UPDATER)
        elif os.path.isfile(up):
            print("⬆️ Đang đẩy %s..." % TEN_UPDATER)
            rel = tim_release(token, tag) or rel
            day_tep(token, rel, up, TEN_UPDATER)
        else:
            print("ℹ️ Chưa có dist/%s — chạy `python build_capnhat.py`." % TEN_UPDATER)

    print("\n✅ XONG: https://github.com/%s/releases/tag/%s" % (KHO_GITHUB, tag))
    print("   Người dùng mở tool sẽ thấy nút vàng báo bản mới, hoặc bấm %s." % TEN_UPDATER)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        # Lỗi đã có câu đọc được rồi -> in câu đó, đừng đổ traceback ra màn hình
        # người dùng: nó dài, và chôn mất đúng dòng cần đọc.
        print("\n❌ %s" % e)
        sys.exit(1)
