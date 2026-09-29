"""Phan dung chung cho mo-dun ĐĂNG BÀI TỰ ĐỘNG (fanpage / nhom): thao tac len MOT job AutoUploader.

Khong dang ky mo-dun (file bat dau bang _ -> kien_truc_modun bo qua). Xem dang_fanpage_tu_dong.py /
dang_nhom_tu_dong.py.
"""

from __future__ import annotations

import os

from core.modun import KetQua, NguCanh

HANH_DONG = ("bat", "tat", "dang_ngay")


def lay_job(nc: NguCanh, tham_so: dict):
    """Job tu tham_so['job'] hoac tra nc.autoup theo tham_so['job_id']. Nem ValueError neu thieu."""
    job = tham_so.get("job")
    if job is not None:
        return job
    job_id = (tham_so.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("thiếu tham số job hoặc job_id")
    if nc.autoup is None:
        raise ValueError("NguCanh.autoup trống — không tra được job theo id")
    job = nc.autoup.get(job_id)
    if job is None:
        raise ValueError(f"không có job {job_id}")
    return job


def thao_tac_job(nc: NguCanh, tham_so: dict, kind) -> KetQua:
    """bat / tat / dang_ngay len job cua ``kind``.

    ``kind`` nhan mot chuoi hoac nhieu chuoi: trang DAT LICH ("lich") dang len
    fanpage nen di CHUNG duong voi "page". Truoc day chi so bang mot chuoi ->
    job "lich" bi tu choi -> bam TAT cong tac ma cfg.enabled khong he doi, trang
    van chay tiep (nguoi dung bao "tat roi ma no van chay").
    """
    kq = KetQua()
    job = lay_job(nc, tham_so)
    jid = str(getattr(job, "job_id", "") or "")
    cfg = job.config
    nhan = (kind,) if isinstance(kind, str) else tuple(kind)
    loai = getattr(cfg, "target_kind", "page") or "page"
    if loai not in nhan:
        kq.them_loi(jid, f"job là '{loai}', không phải '{'/'.join(nhan)}'")
        return kq
    hanh_dong = (tham_so.get("hanh_dong") or "").strip()
    if hanh_dong not in HANH_DONG:
        raise ValueError(f"hanh_dong phải là một trong {HANH_DONG}")
    try:
        if hanh_dong == "bat":
            cfg.enabled = True
            job.save()
            if cfg.schedule_mode == "delay":
                job.run_delay_now()
                kq.ghi_chu = "đã bật — sẽ đăng bài đầu ngay bây giờ"
            else:
                job.skip_past()
                kq.ghi_chu = "đã bật — chờ đúng mốc giờ mới đăng"
            job.start()
        elif hanh_dong == "tat":
            cfg.enabled = False
            job.save()
            job.stop()
            kq.ghi_chu = "đã tắt tự động đăng"
        else:
            video = tham_so.get("video") or job.next_video()
            if not video:
                kq.them_loi(jid, "thư mục không có video/bài nào sẵn sàng")
                return kq
            nc.log(f"Đang đăng {os.path.basename(str(video))} lên {cfg.label()}...")
            r = job.upload_now(video)
            kq.ghi_chu = f"đăng ngay: {r or 'xong'}"
            kq.du_lieu["ket_qua"] = r
        kq.them_ok(jid)
    except Exception as exc:  # noqa: BLE001
        kq.them_loi(jid, str(exc)[:200])
    kq.du_lieu["job_id"] = jid
    return kq
