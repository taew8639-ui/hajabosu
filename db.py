"""저장은 이 파일에서만 한다. 연결 정보는 .env의 DATABASE_URL (웹 배포는 Secrets).

처음 연결할 때 테이블 2개(접수, 하자대장)를 만들고 둘 다 RLS를 켠다.
정책(policy)은 만들지 않는다. 그래서 Supabase의 공개 API 역할(anon·authenticated)은
두 테이블을 읽거나 쓸 수 없고, DATABASE_URL로 접속하는 소유자 계정만 쓸 수 있다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (Column, Date, DateTime, Integer, MetaData, Table, Text, create_engine,
                        func, select, text)
from sqlalchemy.dialects.postgresql import insert as pg_insert

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

# data/하자대장.csv와 같은 열, 같은 순서. 값은 CSV처럼 글(TEXT)로 둔다.
대장_열 = ["접수번호", "접수일", "원문파일", "위치", "공종", "하자내용", "긴급도", "조치기한",
         "공사번호", "시공업체", "준공일", "보증만료일", "보증판정", "책임구분", "상태", "비고"]

metadata = MetaData()

접수 = Table(
    "접수", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),  # 자동 번호
    Column("접수일시", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("발견일", Date),
    Column("접수자", Text),
    Column("부서", Text),
    Column("위치", Text),
    Column("내용", Text),
    Column("처리상태", Text, server_default="미처리", nullable=False),  # 미처리 / 처리완료
    Column("접수번호", Text),
)

하자대장 = Table(
    "하자대장", metadata,
    *[Column(c, Text, primary_key=(c == "접수번호")) for c in 대장_열],
)

_engine = None


def _주소() -> str:
    값 = os.getenv("DATABASE_URL", "").strip()
    if not 값:
        raise RuntimeError(".env에 DATABASE_URL 값이 없습니다.")
    # Supabase가 주는 postgresql:// 주소를 SQLAlchemy가 psycopg(3)로 읽게 맞춘다
    for 앞 in ("postgresql://", "postgres://"):
        if 값.startswith(앞):
            return "postgresql+psycopg://" + 값[len(앞):]
    return 값


def 연결():
    """엔진을 한 번만 만들고, 처음에는 테이블과 RLS를 준비한다."""
    global _engine
    if _engine is None:
        엔진 = create_engine(_주소(), pool_pre_ping=True)
        _초기화(엔진)
        _engine = 엔진
    return _engine


def _초기화(엔진) -> None:
    metadata.create_all(엔진)  # 이미 있으면 건너뛴다
    with 엔진.begin() as conn:
        for 이름 in ("접수", "하자대장"):  # 여러 번 실행해도 같은 결과
            conn.execute(text(f'ALTER TABLE "{이름}" ENABLE ROW LEVEL SECURITY'))


# ---------- 하자대장 ----------
def 대장_읽기() -> list[dict]:
    """하자대장 전체를 접수번호 순으로 돌려준다. 칸 순서는 CSV와 같다."""
    with 연결().connect() as conn:
        행들 = conn.execute(select(하자대장).order_by(하자대장.c.접수번호)).mappings().all()
    return [{c: (행[c] or "") for c in 대장_열} for 행 in 행들]


def 대장_저장(행들: list[dict]) -> int:
    """접수번호가 같으면 덮어쓰고 없으면 추가한다. 다른 행은 지우지 않는다. 저장한 건수를 돌려준다."""
    자료 = [{c: str(행.get(c, "") or "") for c in 대장_열} for 행 in 행들]
    if not 자료:
        return 0
    if any(not r["접수번호"] for r in 자료):
        raise ValueError("접수번호가 비어 있는 행이 있습니다.")
    문장 = pg_insert(하자대장).values(자료)
    문장 = 문장.on_conflict_do_update(
        index_elements=[하자대장.c.접수번호],
        set_={c: 문장.excluded[c] for c in 대장_열 if c != "접수번호"},
    )
    with 연결().begin() as conn:
        conn.execute(문장)
    return len(자료)


# ---------- 접수 ----------
접수_열 = ["id", "접수일시", "발견일", "접수자", "부서", "위치", "내용", "처리상태", "접수번호"]


def 접수_추가(발견일, 접수자: str, 부서: str, 위치: str, 내용: str) -> int:
    """접수 한 건을 미처리로 저장하고 id를 돌려준다. 접수일시·처리상태는 DB 기본값."""
    with 연결().begin() as conn:
        return conn.execute(
            접수.insert().values(발견일=발견일, 접수자=접수자 or None, 부서=부서 or None,
                               위치=위치, 내용=내용).returning(접수.c.id)
        ).scalar_one()


def 접수_읽기(처리상태: str | None = None) -> list[dict]:
    """접수를 id 순으로. 처리상태를 주면 그 상태만."""
    문장 = select(접수).order_by(접수.c.id)
    if 처리상태:
        문장 = 문장.where(접수.c.처리상태 == 처리상태)
    with 연결().connect() as conn:
        return [dict(행) for 행 in conn.execute(문장).mappings().all()]


def 접수_처리완료(id: int, 접수번호: str) -> None:
    """접수번호를 적고 처리상태를 처리완료로 바꾼다."""
    with 연결().begin() as conn:
        conn.execute(접수.update().where(접수.c.id == id).values(접수번호=접수번호, 처리상태="처리완료"))


# ---------- 건수 확인 ----------
def 건수() -> dict:
    with 연결().connect() as conn:
        return {t.name: conn.execute(select(func.count()).select_from(t)).scalar_one()
                for t in (접수, 하자대장)}
