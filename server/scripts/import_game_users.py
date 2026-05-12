from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auth


PINYIN = {
    "朱蕾": "zhulei",
    "龙福": "longfu",
    "刘新贝": "liuxinbei",
    "郭盈": "guoying",
    "刘法佳": "liufajia",
    "陈舒": "chenshu",
    "胡琪": "huqi",
    "向宇婷": "xiangyuting",
    "贺启涛": "heqitao",
    "罗馨怡": "luoxinyi",
    "孟忠诚": "mengzhongcheng",
    "徐杨": "xuyang",
    "邓春梅": "dengchunmei",
    "张海涛": "zhanghaitao",
    "薛科文": "xuekewen",
    "黄娟": "huangjuan",
    "罗健梅": "luojianmei",
    "姚林希": "yaolinxi",
    "汤达宇": "tangdayu",
    "黄浪": "huanglang",
    "曾珺": "zengjun",
    "杨洁": "yangjie",
    "邓雨佳": "dengyujia",
    "杨杭": "yanghang",
    "杨一宁": "yangyining",
    "罗瑾瑜": "luojinyu",
    "刘宇星": "liuyuxing",
    "黄弋芹": "huangyiqin",
    "黄也": "huangye",
    "粟玉": "suyu",
    "江彩燕": "jiangcaiyan",
    "李刘阳": "liliuyang",
    "李奚禾": "lixihe",
    "吕寒英": "lvhanying",
    "易宇": "yiyu",
    "高甜甜": "gaotiantian",
}


def load_rows(csv_path: Path) -> list[dict]:
    rows = []
    current_team = ""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            team = (row.get("团队名称") or "").strip()
            name = (row.get("使用人") or "").strip()
            ip = (row.get("ip") or "").strip()
            if team:
                current_team = team
            if not name:
                continue
            username = PINYIN.get(name)
            if not username:
                raise ValueError(f"Missing pinyin mapping for {name}")
            rows.append({
                "username": username,
                "display_name": name,
                "team": team or current_team,
                "allowed_ips": ip,
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Import game-video-tool users from CSV.")
    parser.add_argument("csv", nargs="?", default=r"D:\下载-gool\顽皮ai视频 - 加白ip.csv")
    parser.add_argument("--password", default="123456")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    rows = load_rows(csv_path)
    imported = []
    for row in rows:
        imported.append(auth.upsert_imported_user(
            username=row["username"],
            password=args.password,
            display_name=row["display_name"],
            team=row["team"],
            allowed_ips=row["allowed_ips"],
        ))
    print(f"imported={len(imported)}")
    for user in imported:
        print(f"{user['username']}\t{user['display_name']}\t{user.get('team', '')}\t{user.get('allowed_ips', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
