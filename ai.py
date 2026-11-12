"""AI 호출은 이 파일에서만 한다. 키와 모델은 .env에서 읽는다.

사용:  python ai.py data/접수함/01_20261102_B1푸드코트_누수.txt
"""
import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

접수정리_지침 = BASE / "지침" / "접수정리.md"
결과_키 = ["접수일", "위치", "공종", "하자내용", "긴급도", "근거"]


def _환경값(이름: str) -> str:
    값 = os.getenv(이름, "").strip()
    if not 값:
        raise RuntimeError(f".env에 {이름} 값이 없습니다.")
    return 값


def _json_꺼내기(글: str) -> dict:
    """AI 답에서 JSON 객체를 꺼낸다. 앞뒤 군더더기가 있어도 첫 { 부터 마지막 } 까지만 읽는다."""
    시작, 끝 = 글.find("{"), 글.rfind("}")
    if 시작 < 0 or 끝 < 시작:
        raise ValueError(f"AI 답에 JSON이 없습니다: {글[:200]}")
    return json.loads(글[시작:끝 + 1])


def 접수정리(원문: str, 파일명: str) -> dict:
    """접수 원문 1건을 읽고 접수일·위치·공종·하자내용·긴급도·근거를 dict로 돌려준다."""
    client = anthropic.Anthropic(api_key=_환경값("ANTHROPIC_API_KEY"))
    지침 = 접수정리_지침.read_text(encoding="utf-8")

    응답 = client.messages.create(
        model=_환경값("MODEL"),
        max_tokens=4000,
        system=지침,
        messages=[{
            "role": "user",
            "content": f"원문 파일명: {파일명}\n\n[접수 원문]\n{원문}",
        }],
    )

    if 응답.stop_reason != "end_turn":
        raise RuntimeError(f"AI가 정상 종료하지 않았습니다: {응답.stop_reason}")
    글 = next((b.text for b in 응답.content if b.type == "text"), "")
    결과 = _json_꺼내기(글)

    빠진 = [k for k in 결과_키 if k not in 결과]
    if 빠진:
        raise ValueError(f"AI 답에 빠진 칸이 있습니다: {빠진}")
    return 결과


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("사용법: python ai.py <접수 원문 파일>")
    경로 = Path(sys.argv[1])
    결과 = 접수정리(경로.read_text(encoding="utf-8"), 경로.name)
    print(json.dumps(결과, ensure_ascii=False, indent=2))
