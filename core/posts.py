"""Kho luu cac bai viet da quet tu nhom Facebook.

Moi bai gom: caption (noi dung), dinh dang (Anh/Video/Album/Text/Link) va
duong dan -- neu co anh thi la duong dan file anh da tai ve, khong thi la link
bai viet tren Facebook (content).

Luu ra ``data/posts.json`` canh tool.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from typing import Iterator, Optional

from .config import TOOL_DIR

POSTS_PATH = os.path.join(TOOL_DIR, "data", "posts.json")
MEDIA_DIR = os.path.join(TOOL_DIR, "data", "post_media")


@dataclass
class Post:
    id: str = ""
    group: str = ""            # link/id nhom nguon
    caption: str = ""          # noi dung bai
    fmt: str = ""              # dinh dang: Anh / Video / Album / Text / Link
    permalink: str = ""        # link bai tren facebook (content)
    author: str = ""
    time: str = ""
    images: list = field(default_factory=list)   # link anh goc tren fbcdn
    videos: list = field(default_factory=list)   # link video
    saved_paths: list = field(default_factory=list)   # anh da tai ve (duong dan file)
    saved_videos: list = field(default_factory=list)  # video da tai ve
    status: str = ""            # trang thai tai: "Đã tải 2 ảnh, 1 video" / "Lỗi"...
    reactions: str = ""
    comments: str = ""
    scanned_at: str = ""

    @property
    def path_or_content(self) -> str:
        """Cot 'duong dan': anh da tai ve neu co, khong thi link bai (content)."""
        if self.saved_paths:
            return self.saved_paths[0] if len(self.saved_paths) == 1 else \
                f"{self.saved_paths[0]}  (+{len(self.saved_paths) - 1})"
        return self.permalink

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Post":
        known = {k: v for k, v in (raw or {}).items() if k in cls.__dataclass_fields__}
        for key in ("images", "videos", "saved_paths", "saved_videos"):
            if not isinstance(known.get(key), list):
                known[key] = []
        return cls(**known)


def classify(images: list, videos: list, caption: str, permalink: str) -> str:
    """Suy ra dinh dang bai tu media co san."""
    if videos:
        return "Video"
    if len(images) > 1:
        return "Album"
    if len(images) == 1:
        return "Ảnh"
    if caption.strip():
        return "Text"
    return "Link" if permalink else "Khác"


class PostStore:
    def __init__(self, path: str = POSTS_PATH):
        self.path = path
        self.posts: list[Post] = []
        self.load()

    def load(self) -> None:
        if not os.path.isfile(self.path):
            self.posts = []
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            self.posts = []
            return
        items = raw.get("posts", raw) if isinstance(raw, dict) else raw
        self.posts = [Post.from_dict(x) for x in items if isinstance(x, dict)]

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = {"version": 1, "posts": [p.to_dict() for p in self.posts]}
        temp = self.path + ".tmp"
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        shutil.move(temp, self.path)

    def __iter__(self) -> Iterator[Post]:
        return iter(self.posts)

    def __len__(self) -> int:
        return len(self.posts)

    def by_id(self, post_id: str) -> Optional[Post]:
        for p in self.posts:
            if p.id == post_id:
                return p
        return None

    def add_many(self, posts: list[Post], replace_group: str = "") -> int:
        """Them bai moi (chong trung theo id). Tra ve so bai them duoc.

        ``replace_group`` (neu co): xoa cac bai cu cua nhom do truoc khi them,
        de quet lai mot nhom cho ra danh sach moi thay vi don dong.
        """
        if replace_group:
            self.posts = [p for p in self.posts if p.group != replace_group]
        existing = {p.id for p in self.posts}
        added = 0
        for p in posts:
            if p.id and p.id in existing:
                continue
            existing.add(p.id)
            self.posts.append(p)
            added += 1
        self.save()
        return added

    def remove(self, post_ids: list[str]) -> int:
        wanted = set(post_ids)
        before = len(self.posts)
        self.posts = [p for p in self.posts if p.id not in wanted]
        self.save()
        return before - len(self.posts)

    def groups(self) -> list[str]:
        seen = []
        for p in self.posts:
            if p.group and p.group not in seen:
                seen.append(p.group)
        return seen
