from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import asyncio
import time

@register("chatlock", "YourName", "Chat 指令独占锁，防止并发卡顿", "1.0.0")
class ChatLockPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.lock = asyncio.Lock()          # 全局锁
        # 记录当前占用者（仅用于日志）
        self.current_user: str = ""

    # === 核心：拦截 /chat 命令 ==========================================
    @filter.command("chat")
    async def chat(self, event: AstrMessageEvent):
        """/chat 内容  → 带锁的 AI 对话"""
        # 1. 抢占锁
        if self.lock.locked():
            # 构造 @ 消息
            at_seg = [Comp.At(qq=event.get_sender_id())] if event.get_group_id() else []
            chain = at_seg + [Comp.Plain(" 目前正在使用中，请稍后再试")]
            yield event.chain_result(chain)
            return

        # 2. 拿到锁，开始聊天
        async with self.lock:
            self.current_user = f"{event.get_sender_name()}({event.get_sender_id()})"
            logger.info(f"[ChatLock] 开始为 {self.current_user} 生成回复...")
            try:
                # ======  调用 AstrBot 原生 LLM  ======
                prov_id = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
                llm_resp = await self.context.llm_generate(
                    chat_provider_id=prov_id,
                    prompt=event.message_str.removeprefix("/chat").strip()
                )
                yield event.plain_result(llm_resp.completion_text)
            except Exception as e:
                logger.exception("LLM 调用失败")
                yield event.plain_result(f"生成失败：{e}")
            finally:
                logger.info(f"[ChatLock] 释放锁，当前占用者 {self.current_user} 完成")
                self.current_user = ""

    # === 可选：管理员强制解锁 ==========================================
    @filter.command("unlock")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def unlock(self, event: AstrMessageEvent):
        if self.lock.locked():
            # 偷偷释放（不会中断正在跑的协程，只是让下一个人能进）
            self.lock.release()
            self.current_user = ""
            yield event.plain_result("已强制解锁 /chat 占用。")
        else:
            yield event.plain_result("当前无人占用。")

# === 消息组件别名，方便使用 ============================================
from astrbot.api.message_components import At, Plain as Comp
