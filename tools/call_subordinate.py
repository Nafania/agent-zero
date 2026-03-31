from agent import Agent, UserMessage
from helpers.tool import Tool, Response
from helpers.print_style import PrintStyle
from initialize import initialize_agent
from extensions.python.hist_add_tool_result import _90_save_tool_call_file as save_tool_call_file

_SAME_PROFILE_STREAK_KEY = "_delegation_same_profile_streak"


class Delegation(Tool):

    async def execute(self, message="", reset="", **kwargs):
        max_depth = getattr(self.agent.config, "max_agent_depth", 5) or 5
        next_depth = self.agent.number + 1
        if next_depth >= max_depth:
            return Response(
                message=f"Delegation refused: agent depth limit reached ({next_depth}/{max_depth}). "
                        "Solve the task directly instead of delegating further.",
                break_loop=False,
            )

        if (
            self.agent.get_data(Agent.DATA_NAME_SUBORDINATE) is None
            or str(reset).lower().strip() == "true"
        ):
            config = initialize_agent()

            agent_profile = kwargs.get("profile", kwargs.get("agent_profile", ""))
            if agent_profile:
                config.profile = agent_profile
            config.max_agent_depth = max_depth

            # same-profile loop detection
            requested_profile = config.profile or "default"
            current_profile = getattr(self.agent.config, "profile", "") or "default"
            streak = (self.agent.get_data(_SAME_PROFILE_STREAK_KEY) or 0)
            if requested_profile == current_profile:
                streak += 1
            else:
                streak = 0
            if streak >= 2:
                PrintStyle.warning(
                    f"Delegation loop warning: profile '{requested_profile}' delegated to itself {streak + 1} times"
                )
                return Response(
                    message=f"Delegation refused: the same agent profile '{requested_profile}' "
                            f"has been delegating to itself repeatedly ({streak + 1} times). "
                            "This indicates a delegation loop. Solve the task directly.",
                    break_loop=False,
                )

            sub = Agent(next_depth, config, self.agent.context)
            sub.set_data(Agent.DATA_NAME_SUPERIOR, self.agent)
            sub.set_data(_SAME_PROFILE_STREAK_KEY, streak)
            self.agent.set_data(Agent.DATA_NAME_SUBORDINATE, sub)

        subordinate: Agent = self.agent.get_data(Agent.DATA_NAME_SUBORDINATE)  # type: ignore
        subordinate.hist_add_user_message(UserMessage(message=message, attachments=[]))

        # run subordinate monologue
        result = await subordinate.monologue()

        # seal the subordinate's current topic so messages move to `topics` for compression
        subordinate.history.new_topic()

        # hint to use includes for long responses
        additional = None
        if len(result) >= save_tool_call_file.LEN_MIN:
            hint = self.agent.read_prompt("fw.hint.call_sub.md")
            if hint:
                additional = {"hint": hint}

        # result
        return Response(message=result, break_loop=False, additional=additional)

    def get_log_object(self):
        return self.agent.context.log.log(
            type="subagent",
            heading=f"icon://communication {self.agent.agent_name}: Calling Subordinate Agent",
            content="",
            kvps=self.args,
        )
