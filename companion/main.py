"""1:1 맞춤형 컴패니언 대화 CLI.

사용법(무료):
    export GEMINI_API_KEY=...   # https://aistudio.google.com 에서 무료 발급
    python -m companion.main
자세한 백엔드 선택은 README 참고.
"""
import sys

from . import chat, config, memory, providers

EXIT_WORDS = {"/bye", "/잘자", "exit", "quit", "종료"}

HELP = """명령어:
  /프로필           지금까지 기억한 취향·사실 보기
  /기억 <내용>       바로 기억시키기 (예: /기억 민트초코 싫어함)
  /초기화           프로필과 대화 기록 전부 삭제
  /잘자 (또는 /bye)  대화를 정리하고 종료
이름·말투·수위 설정을 바꾸려면 data/companion/persona.json을 수정하세요.
그 외에는 그냥 평소처럼 말을 걸면 됩니다."""


def _input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        raise KeyboardInterrupt from None


def setup_persona() -> dict:
    print("처음이네요. 그녀를 소개해 주세요. (그냥 Enter를 치면 기본값)")
    name = _input("이름 [예린]: ") or "예린"
    calling = _input(f"{name}(이)가 당신을 부를 호칭 [자기야]: ") or "자기야"
    style = _input("말투/성격 [다정하고 장난기 있는 반말]: ") or "다정하고 장난기 있는 반말"
    extra = _input("관계·대화 수위 등 추가 설정 (선택, 자유롭게): ")
    persona = {"이름": name, "호칭": calling, "말투": style, "설정": extra}
    memory.save_persona(persona)
    return persona


def show_profile(profile: dict):
    summary = memory.profile_text(profile)
    print(summary if summary else "아직 기억하고 있는 게 없어요. 대화하면서 채워집니다.")


def finish_session(provider, profile: dict, history: list, session_messages: list) -> dict:
    """세션 대화에서 취향을 학습하고 기록을 저장."""
    memory.save_history(history)
    if len(session_messages) >= 2:
        print("(오늘 대화를 기억해 두는 중...)")
        try:
            profile = memory.update_profile(provider, profile, session_messages)
            memory.save_profile(profile)
        except Exception as err:  # noqa: BLE001 - 학습 실패로 종료를 막지 않는다
            print(f"[warn] 취향 학습 실패: {err}")
    return profile


def run(provider, persona: dict, profile: dict, history: list):
    session_messages = []  # 이번 세션에서 오간 메시지(취향 학습용)
    print(f"\n{persona['이름']}(와)과 대화를 시작합니다. 백엔드: {provider.name}, 명령어: /help\n")
    try:
        while True:
            user = _input("나: ")
            if not user:
                continue
            low = user.lower()
            if low in EXIT_WORDS:
                break
            if low in ("/help", "/도움말"):
                print(HELP)
                continue
            if low in ("/프로필", "/profile"):
                show_profile(profile)
                continue
            if user.startswith(("/기억 ", "/remember ")):
                fact = user.split(" ", 1)[1].strip()
                if fact:
                    profile["기억"].append(fact)
                    memory.save_profile(profile)
                    print("(기억했어요)")
                continue
            if low in ("/초기화", "/reset"):
                if _input("프로필과 대화 기록을 전부 지울까요? [y/N]: ").lower() == "y":
                    profile = memory.empty_profile()
                    history.clear()
                    memory.save_profile(profile)
                    memory.save_history(history)
                    print("(전부 지웠어요. 처음부터 다시 시작합니다)")
                continue

            history.append({"role": "user", "content": user})
            session_messages.append({"role": "user", "content": user})
            print(f"{persona['이름']}: ", end="", flush=True)
            try:
                system = chat.build_system(persona, profile)
                reply, refused = provider.chat(system, history[-config.HISTORY_SEND:])
            except Exception as err:  # noqa: BLE001
                print(f"\n[warn] 응답 실패: {_friendly_error(err)}")
                history.pop()  # 실패한 턴은 기록에서 제거
                session_messages.pop()
                continue
            if refused:
                print(f"{persona['이름']}: 음… 그 얘기는 좀 그래. 다른 얘기 하자!")
                history.pop()
                session_messages.pop()
                continue
            history.append({"role": "assistant", "content": reply})
            session_messages.append({"role": "assistant", "content": reply})
            memory.save_history(history)
    except KeyboardInterrupt:
        print()
    profile = finish_session(provider, profile, history, session_messages)
    print(f"{persona['이름']}: 잘 가! 또 얘기하자 :)")


def _friendly_error(err) -> str:
    import requests

    if isinstance(err, TypeError) and "authentication" in str(err).lower():
        return "인증 정보가 없습니다. API 키 환경변수를 확인하세요."
    try:
        import anthropic
        if isinstance(err, anthropic.AuthenticationError):
            return "API 키가 올바르지 않습니다. ANTHROPIC_API_KEY를 확인하세요."
        if isinstance(err, anthropic.RateLimitError):
            return "요청이 너무 잦습니다. 잠시 후 다시 말을 걸어 보세요."
        if isinstance(err, anthropic.APIConnectionError):
            return "네트워크 연결에 실패했습니다."
        if isinstance(err, anthropic.APIStatusError):
            return f"API 오류({err.status_code}): {err.message}"
    except ImportError:
        pass
    if isinstance(err, requests.HTTPError):
        code = err.response.status_code if err.response is not None else "?"
        if code == 429:
            return "요청 한도에 걸렸습니다(무료 티어). 잠시 후 다시 말을 걸어 보세요."
        return f"API 오류({code})"
    if isinstance(err, requests.RequestException):
        return "서버에 연결하지 못했습니다. 네트워크(또는 Ollama 실행 여부)를 확인하세요."
    return str(err)


def main():
    provider = providers.make_provider()
    try:
        persona = memory.load_persona() or setup_persona()
    except KeyboardInterrupt:
        print("\n종료합니다.")
        return
    profile = memory.load_profile()
    history = memory.load_history()
    run(provider, persona, profile, history)


if __name__ == "__main__":
    sys.exit(main())
