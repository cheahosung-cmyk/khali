"""취향 프로필·대화 기록의 저장/로드와 대화 기반 프로필 갱신."""
import json

from . import config

PROFILE_KEYS = ["좋아하는 것", "싫어하는 것", "관심사", "기억"]

EXTRACT_SYSTEM = (
    "너는 연인 사이의 대화 기록에서 사용자에 대한 정보를 정리하는 도구다. "
    "기존 프로필과 이번 대화를 보고 갱신된 전체 프로필을 반환한다. "
    "이번 대화에서 새로 드러난 취향·관심사·기억할 사실을 추가하고, "
    "중복은 합치고, 대화에서 명백히 바뀐 내용은 수정한다. "
    "각 항목은 한 문장 이내로 짧게 쓴다. 추측은 넣지 않는다. "
    '반환 형식은 {"좋아하는 것": [...], "싫어하는 것": [...], '
    '"관심사": [...], "기억": [...]} 형태의 JSON 하나이며, '
    "JSON 외에는 아무것도 출력하지 않는다."
)

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "좋아하는 것": {"type": "array", "items": {"type": "string"}},
        "싫어하는 것": {"type": "array", "items": {"type": "string"}},
        "관심사": {"type": "array", "items": {"type": "string"}},
        "기억": {"type": "array", "items": {"type": "string"}},
    },
    "required": PROFILE_KEYS,
    "additionalProperties": False,
}


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path, obj):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def empty_profile() -> dict:
    return {k: [] for k in PROFILE_KEYS}


def load_profile() -> dict:
    profile = _load_json(config.PROFILE_PATH, empty_profile())
    return {k: list(profile.get(k, [])) for k in PROFILE_KEYS}


def save_profile(profile: dict):
    _save_json(config.PROFILE_PATH, profile)


def load_history() -> list:
    return _load_json(config.HISTORY_PATH, [])


def save_history(messages: list):
    _save_json(config.HISTORY_PATH, messages[-config.HISTORY_KEEP:])


def load_persona() -> dict | None:
    return _load_json(config.PERSONA_PATH, None)


def save_persona(persona: dict):
    _save_json(config.PERSONA_PATH, persona)


def profile_text(profile: dict) -> str:
    """시스템 프롬프트에 넣을 프로필 요약. 비어 있으면 빈 문자열."""
    lines = []
    for key in PROFILE_KEYS:
        items = [s for s in profile.get(key, []) if s.strip()]
        if items:
            lines.append(f"[{key}]\n" + "\n".join(f"- {s}" for s in items))
    return "\n\n".join(lines)


def _normalize(profile: dict) -> dict:
    """빈 항목 제거·중복 제거·개수 제한."""
    out = {}
    for key in PROFILE_KEYS:
        seen, items = set(), []
        for s in profile.get(key, []):
            s = str(s).strip()
            if s and s not in seen:
                seen.add(s)
                items.append(s)
        out[key] = items[-config.LIST_CAP:]
    return out


def update_profile(provider, profile: dict, session_messages: list) -> dict:
    """세션 대화에서 취향을 추출해 갱신된 프로필을 반환. 실패 시 기존 프로필 유지."""
    transcript = "\n".join(
        f"{'사용자' if m['role'] == 'user' else '그녀'}: {m['content']}"
        for m in session_messages
    )
    prompt = (
        "기존 프로필:\n"
        f"{json.dumps(profile, ensure_ascii=False)}\n\n"
        "이번 대화:\n"
        f"{transcript}\n\n"
        "갱신된 전체 프로필을 반환해라."
    )
    text = provider.extract_json(EXTRACT_SYSTEM, prompt, EXTRACT_SCHEMA)
    if not text:
        return profile
    try:
        return _normalize(json.loads(text))
    except json.JSONDecodeError:
        return profile
