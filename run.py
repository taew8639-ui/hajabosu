"""접수함 폴더의 원문을 모두 읽어 하자대장 CSV로 저장하고, DB의 미처리 접수도 처리한다.

사용:  python run.py [입력폴더] [저장파일]
기본:  data/접수함  ->  data/하자대장.csv
DB 접수(intake.py로 받은 것)는 DB 하자대장에 저장된다. 접수일은 발견일이다.
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


def _대장_순번표() -> dict:
    """DB 하자대장에 이미 있는 접수번호에서 날짜별 가장 큰 순번을 센다 (번호가 겹치지 않게)."""
    표: dict = defaultdict(int)
    for 행 in rules.대장_읽기():
        m = re.fullmatch(r"HJ-(\d{4})(\d{2})(\d{2})-(\d+)", 행["접수번호"])
        if m:
            날 = f"{m[1]}-{m[2]}-{m[3]}"
            표[날] = max(표[날], int(m[4]))
    return 표


def db_접수_처리() -> tuple[int, int]:
    """DB 접수 중 미처리 건을 해석·판정해 DB 하자대장에 저장하고 처리완료로 바꾼다.

    접수일은 AI가 아니라 접수의 발견일이다. 실패한 건은 미처리로 남겨 다음 실행에서 다시 한다.
    돌려주는 값: (처리한 건수, 실패한 건수)
    """
    import db

    대기 = db.접수_읽기("미처리")
    if not 대기:
        print("DB 접수: 미처리 없음")
        return 0, 0
    순번표 = _대장_순번표()
    성공 = 실패 = 0
    for 건 in 대기:
        이름 = f"DB접수#{건['id']}"
        try:
            if not 건["발견일"]:
                raise ValueError("발견일이 없음")
            접수일 = 건["발견일"].isoformat()
            원문 = f"발견일: {접수일}\n위치: {건['위치'] or ''}\n내용: {건['내용'] or ''}"
            해석 = ai.접수정리(원문, 이름)
            번호 = rules.접수번호(접수일, 순번표[접수일] + 1)
            행 = dict.fromkeys(열, "")
            행.update(접수번호=번호, 접수일=접수일, 원문파일=이름, 위치=해석["위치"], 공종=해석["공종"],
                    하자내용=해석["하자내용"], 긴급도=해석["긴급도"])
            행["조치기한"] = rules.조치기한(접수일, 해석["긴급도"]).isoformat()
            행.update(rules.보증판정(접수일, 해석["위치"], 해석["공종"]))
            rules.대장_저장([행])
            순번표[접수일] += 1
            db.접수_처리완료(건["id"], 번호)
            성공 += 1
            print(f"[DB 접수 {건['id']}] {번호} {행['보증판정']}")
        except Exception as e:
            실패 += 1
            print(f"[DB 접수 {건['id']}] 실패(미처리로 둠): {type(e).__name__}: {e}")
    print(f"DB 접수 처리 {성공}건 (실패 {실패}건)")
    return 성공, 실패


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
    try:
        db_접수_처리()
    except Exception as e:  # DB에 못 닿아도 파일 처리 결과는 이미 저장됐다
        print(f"DB 접수 처리 못 함: {type(e).__name__}")


if __name__ == "__main__":
    입력 = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "data" / "접수함"
    출력 = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "data" / "하자대장.csv"
    main(입력, 출력)
