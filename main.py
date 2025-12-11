import asyncio
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Star, register, Context
from astrbot.api import logger
from astrbot.api.message_components import Plain, At

# 全局锁：任何对话、任何提供商都串行
LLM_LOCK = asyncio.Lock()

@register("llm_lock", "YourName", "LLM 调用独占锁，防止并发卡顿", "1.0.0")
class LlmLockPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        logger.info("[LlmLock] 插件加载成功，全局锁 ID: %s", id(LLM_LOCK))

    @filter.on_llm_request(priority=999)          # 最高优先级，最先执行
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """在框架真正调用 LLM 之前拦截"""
        if LLM_LOCK.locked():
            # 占锁中 → 立即拒绝
            at_seg = [At(qq=event.get_sender_id())] if event.get_group_id() else []
            chain = at_seg + [Plain(" 请稍后再试")]
            await self.context.send_message(event.unified_msg_origin, MessageChain(chain))
            req.prompt = ""                       # 清空 prompt → 框架跳过 LLM 调用
            event.stop_event()                    # 阻止后续所有插件继续处理
            logger.info("[LlmLock] 拒绝并发请求，sender=%s", event.get_sender_id())
            return

        # 抢到锁
        await LLM_LOCK.acquire()
        logger.info("[LlmLock] 获得全局锁，sender=%s", event.get_sender_id())

    @filter.on_llm_response(priority=999)        # 最后释放锁
    async def on_llm_response(self, event: AstrMessageEvent, resp):
        """LLM 返回后释放锁"""
        if LLM_LOCK.locked():
            LLM_LOCK.release()
            logger.info("[LlmLock] 全局锁已释放")

    async def terminate(self):
        if LLM_LOCK.locked():
            LLM_LOCK.release()
