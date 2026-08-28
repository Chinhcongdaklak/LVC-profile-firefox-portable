"""Mo hinh du lieu acc va noi luu tru (JSON)."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field, asdict
from typing import Iterator, Optional

from .config import ACCOUNTS_PATH
from .proxy import Proxy

STATUSES = ("Chưa rõ", "Live", "Checkpoint", "Die")

_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_folder_name(account_id: str) -> str:
    """Bien id acc thanh ten thu muc hop le tren Windows."""
    name = _INVALID_NAME.sub("_", (account_id or "").strip()).rstrip(". ")
    return name or "unnamed"


@dataclass
class Identity:
    """Mui gio va ngon ngu cua mot profile, suy ra tu quoc gia cua IP proxy."""

    timezone: str = ""            # ten IANA, vi du "Europe/Berlin"
    accept_languages: str = ""    # vi du "de-DE, de, en-US, en"
    country: str = ""             # ma 2 chu
    city: str = ""
    ip: str = ""                  # IP thoat luc do duoc
    checked_at: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.timezone or self.accept_languages)

    def summary(self) -> str:
        bits = [b for b in (self.city, self.country) if b]
        parts = [p for p in (", ".join(bits), self.timezone) if p]
        return " · ".join(parts)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Optional[dict]) -> "Identity":
        if not raw:
            return cls()
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class Account:
    id: str = ""
    password: str = ""
    recovery_mail: str = ""
    #: Mat khau cua chinh mail khoi phuc.
    recovery_mail_password: str = ""
    #: Mail khoi phuc CUA mail khoi phuc -- chuoi khoi phuc thuong di ba tang.
    recovery_mail_backup: str = ""
    twofa: str = ""
    cookie: str = ""
    proxy: dict = field(default_factory=dict)
    #: Mui gio / ngon ngu khop theo IP proxy (xem lop Identity).
    identity: dict = field(default_factory=dict)
    #: Tu do lai danh tinh moi khi doi proxy.
    auto_identity: bool = True
    group: str = ""
    status: str = "Chưa rõ"
    note: str = ""
    #: Cac truong phu (token, email, phone, user_agent, dob...) khong co cot rieng.
    #: Giu o day de nhap hang loat khong lam mat du lieu.
    extra: dict = field(default_factory=dict)
    #: Ket qua lan test proxy gan nhat: "Live", "Die" hoac rong (chua test).
    #: Cot "Trang thai" uu tien hien gia tri nay -- xem App._row_values.
    proxy_status: str = ""
    #: Thoi diem test proxy gan nhat (chi de xem lai, khong dung de tinh toan).
    proxy_checked: str = ""
    #: Thoi diem dang nhap bang cookie thanh cong gan nhat. Rong = chua chay.
    #: Dung de to mau dong trong bang, va luu lai de tat tool mo lai van con.
    cookie_ok: str = ""
    created_at: str = ""
    last_opened: str = ""

    @property
    def folder(self) -> str:
        return safe_folder_name(self.id)

    def get_proxy(self) -> Proxy:
        return Proxy.from_dict(self.proxy)

    def set_proxy(self, value: Proxy) -> None:
        self.proxy = value.to_dict() if value.enabled else {}

    def get_identity(self) -> Identity:
        return Identity.from_dict(self.identity)

    def set_identity(self, value: Optional[Identity]) -> None:
        self.identity = value.to_dict() if value and value.enabled else {}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Account":
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        known.setdefault("id", "")
        if not isinstance(known.get("proxy"), dict):
            known["proxy"] = {}
        if not isinstance(known.get("identity"), dict):
            known["identity"] = {}
        if not isinstance(known.get("extra"), dict):
            known["extra"] = {}
        cls._migrate_extra(known)
        return cls(**known)

    #: Truoc day cot Email / Pass Email khi nhap hang loat bi do vao tui phu
    #: ``extra`` -- ma bang chi tiet lai doc truong that, nen nhap xong khong
    #: thay dau. Doc file cu thi keo chung ve dung cho.
    _EXTRA_MOVED = {
        "email": "recovery_mail",
        "pass_email": "recovery_mail_password",
        "recovery_mail_pass": "recovery_mail_password",
    }

    @classmethod
    def _migrate_extra(cls, known: dict) -> None:
        extra = known.get("extra") or {}
        for source, target in cls._EXTRA_MOVED.items():
            value = str(extra.get(source) or "").strip()
            if value and not str(known.get(target) or "").strip():
                known[target] = value
                extra.pop(source, None)


class AccountStore:
    """Danh sach acc, luu ra file JSON canh tool."""

    def __init__(self, path: str = ACCOUNTS_PATH):
        self.path = path
        self.accounts: list[Account] = []
        # Danh sach nhom nguoi dung tu tao. Phai luu rieng chu khong suy ra tu acc,
        # neu khong nhom vua tao ma chua co acc nao se bien mat ngay.
        self.group_names: list[str] = []
        self.load()

    # ---- doc/ghi ------------------------------------------------------
    def load(self) -> None:
        if not os.path.isfile(self.path):
            self.accounts = []
            self.group_names = []
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            self.accounts = []
            self.group_names = []
            return
        items = raw.get("accounts", raw) if isinstance(raw, dict) else raw
        self.accounts = [Account.from_dict(item) for item in items if isinstance(item, dict)]
        stored = raw.get("groups", []) if isinstance(raw, dict) else []
        self.group_names = [
            str(name).strip() for name in stored if str(name).strip()
        ]

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = {
            "version": 1,
            "groups": self.group_names,
            "accounts": [a.to_dict() for a in self.accounts],
        }
        temp = self.path + ".tmp"
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        # Ghi ra file tam roi doi ten de khong mat du lieu neu tool bi tat giua chung.
        shutil.move(temp, self.path)

    # ---- truy van -----------------------------------------------------
    def __iter__(self) -> Iterator[Account]:
        return iter(self.accounts)

    def __len__(self) -> int:
        return len(self.accounts)

    def get(self, account_id: str) -> Optional[Account]:
        for account in self.accounts:
            if account.id == account_id:
                return account
        return None

    def groups(self) -> list[str]:
        """Nhom nguoi dung tu tao, cong them nhom cu con dinh tren acc.

        Phan sau de khong mat nhom o file accounts.json cu (chua co khoa
        ``groups``) va o cac acc nhap hang loat kem ten nhom moi.
        """
        in_use = {a.group.strip() for a in self.accounts if a.group.strip()}
        return sorted(set(self.group_names) | in_use, key=str.lower)

    def count_in_group(self, name: str) -> int:
        return sum(1 for a in self.accounts if a.group.strip() == name.strip())

    # ---- nhom ---------------------------------------------------------
    def add_group(self, name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise ValueError("Tên nhóm không được để trống.")
        for existing in self.groups():
            if existing.lower() == name.lower():
                raise ValueError(f"Nhóm '{existing}' đã có rồi.")
        self.group_names.append(name)
        self.save()
        return name

    def rename_group(self, old: str, new: str) -> int:
        """Doi ten nhom va keo theo moi acc dang o nhom do. Tra ve so acc bi doi."""
        old, new = (old or "").strip(), (new or "").strip()
        if not new:
            raise ValueError("Tên nhóm không được để trống.")
        if old == new:
            return 0
        for existing in self.groups():
            if existing.lower() == new.lower() and existing != old:
                raise ValueError(f"Nhóm '{existing}' đã có rồi.")
        self.group_names = [new if g == old else g for g in self.group_names]
        if new not in self.group_names:
            self.group_names.append(new)
        moved = 0
        for account in self.accounts:
            if account.group.strip() == old:
                account.group = new
                moved += 1
        self.save()
        return moved

    def remove_group(self, name: str) -> int:
        """Xoa nhom; acc trong nhom do tro thanh khong nhom. Tra ve so acc anh huong."""
        name = (name or "").strip()
        self.group_names = [g for g in self.group_names if g != name]
        cleared = 0
        for account in self.accounts:
            if account.group.strip() == name:
                account.group = ""
                cleared += 1
        self.save()
        return cleared

    def assign_group(self, account_ids: list[str], name: str) -> int:
        """Chuyen cac acc sang mot nhom. ``name`` rong nghia la bo khoi nhom."""
        name = (name or "").strip()
        if name and name not in self.groups():
            self.group_names.append(name)
        wanted = set(account_ids)
        moved = 0
        for account in self.accounts:
            if account.id in wanted and account.group != name:
                account.group = name
                moved += 1
        self.save()
        return moved

    def search(self, keyword: str = "", group: str = "", status: str = "") -> list[Account]:
        keyword = (keyword or "").strip().lower()
        result = []
        for account in self.accounts:
            if group and account.group != group:
                continue
            if status and account.status != status:
                continue
            if keyword:
                haystack = " ".join([
                    account.id, account.recovery_mail, account.group,
                    account.note, account.get_proxy().as_text(),
                ]).lower()
                if keyword not in haystack:
                    continue
            result.append(account)
        return result

    # ---- thay doi -----------------------------------------------------
    def add(self, account: Account) -> Account:
        if not account.id.strip():
            raise ValueError("ID acc không được để trống.")
        if self.get(account.id):
            raise ValueError(f"ID '{account.id}' đã tồn tại trong danh sách.")
        account.created_at = account.created_at or time.strftime("%Y-%m-%d %H:%M")
        self.accounts.append(account)
        self.save()
        return account

    def update(self, original_id: str, account: Account) -> Account:
        for index, existing in enumerate(self.accounts):
            if existing.id == original_id:
                if account.id != original_id and self.get(account.id):
                    raise ValueError(f"ID '{account.id}' đã tồn tại trong danh sách.")
                account.created_at = existing.created_at
                account.last_opened = existing.last_opened
                self.accounts[index] = account
                self.save()
                return account
        raise KeyError(original_id)

    def remove(self, account_id: str) -> None:
        self.accounts = [a for a in self.accounts if a.id != account_id]
        self.save()

    def mark_opened(self, account_id: str) -> None:
        account = self.get(account_id)
        if account:
            account.last_opened = time.strftime("%Y-%m-%d %H:%M")
            self.save()

    def import_lines(
        self,
        text: str,
        separator: str = "|",
        fields: Optional[list[str]] = None,
        group: str = "",
    ) -> tuple[int, list[str]]:
        """Nhap hang loat theo dinh dang cot nguoi dung chon.

        ``fields`` la thu tu y nghia cua tung cot, vi du
        ``["id", "password", "recovery_mail", "twofa", "proxy"]``. Khoa rong ("")
        nghia la bo qua cot do. ``group`` (neu co) ep tat ca acc vao mot nhom.

        Tra ve ``(so acc them duoc, danh sach loi)``.
        """
        from . import proxy as proxy_module

        fields = fields or ["id", "password", "recovery_mail", "twofa", "proxy", "group"]
        # Nhan moi truong chu cua Account, thay vi mot danh sach viet cung: them
        # truong moi ma quen sua cho nay thi nhap hang loat se im lang bo qua cot
        # do -- dung la loi da tung xay ra voi hai o mail khoi phuc.
        text_keys = {
            name for name, spec in Account.__dataclass_fields__.items()
            if spec.type in ("str", str) and name not in {"created_at", "last_opened"}
        }
        group = (group or "").strip()
        if group and group not in self.groups():
            self.group_names.append(group)

        added = 0
        errors: list[str] = []
        for number, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(separator)]

            account = Account()
            bad = False
            for index, key in enumerate(fields):
                if not key or index >= len(parts):
                    continue
                value = parts[index]
                if not value:
                    continue
                if key == "proxy":
                    try:
                        account.set_proxy(proxy_module.parse(value))
                    except ValueError as exc:
                        errors.append(f"Dòng {number}: {exc}")
                        bad = True
                        break
                elif key.startswith("x:"):
                    account.extra[key[2:]] = value  # truong phu (token, email...)
                elif key in text_keys:
                    setattr(account, key, value)
                elif key == "cookie":
                    account.cookie = value
            if bad:
                continue

            if group:
                account.group = group  # nhom da chon ep len tat ca
            if not account.id:
                errors.append(f"Dòng {number}: thiếu ID acc")
                continue
            try:
                self.add(account)
                added += 1
            except ValueError as exc:
                errors.append(f"Dòng {number}: {exc}")
        return added, errors
