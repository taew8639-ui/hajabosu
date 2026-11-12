"""접수함 폴더의 원문을 모두 읽어 하자대장 CSV로 저장한다.

사용:  python run.py [입력폴더] [저장파일]
기본:  data/접수함  ->  data/하자대장.csv
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import ai
import rules

BASE = Path(__file__).resolve().parent
열 = ["접수번호", "접수일", "원문파일", "위치", "공종", "하자내용", "긴급도", "조치기한",
      "공사번호", "시공업체", "준공일", "보증만료일", "보증판정", "책임구분", "상태", "비고"]


def _파일명_날짜(파일명: str) -> str | None:
    """파일명 속 YYYYMMDD를 YYYY-MM-DD로. 없으면 None."""
    m = re.search(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)", 파일명)
    return f"{m[1]}-{m[2]}-{m[3]}" if m else None


def 한건_처리(파일: Path, 순번표: dict) -> dict:
    행 = dict.fromkeys(열, "")
    행["원문파일"] = 파일.name
    try:
        해석 = ai.접수정리(파일.read_text(encoding="utf-8"), 파일.name)
        접수일 = 해석["접수일"] or _파일명_날짜(파일.name)  # 원문 날짜 우선, 없으면 파일명
        if not 접수일:
            raise ValueError("접수일을 알 수 없음")
        순번표[접수일] += 1
        행.update(접수번호=rules.접수번호(접수일, 순번표[접수일]), 접수일=접수일,
                위치=해석["위치"], 공종=해석["공종"], 하자내용=해석["하자내용"],
                긴급도=해석["긴급도"])
        행["조치기한"] = rules.조치기한(접수일, 해석["긴급도"]).isoformat()
        행.update(rules.보증판정(접수일, 해석["위치"], 해석["공종"]))
    except Exception as e:  # 한 건이 실패해도 나머지는 계속 처리하고, 실패 건은 확인필요로 남긴다
        행["상태"] = "확인필요"
        행["비고"] = f"처리 실패: {type(e).__name__}: {e}"
    return 행


def main(입력: Path, 출력: Path) -> None:
    파일들 = sorted(p for p in 입력.glob("*.txt"))
    순번표: dict = defaultdict(int)
    행들 = []
    for p in 파일들:
        행 = 한건_처리(p, 순번표)
        행들.append(행)
        print(f"[{len(행들)}/{len(파일들)}] {행['접수번호'] or '-'} {행['보증판정'] or '실패'}")
    with open(출력, "w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: 엑셀에서 한글이 깨지지 않게
        w = csv.DictWriter(f, fieldnames=열)
        w.writeheader()
        w.writerows(행들)
    실패 = sum(1 for r in 행들 if r["비고"].startswith("처리 실패"))
    print(f"저장 {len(행들)}건 (실패 {실패}건)")


if __name__ == "__main__":
    입력 = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "data" / "접수함"
    출력 = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "data" / "하자대장.csv"
    main(입력, 출력)
