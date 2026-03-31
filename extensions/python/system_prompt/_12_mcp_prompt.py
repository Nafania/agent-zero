from helpers.extension import Extension, extensible
from helpers.mcp_handler import MCPConfig
from agent import Agent


class McpPrompt(Extension):

    async def execute(self, **kwargs):
        agent = self.agent
        system_prompt = kwargs.get("system_prompt", [])
        prompt = get_mcp_tools_prompt(agent)
        if prompt:
            system_prompt.append(prompt)


@extensible
def get_mcp_tools_prompt(agent: Agent) -> str:
    mcp_config = MCPConfig.get_instance()
    if mcp_config.servers:
        pre_progress = agent.context.log.progress
        agent.context.log.set_progress("Collecting MCP tools")
        tools = MCPConfig.get_instance().get_tools_prompt()
        agent.context.log.set_progress(pre_progress)
        return tools
    return ""
