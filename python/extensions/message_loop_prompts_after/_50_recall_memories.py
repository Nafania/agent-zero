import asyncio
from python.helpers.extension import Extension
from python.helpers.memory import Memory
from agent import LoopData
from python.helpers import dirty_json, errors, settings, log
from python.helpers.cognee_init import get_cognee_setting
from python.helpers.print_style import PrintStyle

DATA_NAME_TASK = "_recall_memories_task"
DATA_NAME_ITER = "_recall_memories_iter"
SEARCH_TIMEOUT = 30


class RecallMemories(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        set = settings.get_settings()

        if not set["memory_recall_enabled"]:
            return

        if loop_data.iteration % set["memory_recall_interval"] == 0:
            log_item = self.agent.context.log.log(
                type="util",
                heading="Searching memories...",
            )

            task = asyncio.create_task(
                asyncio.wait_for(
                    self.search_memories(loop_data=loop_data, log_item=log_item, **kwargs),
                    timeout=SEARCH_TIMEOUT,
                )
            )
        else:
            task = None

        self.agent.set_data(DATA_NAME_TASK, task)
        self.agent.set_data(DATA_NAME_ITER, loop_data.iteration)

    async def search_memories(self, log_item: log.LogItem, loop_data: LoopData, **kwargs):
        extras = loop_data.extras_persistent
        if "memories" in extras:
            del extras["memories"]
        if "solutions" in extras:
            del extras["solutions"]

        set = settings.get_settings()

        user_instruction = (
            loop_data.user_message.output_text() if loop_data.user_message else "None"
        )
        history = self.agent.history.output_text()[-set["memory_recall_history_len"]:]

        if set["memory_recall_query_prep"]:
            system = self.agent.read_prompt("memory.memories_query.sys.md")
            message = self.agent.read_prompt(
                "memory.memories_query.msg.md", history=history, message=user_instruction
            )
            try:
                query = await self.agent.call_utility_model(
                    system=system,
                    message=message,
                )
                query = query.strip()
                log_item.update(query=query)
            except Exception as e:
                err = errors.format_error(e)
                self.agent.context.log.log(
                    type="warning", heading="Recall memories extension error:", content=err
                )
                query = ""

            if not query:
                log_item.update(heading="Failed to generate memory query")
                return
        else:
            query = user_instruction + "\n\n" + history

        if not query or len(query) <= 3:
            log_item.update(
                query="No relevant memory query generated, skipping search",
            )
            return

        from python.helpers.memory import _get_cognee
        cognee, SearchType = _get_cognee()
        from cognee.modules.engine.models.node_set import NodeSet

        db = await Memory.get(self.agent)

        datasets = db.get_search_datasets()
        mem_node_name = [Memory.Area.MAIN.value, Memory.Area.FRAGMENTS.value]
        sol_node_name = [Memory.Area.SOLUTIONS.value]

        try:
            session_id = getattr(self.agent.context, 'id', None)
            mem_answers, sol_answers = await asyncio.gather(
                cognee.search(
                    query_text=query,
                    top_k=set["memory_recall_memories_max_search"],
                    datasets=datasets,
                    node_type=NodeSet,
                    node_name=mem_node_name,
                    session_id=session_id,
                ),
                cognee.search(
                    query_text=query,
                    top_k=set["memory_recall_solutions_max_search"],
                    datasets=datasets,
                    node_type=NodeSet,
                    node_name=sol_node_name,
                    session_id=session_id,
                ),
            )
        except Exception as e:
            PrintStyle.error(f"cognee.search failed: {e}")
            mem_answers, sol_answers = [], []

        memories = _to_strings(mem_answers, set["memory_recall_memories_max_result"])
        solutions = _to_strings(sol_answers, set["memory_recall_solutions_max_result"])

        if set["memory_recall_post_filter"] and (memories or solutions):
            memories, solutions = await self._post_filter(
                memories, solutions, history, user_instruction,
            )

        _write_extras(self.agent, extras, memories, solutions, log_item)

    async def _post_filter(self, memories, solutions, history, user_instruction):
        all_items = memories + solutions
        mems_list = {i: text for i, text in enumerate(all_items)}

        try:
            filter_response = await self.agent.call_utility_model(
                system=self.agent.read_prompt("memory.memories_filter.sys.md"),
                message=self.agent.read_prompt(
                    "memory.memories_filter.msg.md",
                    memories=mems_list,
                    history=history,
                    message=user_instruction,
                ),
            )
            filter_inds = dirty_json.try_parse(filter_response)

            if isinstance(filter_inds, list):
                filtered_memories = []
                filtered_solutions = []
                mem_len = len(memories)
                for idx in filter_inds:
                    if isinstance(idx, int):
                        if idx < mem_len:
                            filtered_memories.append(memories[idx])
                        else:
                            sol_idx = idx - mem_len
                            if sol_idx < len(solutions):
                                filtered_solutions.append(solutions[sol_idx])
                memories = filtered_memories
                solutions = filtered_solutions

        except Exception as e:
            err = errors.format_error(e)
            self.agent.context.log.log(
                type="warning", heading="Failed to filter relevant memories", content=err
            )

        return memories, solutions


def _to_strings(answers, limit: int) -> list[str]:
    """Convert cognee.search results to plain strings."""
    if not answers:
        return []

    texts = []
    for answer in answers:
        if len(texts) >= limit:
            break
        text = str(answer)
        if text.startswith("[META:"):
            try:
                meta_end = text.index("]\n")
                text = text[meta_end + 2:]
            except ValueError:
                pass
        texts.append(text)

    return texts


def _write_extras(agent, extras, memories, solutions, log_item):
    if not memories and not solutions:
        log_item.update(heading="No memories or solutions found")
        return

    log_item.update(
        heading=f"{len(memories)} memories and {len(solutions)} relevant solutions found",
    )

    memories_txt = "\n\n".join(memories) if memories else ""
    solutions_txt = "\n\n".join(solutions) if solutions else ""

    if memories_txt:
        log_item.update(memories=memories_txt)
    if solutions_txt:
        log_item.update(solutions=solutions_txt)

    if memories_txt:
        extras["memories"] = agent.parse_prompt(
            "agent.system.memories.md", memories=memories_txt
        )
    if solutions_txt:
        extras["solutions"] = agent.parse_prompt(
            "agent.system.solutions.md", solutions=solutions_txt
        )
