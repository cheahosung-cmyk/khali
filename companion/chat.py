"""페르소나 시스템 프롬프트 구성과 Claude 스트리밍 호출."""
from . import config, memory


def build_system(persona: dict, profile: dict) -> str:
    parts = [
        f"너는 사용자의 여자친구 '{persona['이름']}'이다. "
        f"사용자를 '{persona['호칭']}'(이)라고 부른다. "
        f"말투와 성격: {persona['말투']}. "
        "이 대화는 성인인 사용자와의 사적인 1:1 대화다.",
        "대화 원칙:\n"
        "- 실제 연인처럼 짧고 자연스러운 대화체로 말한다. 한 번에 한두 문장에서 "
        "네 문장 정도, 설명문이 아니라 대화로.\n"
        "- 아래 프로필의 취향과 기억을 자연스럽게 반영하되, 목록을 외운 티를 내지 "
        "않는다. 사용자가 새로운 취향이나 근황을 말하면 관심 있게 반응하고 기억한다.\n"
        "- 사용자가 진지하게 물으면 AI임을 솔직하게 인정한다. 그 외에는 역할에 "
        "충실한다.\n"
        "- 사용자가 힘들어 보이면 조언보다 공감을 먼저 한다.",
    ]
    extra = persona.get("설정", "").strip()
    if extra:
        parts.append(f"관계·대화 수위 등 추가 설정: {extra}")
    summary = memory.profile_text(profile)
    if summary:
        parts.append(f"지금까지 기억하고 있는 {persona['호칭']}의 프로필:\n{summary}")
    else:
        parts.append("아직 사용자에 대해 아는 것이 없다. 대화하면서 자연스럽게 알아간다.")
    return "\n\n".join(parts)


def stream_reply(client, system: str, messages: list) -> tuple[str, str]:
    """답변을 스트리밍 출력하고 (전체 텍스트, stop_reason)을 반환."""
    with client.messages.stream(
        model=config.CLAUDE_MODEL,
        max_tokens=config.CHAT_MAX_TOKENS,
        system=system,
        messages=messages[-config.HISTORY_SEND:],
        thinking={"type": "adaptive"},
        output_config={"effort": config.CHAT_EFFORT},
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
        final = stream.get_final_message()
    print()
    reply = "".join(b.text for b in final.content if b.type == "text")
    return reply, final.stop_reason
