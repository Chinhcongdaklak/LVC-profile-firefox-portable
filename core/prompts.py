"""Thu vien 'cau khoi chuyen' — bai dang de KEO TUONG TAC THAT trong group.

Facebook de xuat group co tuong tac that (comment/reaction that). Cach an toan &
hieu qua nhat de tao tuong tac la dang cau hoi / binh chon / mini-game khien
thanh vien TU comment -- khong phai tha like gia.

Moi cau la mau spintax (co the co {a|b}) de moi lan dang ra mot ban khac nhau.
Nguoi dung tu them/sua cau cua rieng minh.
"""

from __future__ import annotations

#: Thu vien mac dinh, chia theo nhom. Nguoi dung se sua/them trong tool.
LIBRARY: dict[str, list[str]] = {
    "Câu hỏi mở": [
        "Mọi người vào {điểm danh|comment} cho vui nào 🙋 Hôm nay ai đang làm gì thế?",
        "Câu hỏi hôm nay: {điều gì|thứ gì} khiến bạn {tâm đắc|thấy hữu ích} nhất tuần qua?",
        "Nếu được {khuyên|nhắn} người mới một câu, bạn sẽ nói gì? 👇",
        "Bạn {thường|hay} gặp khó khăn gì nhất? Cả nhà cùng gỡ nhé!",
        "Chia sẻ một {mẹo|tip} nhỏ mà bạn thấy {hiệu quả|đáng giá} nào 👇",
    ],
    "Bình chọn / Poll": [
        "Bình chọn nhanh 👇\n1️⃣ {Sáng|Buổi sáng}\n2️⃣ {Tối|Buổi tối}\nBạn {làm việc|tập trung} tốt hơn lúc nào? Comment số nhé!",
        "Bạn thích nội dung nào hơn?\nA. {Video hướng dẫn|Video}\nB. {Bài viết|Bài chữ} chi tiết\nComment A hoặc B nha!",
        "Team nào đây? 👀 Comment 🔥 nếu đồng ý, 💧 nếu không nhé!",
    ],
    "Chia sẻ kinh nghiệm": [
        "Ai đã từng {thử|làm} cái này rồi cho xin {review|nhận xét} với ạ 🙏",
        "Kinh nghiệm xương máu của bạn là gì? Kể cho anh em {tránh|né} với 👇",
        "Một công cụ/ứng dụng bạn {dùng hằng ngày|không thể thiếu} là gì?",
    ],
    "Mini-game / Điểm danh": [
        "Điểm danh cuối tuần 🎉 Comment {tỉnh/thành|nơi bạn đang ở} của bạn nào!",
        "Điền vào chỗ trống: 'Với tôi, ___ là quan trọng nhất.' 👇",
        "Đếm số nào! Người tiếp theo comment số {lớn hơn|kế tiếp} nhé 🔢",
    ],
}


def categories() -> list[str]:
    return list(LIBRARY.keys())


def all_prompts() -> list[str]:
    out = []
    for items in LIBRARY.values():
        out.extend(items)
    return out
