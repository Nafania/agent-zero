import asyncio, random, string, threading, time
import nest_asyncio2

nest_asyncio2.apply()

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Coroutine, Dict, Literal
from enum import Enum
import models

from helpers import (
    extract_tools,
    files,
    errors,
    history,
    tokens,
    context as context_helper,
    dirty_json,
    subagents
)
from helpers.print_style import PrintStyle

from langchain_core.prompts import (
    ChatPromptTemplate,
)
from langchain_core.messages import SystemMessage, BaseMessage

import helpers.log as Log
from helpers.dirty_json import DirtyJson
from helpers.defer import DeferredTask
from typing import Callable
from helpers.localization import Localization
from helpers.extension import call_extensions, extensible
from helpers.errors import RepairableException


class AgentContextType(Enum):
    USER = "user"
    TASK = "task"
    BACKGROUND = "background"


class AgentContext:

    _contexts: dict[str, "AgentContext"] = {}
    _contexts_lock = threading.RLock()
    _counter: int = 0
    _notification_manager = None

    @extensible
    def __init__(
        self,
        config: "AgentConfig",
        id: str | None = None,
        name: str | None = None,
        agent0: "Agent|None" = None,
        log: Log.Log | None = None,
        paused: bool = False,
        streaming_agent: "Agent|None" = None,
        created_at: datetime | None = None,
        type: AgentContextType = AgentContextType.USER,
        last_message: datetime | None = None,
        data: dict | None = None,
        output_data: dict | None = None,
        set_current: bool = False,
    ):
        # initialize context
        self.id = id or AgentContext.generate_id()
        existing = None
        with AgentContext._contexts_lock:
            existing = AgentContext._contexts.get(self.id, None)
            if existing:
                AgentContext._contexts.pop(self.id, None)
            AgentContext._contexts[self.id] = self
        if existing and existing.task:
            existing.task.kill(terminate_thread=True)
        if set_current:
            AgentContext.set_current(self.id)

        # initialize state
        self.name = name
        self.config = config
        self.data = data or {}
        self.output_data = output_data or {}
        self.log = log or Log.Log()
        self.log.context = self
        self.paused = paused
        self._streaming_agent = streaming_agent
        self.task: DeferredTask | None = None
        self.created_at = created_at or datetime.now(timezone.utc)
        self.type = type
        AgentContext._counter += 1
        self.no = AgentContext._counter
        self.last_message = last_message or datetime.now(timezone.utc)

        # Lazy deserialization support: these are set by persist_chat._deserialize_context
        # when loading from disk to defer the expensive agent/history deserialization.
        self._raw_agents: list | None = None
        self._raw_streaming_agent_no: int = 0

        # initialize agent at last (context is complete now)
        self._agent0 = agent0 or Agent(0, self.config, self)

    @property
    def agent0(self):
        self._ensure_hydrated()
        return self._agent0

    @agent0.setter
    def agent0(self, value):
        self._agent0 = value

    @property
    def streaming_agent(self):
        self._ensure_hydrated()
        return self._streaming_agent

    @streaming_agent.setter
    def streaming_agent(self, value):
        self._streaming_agent = value

    @staticmethod
    def get(id: str):
        with AgentContext._contexts_lock:
            return AgentContext._contexts.get(id, None)

    @staticmethod
    def use(id: str):
        context = AgentContext.get(id)
        if context:
            AgentContext.set_current(id)
        else:
            AgentContext.set_current("")
        return context

    @staticmethod
    def current():
        ctxid = context_helper.get_context_data("agent_context_id", "")
        if not ctxid:
            return None
        return AgentContext.get(ctxid)

    @staticmethod
    def set_current(ctxid: str):
        context_helper.set_context_data("agent_context_id", ctxid)

    @staticmethod
    def first():
        with AgentContext._contexts_lock:
            if not AgentContext._contexts:
                return None
            return list(AgentContext._contexts.values())[0]

    @staticmethod
    def all():
        with AgentContext._contexts_lock:
            return list(AgentContext._contexts.values())

    @staticmethod
    def generate_id():
        def generate_short_id():
            return "".join(random.choices(string.ascii_letters + string.digits, k=8))

        while True:
            short_id = generate_short_id()
            with AgentContext._contexts_lock:
                if short_id not in AgentContext._contexts:
                    return short_id

    @classmethod
    def get_notification_manager(cls):
        if cls._notification_manager is None:
            from helpers.notification import NotificationManager  # type: ignore

            cls._notification_manager = NotificationManager()
        return cls._notification_manager

    @staticmethod
    @extensible
    def remove(id: str):
        with AgentContext._contexts_lock:
            context = AgentContext._contexts.pop(id, None)
        if context and context.task:
            context.task.kill(terminate_thread=True)
        return context

    def get_data(self, key: str, recursive: bool = True):
        # recursive is not used now, prepared for context hierarchy
        return self.data.get(key, None)

    def set_data(self, key: str, value: Any, recursive: bool = True):
        # recursive is not used now, prepared for context hierarchy
        self.data[key] = value

    def get_output_data(self, key: str, recursive: bool = True):
        # recursive is not used now, prepared for context hierarchy
        return self.output_data.get(key, None)

    def set_output_data(self, key: str, value: Any, recursive: bool = True):
        # recursive is not used now, prepared for context hierarchy
        self.output_data[key] = value

    @extensible
    def output(self):
        return {
            "id": self.id,
            "name": self.name,
            "created_at": (
                Localization.get().serialize_datetime(self.created_at)
                if self.created_at
                else Localization.get().serialize_datetime(datetime.fromtimestamp(0))
            ),
            "no": self.no,
            "log_guid": self.log.guid,
            "log_version": len(self.log.updates),
            "log_length": len(self.log.logs),
            "paused": self.paused,
            "last_message": (
                Localization.get().serialize_datetime(self.last_message)
                if self.last_message
                else Localization.get().serialize_datetime(datetime.fromtimestamp(0))
            ),
            "type": self.type.value,
            "running": self.is_running(),
            **self.output_data,
        }

    @staticmethod
    def log_to_all(
        type: Log.Type,
        heading: str | None = None,
        content: str | None = None,
        kvps: dict | None = None,
        update_progress: Log.ProgressUpdate | None = None,
        id: str | None = None,  # Add id parameter
        **kwargs,
    ) -> list[Log.LogItem]:
        items: list[Log.LogItem] = []
        for context in AgentContext.all():
            items.append(
                context.log.log(
                    type, heading, content, kvps, update_progress, id, **kwargs
                )
            )
        return items

    @extensible
    def kill_process(self):
        if self.task:
            self.task.kill()

    @extensible
    def reset(self):
        self.kill_process()
        self.log.reset()
        self.agent0 = Agent(0, self.config, self)
        self.streaming_agent = None
        self.paused = False

    @extensible
    def nudge(self):
        self.kill_process()
        self.paused = False
        self.task = self.communicate(UserMessage(self.agent0.read_prompt("fw.msg_nudge.md")))
        return self.task

    def _ensure_hydrated(self):
        """Ensure agents and history are fully deserialized (lazy hydration)."""
        if self._raw_agents is not None:
            from helpers.persist_chat import hydrate_context_agents
            hydrate_context_agents(self)

    @extensible
    def get_agent(self):
        return self.streaming_agent or self.agent0

    def is_running(self) -> bool:
        return (self.task and self.task.is_alive()) or False

    @extensible
    def communicate(self, msg: "UserMessage", broadcast_level: int = 1):
        self.paused = False  # unpause if paused

        current_agent = self.get_agent()

        if self.task and self.task.is_alive():
            # set intervention messages to agent(s):
            intervention_agent = current_agent
            while intervention_agent and broadcast_level != 0:
                intervention_agent.intervention = msg
                broadcast_level -= 1
                intervention_agent = intervention_agent.data.get(
                    Agent.DATA_NAME_SUPERIOR, None
                )
        else:
            self.task = self.run_task(self._process_chain, current_agent, msg)

        return self.task

    @extensible
    def run_task(
        self, func: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any
    ):
        if not self.task:
            self.task = DeferredTask(
                thread_name=f"AgentCtx-{self.id}",
            )
        self.task.start_task(func, *args, **kwargs)
        return self.task

    @extensible
    async def handle_exception(self, location: str, exception: Exception):
        if exception:
            raise exception

    # this wrapper ensures that superior agents are called back if the chat was loaded from file and original callstack is gone
    @extensible
    async def _process_chain(self, agent: "Agent", msg: "UserMessage|str", user=True):
        try:
            msg_template = (
                agent.hist_add_user_message(msg)  # type: ignore
                if user
                else agent.hist_add_tool_result(
                    tool_name="call_subordinate", tool_result=msg  # type: ignore
                )
            )
            response = await agent.monologue()  # type: ignore
            superior = agent.data.get(Agent.DATA_NAME_SUPERIOR, None)
            if superior:
                response = await self._process_chain(superior, response, False)  # type: ignore

            # call end of process extensions
            await self.get_agent().call_extensions("process_chain_end", data={})

            return response
        except Exception as e:
            await self.handle_exception("process_chain", e)
        finally:
            if user:
                from helpers.state_snapshot import touch_chat_list
                from helpers.state_monitor_integration import mark_dirty_all
                touch_chat_list()
                mark_dirty_all(reason="process_chain_end")


@dataclass
class AgentConfig:
    mcp_servers: str
    profile: str = ""
    knowledge_subdirs: list[str] = field(default_factory=lambda: ["default", "custom"])
    additional: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserMessage:
    message: str
    attachments: list[str] = field(default_factory=list[str])
    system_message: list[str] = field(default_factory=list[str])


class LoopData:
    @extensible
    def __init__(self, **kwargs):
        self.iteration = -1
        self.system = []
        self.user_message: history.Message | None = None
        self.history_output: list[history.OutputMessage] = []
        self.extras_temporary: OrderedDict[str, history.MessageContent] = OrderedDict()
        self.extras_persistent: OrderedDict[str, history.MessageContent] = OrderedDict()
        self.last_response = ""
        self.params_temporary: dict = {}
        self.params_persistent: dict = {}
        self.current_tool = None

        # override values with kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)


# intervention exception class - skips rest of message loop iteration
class InterventionException(Exception):
    pass


# killer exception class - not forwarded to LLM, cannot be fixed on its own, ends message loop


class HandledException(Exception):
    pass


class Agent:

    DATA_NAME_SUPERIOR = "_superior"
    DATA_NAME_SUBORDINATE = "_subordinate"
    DATA_NAME_CTX_WINDOW = "ctx_window"

    @extensible
    def __init__(
        self, number: int, config: AgentConfig, context: AgentContext | None = None
    ):

        # agent config
        self.config = config

        # agent context
        self.context = context or AgentContext(config=config, agent0=self)

        # non-config vars
        self.number = number
        self.agent_name = f"A{self.number}"

        self.history = history.History(self)  # type: ignore[abstract]
        self.last_user_message: history.Message | None = None
        self.intervention: UserMessage | None = None
        self.data: dict[str, Any] = {}  # free data object all the tools can use

        asyncio.run(self.call_extensions("agent_init"))

    @extensible
    async def monologue(self):
        error_retries = 0  # counter for critical error retries
        duplicate_retries = 0  # counter for duplicate response retries
        while True:
            try:
                # loop data dictionary to pass to extensions
                self.loop_data = LoopData(user_message=self.last_user_message)
                # call monologue_start extensions
                await self.call_extensions("monologue_start", loop_data=self.loop_data)

                printer = PrintStyle(italic=True, font_color="#b3ffd9", padding=False)

                # let the agent run message loop until he stops it with a response tool
                while True:

                    self.context.streaming_agent = self  # mark self as current streamer
                    self.loop_data.iteration += 1
                    self.loop_data.params_temporary = {}  # clear temporary params

                    # call message_loop_start extensions
                    await self.call_extensions(
                        "message_loop_start", loop_data=self.loop_data
                    )
                    await self.handle_intervention()

                    loop_exception = None
                    try:
                        # prepare LLM chain (model, system, history)
                        prompt = await self.prepare_prompt(loop_data=self.loop_data)

                        # call before_main_llm_call extensions
                        await self.call_extensions(
                            "before_main_llm_call", loop_data=self.loop_data
                        )
                        await self.handle_intervention()


                        async def reasoning_callback(chunk: str, full: str):
                            await self.handle_intervention()
                            if chunk == full:
                                printer.print("Reasoning: ")  # start of reasoning
                            # Pass chunk and full data to extensions for processing
                            stream_data = {"chunk": chunk, "full": full}
                            await self.call_extensions(
                                "reasoning_stream_chunk",
                                loop_data=self.loop_data,
                                stream_data=stream_data,
                            )
                            # Stream masked chunk after extensions processed it
                            if stream_data.get("chunk"):
                                printer.stream(stream_data["chunk"])
                            # Use the potentially modified full text for downstream processing
                            await self.handle_reasoning_stream(stream_data["full"])

                        async def stream_callback(chunk: str, full: str):
                            await self.handle_intervention()
                            # output the agent response stream
                            if chunk == full:
                                printer.print("Response: ")  # start of response
                            # Pass chunk and full data to extensions for processing
                            stream_data = {"chunk": chunk, "full": full}
                            await self.call_extensions(
                                "response_stream_chunk",
                                loop_data=self.loop_data,
                                stream_data=stream_data,
                            )
                            # Stream masked chunk after extensions processed it
                            if stream_data.get("chunk"):
                                printer.stream(stream_data["chunk"])
                            # Use the potentially modified full text for downstream processing
                            await self.handle_response_stream(stream_data["full"])

                        # call main LLM
                        agent_response, _reasoning = await self.call_chat_model(
                            messages=prompt,
                            response_callback=stream_callback,
                            reasoning_callback=reasoning_callback,
                        )
                        await self.handle_intervention(agent_response)

                        # Notify extensions to finalize their stream filters
                        await self.call_extensions(
                            "reasoning_stream_end", loop_data=self.loop_data
                        )
                        await self.handle_intervention(agent_response)

                        await self.call_extensions(
                            "response_stream_end", loop_data=self.loop_data
                        )

                        await self.handle_intervention(agent_response)

                        if (
                            self.loop_data.last_response == agent_response
                        ):  # if assistant_response is the same as last message in history, let him know
                            duplicate_retries += 1

                            if duplicate_retries >= 3:
                                from helpers.errors import HandledException
                                error_msg = "Agent stuck in duplicate response loop (3 consecutive identical responses). Breaking loop."
                                PrintStyle(font_color="red", padding=True).print(error_msg)
                                self.context.log.log(type="error", content=error_msg)
                                raise HandledException(Exception(error_msg))

                            # Append the assistant's response to the history
                            self.hist_add_ai_response(agent_response)
                            # Append warning message to the history
                            warning_msg = self.read_prompt("fw.msg_repeat.md")
                            self.hist_add_warning(message=warning_msg)
                            PrintStyle(font_color="orange", padding=True).print(
                                warning_msg
                            )
                            self.context.log.log(type="warning", content=warning_msg)

                        else:  # otherwise proceed with tool
                            # Append the assistant's response to the history
                            self.hist_add_ai_response(agent_response)
                            # process tools requested in agent message
                            tools_result = await self.process_tools(agent_response)
                            if tools_result:  # final response of message loop available
                                return tools_result  # break the execution if the task is done

                        error_retries = 0  # reset retry counter on successful iteration
                        duplicate_retries = 0  # reset duplicate counter on successful iteration

                    # exceptions inside message loop:
                    except InterventionException as e:
                        error_retries = 0  # reset retry counter on user intervention
                        pass  # intervention message has been handled in handle_intervention(), proceed with conversation loop
                    except RepairableException as e:
                        # Forward repairable errors to the LLM, maybe it can fix them
                        msg = {"message": errors.format_error(e)}
                        await self.call_extensions("error_format", msg=msg)
                        self.hist_add_warning(msg["message"])
                        PrintStyle(font_color="red", padding=True).print(msg["message"])
                        self.context.log.log(type="warning", content=msg["message"])
                    except Exception as e:
                        loop_exception = e
                        # Retry critical exceptions before failing
                        error_retries = await self.retry_critical_exception(
                            e, error_retries
                        )

                    finally:
                        if self.context.task and self.context.task.is_alive():
                            await self.call_extensions(
                                "message_loop_end", loop_data=self.loop_data, exception=loop_exception
                            )
                        loop_exception = None

            # exceptions outside message loop:
            except InterventionException as e:
                error_retries = 0  # reset retry counter on user intervention
                pass  # just start over
            except Exception as e:
                # Retry critical exceptions before failing
                error_retries = await self.retry_critical_exception(
                    e, error_retries
                )
            finally:
                self.context.streaming_agent = None  # unset current streamer
                # call monologue_end extensions
                if self.context.task and self.context.task.is_alive(): # don't call extensions post mortem
                    await self.call_extensions("monologue_end", loop_data=self.loop_data)  # type: ignore

    @extensible
    async def prepare_prompt(self, loop_data: LoopData) -> list[BaseMessage]:
        self.context.log.set_progress("Building prompt")

        # call extensions before setting prompts
        await self.call_extensions("message_loop_prompts_before", loop_data=loop_data)

        # set system prompt and message history
        loop_data.system = await self.get_system_prompt(self.loop_data)
        loop_data.history_output = self.history.output()

        # and allow extensions to edit them
        await self.call_extensions("message_loop_prompts_after", loop_data=loop_data)

        # concatenate system prompt
        system_text = "\n\n".join(loop_data.system)

        # join extras
        extras = history.Message(  # type: ignore[abstract]
            False,
            content=self.read_prompt(
                "agent.context.extras.md",
                extras=dirty_json.stringify(
                    {**loop_data.extras_persistent, **loop_data.extras_temporary}
                ),
            ),
        ).output()
        loop_data.extras_temporary.clear()

        # convert history + extras to LLM format
        history_langchain: list[BaseMessage] = history.output_langchain(
            loop_data.history_output + extras
        )

        # build full prompt from system prompt, message history and extrS
        full_prompt: list[BaseMessage] = [
            SystemMessage(content=system_text),
            *history_langchain,
        ]
        full_text = ChatPromptTemplate.from_messages(full_prompt).format()

        # store as last context window content
        self.set_data(
            Agent.DATA_NAME_CTX_WINDOW,
            {
                "text": full_text,
                "tokens": tokens.approximate_tokens(full_text),
            },
        )

        return full_prompt

    async def retry_critical_exception(
        self, e: Exception, error_retries: int, delay: int = 3, max_retries: int = 1
    ) -> int:
        if error_retries >= max_retries:
            self.handle_critical_exception(e)

        error_message = errors.format_error(e)
        
        self.context.log.log(
            type="warning", heading="Critical error occurred, retrying...", content=error_message
        )
        PrintStyle(font_color="orange", padding=True).print(
            "Critical error occurred, retrying..."
        )
        await asyncio.sleep(delay)
        await self.handle_intervention()
        agent_facing_error = self.read_prompt(
            "fw.msg_critical_error.md", error_message=error_message
        )
        self.hist_add_warning(message=agent_facing_error)
        PrintStyle(font_color="orange", padding=True).print(
            agent_facing_error
        )
        return error_retries + 1

    @extensible
    async def handle_exception(self, location: str, exception: Exception):
        if exception:
            raise exception

    def handle_critical_exception(self, exception: Exception):
        if isinstance(exception, HandledException):
            raise exception  # Re-raise the exception to kill the loop
        elif isinstance(exception, asyncio.CancelledError):
            # Handling for asyncio.CancelledError
            PrintStyle(font_color="white", background_color="red", padding=True).print(
                f"Context {self.context.id} terminated during message loop"
            )
            raise HandledException(
                exception
            )  # Re-raise the exception to cancel the loop
        else:
            # Handling for general exceptions
            error_text = errors.error_text(exception)
            error_message = errors.format_error(exception)

            # Mask secrets in error messages
            PrintStyle(font_color="red", padding=True).print(error_message)
            self.context.log.log(
                type="error",
                content=error_message,
            )
            PrintStyle(font_color="red", padding=True).print(
                f"{self.agent_name}: {error_text}"
            )

            raise HandledException(exception)  # Re-raise the exception to kill the loop

    @extensible
    async def get_system_prompt(self, loop_data: LoopData) -> list[str]:
        system_prompt: list[str] = []
        await self.call_extensions(
            "system_prompt", system_prompt=system_prompt, loop_data=loop_data
        )
        return system_prompt

    @extensible
    def parse_prompt(self, _prompt_file: str, **kwargs):
        dirs = subagents.get_paths(self, "prompts")
        prompt = files.parse_file(
            _prompt_file, _directories=dirs, _agent=self, **kwargs
        )
        return prompt

    @extensible
    def read_prompt(self, file: str, **kwargs) -> str:
        dirs = subagents.get_paths(self, "prompts")
        prompt = files.read_prompt_file(file, _directories=dirs, _agent=self, **kwargs)
        if files.is_full_json_template(prompt):
            prompt = files.remove_code_fences(prompt)
        return prompt

    def get_data(self, field: str):
        return self.data.get(field, None)

    def set_data(self, field: str, value):
        self.data[field] = value

    _last_msg_touch: float = 0.0
    _MSG_TOUCH_INTERVAL: float = 5.0

    @extensible
    def hist_add_message(
        self, ai: bool, content: history.MessageContent, tokens: int = 0
    ):
        now = datetime.now(timezone.utc)
        self.last_message = now
        self.context.last_message = now
        now_mono = time.time()
        if now_mono - Agent._last_msg_touch >= Agent._MSG_TOUCH_INTERVAL:
            Agent._last_msg_touch = now_mono
            from helpers.state_snapshot import touch_chat_list
            touch_chat_list()
        # Allow extensions to process content before adding to history
        content_data = {"content": content}
        asyncio.run(
            self.call_extensions("hist_add_before", content_data=content_data, ai=ai)
        )
        return self.history.add_message(
            ai=ai, content=content_data["content"], tokens=tokens
        )

    @extensible
    def hist_add_user_message(self, message: UserMessage, intervention: bool = False):
        self.history.new_topic()  # user message starts a new topic in history

        # load message template based on intervention
        if intervention:
            content = self.parse_prompt(
                "fw.intervention.md",
                message=message.message,
                attachments=message.attachments,
                system_message=message.system_message,
            )
        else:
            content = self.parse_prompt(
                "fw.user_message.md",
                message=message.message,
                attachments=message.attachments,
                system_message=message.system_message,
            )

        # remove empty parts from template
        if isinstance(content, dict):
            content = {k: v for k, v in content.items() if v}

        # add to history
        msg = self.hist_add_message(False, content=content)  # type: ignore
        self.last_user_message = msg
        return msg

    @extensible
    def hist_add_ai_response(self, message: str):
        self.loop_data.last_response = message
        content = self.parse_prompt("fw.ai_response.md", message=message)
        return self.hist_add_message(True, content=content)

    @extensible
    def hist_add_warning(self, message: history.MessageContent):
        content = self.parse_prompt("fw.warning.md", message=message)
        return self.hist_add_message(False, content=content)

    @extensible
    def hist_add_tool_result(self, tool_name: str, tool_result: str, **kwargs):
        data = {
            "tool_name": tool_name,
            "tool_result": tool_result,
            **kwargs,
        }
        asyncio.run(self.call_extensions("hist_add_tool_result", data=data))
        return self.hist_add_message(False, content=data)

    def concat_messages(
        self, messages
    ):  # TODO add param for message range, topic, history
        return self.history.output_text(human_label="user", ai_label="assistant")

    @extensible
    def get_chat_model(self):
        return None

    @extensible
    def get_utility_model(self):
        return None

    @extensible
    def get_browser_model(self):
        return None

    @extensible
    def get_embedding_model(self):
        return None

    @extensible
    async def call_utility_model(
        self,
        system: str,
        message: str,
        callback: Callable[[str], Awaitable[None]] | None = None,
        background: bool = False,
    ):
        model = self.get_utility_model()

        # call extensions
        call_data = {
            "model": model,
            "system": system,
            "message": message,
            "callback": callback,
            "background": background,
        }
        await self.call_extensions("util_model_call_before", call_data=call_data)

        # propagate stream to callback if set
        async def stream_callback(chunk: str, total: str):
            if call_data["callback"]:
                await call_data["callback"](chunk)

        response, _reasoning = await call_data["model"].unified_call(
            system_message=call_data["system"],
            user_message=call_data["message"],
            response_callback=stream_callback if call_data["callback"] else None,
            rate_limiter_callback=(
                self.rate_limiter_callback if not call_data["background"] else None
            ),
            _metrics_context=self._build_metrics_context("utility"),
        )

        return response

    @extensible
    async def call_chat_model(
        self,
        messages: list[BaseMessage],
        response_callback: Callable[[str, str], Awaitable[None]] | None = None,
        reasoning_callback: Callable[[str, str], Awaitable[None]] | None = None,
        background: bool = False,
        explicit_caching: bool = True,
    ):
        response = ""

        # model class
        model = self.get_chat_model()

        # call model
        response, reasoning = await model.unified_call(
            messages=messages,
            reasoning_callback=reasoning_callback,
            response_callback=response_callback,
            rate_limiter_callback=(
                self.rate_limiter_callback if not background else None
            ),
            explicit_caching=explicit_caching,
            _metrics_context=self._build_metrics_context("chat"),
        )

        return response, reasoning

    def _build_metrics_context(self, usage_type: str) -> dict:
        project = self.context.data.get("project")
        return {
            "usage_type": usage_type,
            "agent_name": self.agent_name,
            "context_id": self.context.id,
            "project": project,
            "chat_name": self.context.name,
        }

    @extensible
    async def rate_limiter_callback(
        self, message: str, key: str, total: int, limit: int
    ):
        # show the rate limit waiting in a progress bar, no need to spam the chat history
        self.context.log.set_progress(message, True)
        return False

    @extensible
    async def handle_intervention(self, progress: str = ""):
        while self.context.paused:
            await asyncio.sleep(0.1)  # wait if paused
        if (
            self.intervention
        ):  # if there is an intervention message, but not yet processed
            msg = self.intervention
            self.intervention = None  # reset the intervention message
            # If a tool was running, save its progress to history
            last_tool = self.loop_data.current_tool
            if last_tool:
                tool_progress = last_tool.progress.strip()
                if tool_progress:
                    self.hist_add_tool_result(last_tool.name, tool_progress)
                    last_tool.set_progress(None)
            if progress.strip():
                self.hist_add_ai_response(progress)
            # append the intervention message
            self.hist_add_user_message(msg, intervention=True)
            raise InterventionException(msg)

    async def wait_if_paused(self):
        while self.context.paused:
            await asyncio.sleep(0.1)

    @extensible
    async def validate_tool_request(self, tool_request: Any):
        if not isinstance(tool_request, dict):
            raise ValueError("Tool request must be a dictionary")
        if not tool_request.get("tool_name") or not isinstance(tool_request.get("tool_name"), str):
            raise ValueError("Tool request must have a tool_name (type string) field")
        if "tool_args" not in tool_request or not isinstance(tool_request.get("tool_args"), dict):
            raise ValueError("Tool request must have a tool_args (type dictionary) field")

    @extensible
    async def process_tools(self, msg: str):
        # search for tool usage requests in agent message
        tool_request = extract_tools.json_parse_dirty(msg)

        if tool_request is not None:
            await self.validate_tool_request(tool_request)

            raw_tool_name = tool_request.get("tool_name", tool_request.get("tool",""))  # Get the raw tool name
            tool_args = tool_request.get("tool_args", tool_request.get("args", {}))

            tool_name = raw_tool_name  # Initialize tool_name with raw_tool_name
            tool_method = None  # Initialize tool_method

            # Split raw_tool_name into tool_name and tool_method if applicable
            if ":" in raw_tool_name:
                tool_name, tool_method = raw_tool_name.split(":", 1)

            tool = None  # Initialize tool to None

            # Try getting tool from MCP first
            try:
                import helpers.mcp_handler as mcp_helper

                mcp_tool_candidate = mcp_helper.MCPConfig.get_instance().get_tool(
                    self, tool_name
                )
                if mcp_tool_candidate:
                    tool = mcp_tool_candidate
            except ImportError:
                PrintStyle(
                    background_color="black", font_color="yellow", padding=True
                ).print("MCP helper module not found. Skipping MCP tool lookup.")
            except Exception as e:
                PrintStyle(
                    background_color="black", font_color="red", padding=True
                ).print(f"Failed to get MCP tool '{tool_name}': {e}")

            # Fallback to local get_tool if MCP tool was not found or MCP lookup failed
            if not tool:
                tool = self.get_tool(
                    name=tool_name,
                    method=tool_method,
                    args=tool_args,
                    message=msg,
                    loop_data=self.loop_data,
                )

            if tool:
                self.loop_data.current_tool = tool  # type: ignore
                try:
                    await self.handle_intervention()

                    # Call tool hooks for compatibility
                    await tool.before_execution(**tool_args)
                    await self.handle_intervention()

                    # Allow extensions to preprocess tool arguments
                    await self.call_extensions(
                        "tool_execute_before",
                        tool_args=tool_args or {},
                        tool_name=tool_name,
                    )

                    response = await tool.execute(**tool_args)
                    await self.handle_intervention()

                    # Allow extensions to postprocess tool response
                    await self.call_extensions(
                        "tool_execute_after", response=response, tool_name=tool_name
                    )

                    await tool.after_execution(response)
                    await self.handle_intervention()

                    if response.break_loop:
                        return response.message
                finally:
                    self.loop_data.current_tool = None
            else:
                error_detail = (
                    f"Tool '{raw_tool_name}' not found or could not be initialized."
                )
                self.hist_add_warning(error_detail)
                PrintStyle(font_color="red", padding=True).print(error_detail)
                self.context.log.log(
                    type="warning", content=f"{self.agent_name}: {error_detail}"
                )
        else:
            warning_msg_misformat = self.read_prompt("fw.msg_misformat.md")
            self.hist_add_warning(warning_msg_misformat)
            PrintStyle(font_color="red", padding=True).print(warning_msg_misformat)
            self.context.log.log(
                type="warning",
                content=f"{self.agent_name}: Message misformat, no valid tool request found.",
            )

    async def handle_reasoning_stream(self, stream: str):
        await self.handle_intervention()
        await self.call_extensions(
            "reasoning_stream",
            loop_data=self.loop_data,
            text=stream,
        )

    async def handle_response_stream(self, stream: str):
        await self.handle_intervention()
        try:
            if len(stream) < 25:
                return  # no reason to try
            response = DirtyJson.parse_string(stream)
            if isinstance(response, dict):
                await self.call_extensions(
                    "response_stream",
                    loop_data=self.loop_data,
                    text=stream,
                    parsed=response,
                )

        except Exception as e:
            pass

    @extensible
    def get_tool(
        self,
        name: str,
        method: str | None,
        args: dict,
        message: str,
        loop_data: LoopData | None,
        **kwargs,
    ):
        from tools.unknown import Unknown
        from helpers.tool import Tool

        classes = []

        # search for tools in agent's folder hierarchy
        paths = subagents.get_paths(self, "tools", name + ".py", default_root="")
        for path in paths:
            try:
                classes = extract_tools.load_classes_from_file(path, Tool)  # type: ignore[arg-type]
                break
            except Exception as e:
                PrintStyle(font_color="orange", padding=False).print(
                    f"Failed to load tool '{name}' from {path}: {e}"
                )
                continue

        tool_class = classes[0] if classes else Unknown
        return tool_class(
            agent=self,
            name=name,
            method=method,
            args=args,
            message=message,
            loop_data=loop_data,
            **kwargs,
        )

    async def call_extensions(self, extension_point: str, **kwargs) -> Any:
        return await call_extensions(
            extension_point=extension_point, agent=self, **kwargs
        )
