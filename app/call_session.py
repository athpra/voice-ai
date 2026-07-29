from dataclasses import dataclass, field


@dataclass
class CallSession:
    call_sid: str
    stream_sid: str
    caller_number: str
    customer_context: dict
    history: list[dict] = field(default_factory=list)

    def add_turn(self, role: str, content: str, max_turns: int) -> None:
        self.history.append({"role": role, "content": content})
        max_messages = max_turns * 2
        if len(self.history) > max_messages:
            self.history[:] = self.history[-max_messages:]
            # Keep strict user/assistant alternation: a trim can leave a
            # leading "assistant" message with no user turn before it, which
            # some models (e.g. Mistral) reject outright.
            if self.history and self.history[0]["role"] != "user":
                self.history.pop(0)
