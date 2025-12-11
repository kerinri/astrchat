import asyncio
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Star, register, Context
from astrbot.api import logger
from astrbot.api.message_components import Plain, At

LLM_LOCK = asyncio.Lock()

@register("llm_lock", "YourName", "LLM 结果独占锁", "1.0.0")
class LlmLockPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        logger.info("[LlmLock] 插件加载，全局锁 ID: %s", id(LLM_LOCK))

    @filter.on_decorating_result(priority=999)
    async def on_decorating_result(self, event: AstrMessageEvent):
        """在框架即将把 LLM 结果发到平台前拦截"""
        # 只处理 LLM 结果
        if getattr(event, "result_content_type", None) != "llm_result":
            return

        if LLM_LOCK.locked():
            at_seg = [At(qq=event.get_sender_id())] if event.get_group_id() else []
            await self.context.send_message(
                event.unified_msg_origin,
                MessageChain(at_seg + [Plain(" 请稍后再试")])
            )
            event.stop_event()                    # 阻止发送
            logger.info("[LlmLock] 拒绝并发 LLM 结果，sender=%s", event.get_sender_id())
            return

        await LLM_LOCK.acquire()
        logger.info("[LlmLock] 获得全局锁，sender=%s", event.get_sender_id())

    @filter.after_message_sent(priority=999)
    async def after_message_sent(self, event: AstrMessageEvent):
        """消息真正发出去后释放锁"""
        if LLM_LOCK.locked():
            LLM_LOCK.release()
            logger.info("[LlmLock] 全局锁已释放")

    async def terminate(self):
        if LLM_LOCK.locked():
            LLM_LOCK.release()
