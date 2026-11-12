"""번호·기한·판정 규칙. 기준은 data/업무설명_하자보수.md (4~6절).

AI를 부르지 않는다. 같은 입력이면 항상 같은 답이 나온다.
"""
import csv
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
공사정보_경로 = BASE / "data" / "공사정보.csv"

조치기한_일수 = {"긴급": 1, "높음": 3, "보통": 7}  # 업무설명 4절
만료임박_일수 = 30  # 업무설명 5절


def _날짜(값) -> date:
    if isinstance(값, datetime):
        return 값.date()
    if isinstance(값, date):
        return 값
    return datetime.strptime(str(값).strip(), "%Y-%m-%d").date()


def _공백정리(글: str) -> str:
    return " ".join(str(글).split())


# ---------- 접수번호 ----------
def 접수번호(접수일, 순번: int) -> str:
    """HJ-접수일(YYYYMMDD)-순번(01부터). 순번은 같은 접수일 안에서 센다."""
    if 순번 < 1:
        raise ValueError("순번은 1부터 시작합니다.")
    return f"HJ-{_날짜(접수일):%Y%m%d}-{순번:02d}"


# ---------- 조치기한 ----------
def 조치기한(접수일, 긴급도: str) -> date:
    """긴급 접수일+1일, 높음 +3일, 보통 +7일."""
    if 긴급도 not in 조치기한_일수:
        raise ValueError(f"알 수 없는 긴급도: {긴급도!r} (긴급/높음/보통 중 하나여야 함)")
    return _날짜(접수일) + timedelta(days=조치기한_일수[긴급도])


# ---------- 공사정보 ----------
def 공사정보_읽기(경로: Path = 공사정보_경로) -> list[dict]:
    for 인코딩 in ("utf-8-sig", "cp949"):
        try:
            with open(경로, encoding=인코딩, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"공사정보 인코딩을 읽을 수 없습니다: {경로}")


def 보증만료일(준공일, 보증기간_년) -> date:
    """준공일 + 하자보증기간(년). 2월 29일 준공은 평년에 2월 28일로 본다."""
    준공 = _날짜(준공일)
    년 = 준공.year + int(보증기간_년)
    try:
        return 준공.replace(year=년)
    except ValueError:
        return 준공.replace(year=년, day=28)


def _공종_후보(공종: str) -> list[str]:
    """`설비/타일` -> ['설비','타일']. 미정이거나 비어 있으면 빈 목록."""
    후보 = [p.strip() for p in str(공종).split("/") if p.strip()]
    return [] if (not 후보 or "미정" in 후보) else 후보


def _만료임박(접수일: date, 만료일: date) -> bool:
    남은 = (만료일 - 접수일).days
    return 0 <= 남은 <= 만료임박_일수


# ---------- 보증 판정 ----------
def 보증판정(접수일, 위치: str, 공종: str, 공사목록: list[dict] | None = None) -> dict:
    """위치와 공종이 모두 같은 공사를 찾아 보증 여부를 판정한다. 판정 기준일은 접수일.

    돌려주는 칸: 공사번호, 시공업체, 준공일, 보증만료일, 보증판정, 책임구분, 상태, 비고
    - 보증내(시공업체) / 보증만료(자체보수) / 확인필요(담당자가 확인)
    - 맞는 공사가 없거나 2건 이상이거나 공종이 미정·후보 병기이면 확인필요
    """
    접수 = _날짜(접수일)
    공사목록 = 공사정보_읽기() if 공사목록 is None else 공사목록
    위치 = _공백정리(위치)
    후보공종 = _공종_후보(공종)

    # 같은 위치에서 후보 공종에 해당하는 공사들
    후보공사 = [
        c for c in 공사목록
        if _공백정리(c["위치"]) == 위치 and (not 후보공종 or c["공종"].strip() in 후보공종)
    ]
    for c in 후보공사:
        c["_만료일"] = 보증만료일(c["준공일"], c["하자보증기간(년)"])

    결과 = {"공사번호": "", "시공업체": "", "준공일": "", "보증만료일": "",
            "보증판정": "확인필요", "책임구분": "확인필요", "상태": "확인필요", "비고": ""}

    # 공종이 하나로 정해졌고 맞는 공사가 정확히 1건일 때만 판정한다
    if len(후보공종) == 1 and len(후보공사) == 1:
        c = 후보공사[0]
        만료 = c["_만료일"]
        결과.update(공사번호=c["공사번호"], 시공업체=c["시공업체"], 준공일=c["준공일"],
                  보증만료일=만료.isoformat(), 상태="판정완료")
        if 접수 <= 만료:  # 같은 날 포함
            결과.update(보증판정="보증내", 책임구분="시공업체")
            if _만료임박(접수, 만료):
                결과["비고"] = "만료임박"
        else:
            결과.update(보증판정="보증만료", 책임구분="자체보수")
        return 결과

    # 확인필요: 사유와, 만료임박인 후보 공사를 비고에 적는다
    if not 후보공종:
        사유 = "공종 미정"
    elif len(후보공종) > 1:
        사유 = "공종 후보 " + "/".join(후보공종)
    elif not 후보공사:
        사유 = "맞는 공사 없음"
    else:
        사유 = f"맞는 공사 {len(후보공사)}건"
    임박 = [f"{c['공사번호']}({c['_만료일'].isoformat()})" for c in 후보공사
          if _만료임박(접수, c["_만료일"])]
    결과["비고"] = 사유 + (" / 후보 공사 만료임박: " + ", ".join(임박) if 임박 else "")
    return 결과
