"""SO PHIEN BAN — MOT cho khai duy nhat (giong tool Video Slide).

Bo cap nhat so so nay de biet may nguoi dung co phai tai ban moi khong, nen no chi co
DUNG MOT nguon. Cua so "Phat hanh" (phat_hanh_gui.py) ghi so moi vao DUNG dong PHIEN_BAN.

Cach danh so X.Y.Z:  X doi lon (lam quen lai) · Y them tinh nang · Z chi sua loi.
So sanh theo TUNG SO ("1.10.0" moi hon "1.9.0") — xem capnhat.so_sanh().

Module nay KHONG import gi cua du an de phat_hanh.py / capnhat.py doc duoc ma khong keo
theo giao dien.
"""

PHIEN_BAN = "1.1.0"

#: Kho PHAT HANH tren GitHub (chi chua Releases, ma nguon o kho khac).
KHO_GITHUB = "Chinhcongdaklak/congprofile"

#: File chuong trinh chinh — thu bo cap nhat thay (ten tren MAY nguoi dung).
TEN_EXE = "LVC Manager Profile.exe"

#: Ten tep DINH KEM tren GitHub Release. KHONG co dau cach: (1) dau cach lam URL tai len
#: hong ("URL can't contain control characters" — loi that lan phat hanh dau 29/09), (2) GitHub
#: tu doi dau cach thanh dau cham. Bo cap nhat tai tep nay roi luu thanh TEN_EXE.
TEN_TEP_PHAT_HANH = "LVC.Manager.Profile.exe"

#: Bo cap nhat rieng (khong trung LVCUpdate.exe cua Video Slide neu de chung thu muc).
TEN_UPDATER = "LVCProfileUpdate.exe"

#: File mo ta ban phat hanh (sha256 + dung luong), dinh kem trong Release.
TEN_MO_TA = "capnhat.json"

#: File ghi phien ban DANG CAI, nam canh .exe (bo cap nhat doc/ghi).
TEN_FILE_PHIEN_BAN = "phien_ban.txt"
