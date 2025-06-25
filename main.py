from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import random
import os
import json
from typing import Tuple, Optional, Dict

@register("astrbot_plugin_weakblacklist", "和泉智宏", "弱黑名单插件 ", "1.2", "https://github.com/0d00-Ciallo-0721/astrbot_plugin_weakblackl")
class WeakBlacklistPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 初始化保底回复计数器存储路径
        self.data_dir = os.path.join("data", "WeakBlacklist")
        os.makedirs(self.data_dir, exist_ok=True)
        self.user_counters_path = os.path.join(self.data_dir, "user_interception_counters.json")
        self.group_counters_path = os.path.join(self.data_dir, "group_interception_counters.json")
        
        # 加载拦截计数器
        self.user_interception_counters: Dict[str, int] = {}
        self.group_interception_counters: Dict[str, int] = {}
        self._load_interception_counters()
        
        # 日志记录插件初始化状态
        blacklisted_users = set(str(uid) for uid in self.config.get("blacklisted_users", []))
        blacklisted_groups = set(str(gid) for gid in self.config.get("blacklisted_groups", []))
        logger.info(f"弱黑名单插件已加载，用户黑名单: {len(blacklisted_users)} 个，群聊黑名单: {len(blacklisted_groups)} 个")

    def _load_interception_counters(self):
        """加载用户和群聊被拦截次数记录"""
        # 加载用户拦截计数器
        try:
            if os.path.exists(self.user_counters_path):
                with open(self.user_counters_path, 'r', encoding='utf-8') as f:
                    self.user_interception_counters = json.load(f)
                    # 确保所有值都是整数类型
                    for key in self.user_interception_counters:
                        self.user_interception_counters[key] = int(self.user_interception_counters[key])
            else:
                self.user_interception_counters = {}
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"加载用户拦截计数器失败: {e}")
            self.user_interception_counters = {}

        # 加载群聊拦截计数器
        try:
            if os.path.exists(self.group_counters_path):
                with open(self.group_counters_path, 'r', encoding='utf-8') as f:
                    self.group_interception_counters = json.load(f)
                    # 确保所有值都是整数类型
                    for key in self.group_interception_counters:
                        self.group_interception_counters[key] = int(self.group_interception_counters[key])
            else:
                self.group_interception_counters = {}
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"加载群聊拦截计数器失败: {e}")
            self.group_interception_counters = {}

    def _save_interception_counters(self):
        """保存用户和群聊被拦截次数记录"""
        try:
            # 保存用户拦截计数器
            with open(self.user_counters_path, 'w', encoding='utf-8') as f:
                json.dump(self.user_interception_counters, f, ensure_ascii=False, indent=2)
            
            # 保存群聊拦截计数器
            with open(self.group_counters_path, 'w', encoding='utf-8') as f:
                json.dump(self.group_interception_counters, f, ensure_ascii=False, indent=2)
                
            logger.debug("弱黑名单拦截计数器已保存")
        except Exception as e:
            logger.error(f"保存拦截计数器失败: {e}")

    def _check_blacklist_status(self, event: AstrMessageEvent) -> Tuple[bool, Optional[str], Optional[str]]:
        """直接从配置检查消息是否来自黑名单用户或群聊"""
        sender_id = str(event.get_sender_id())
        group_id = event.get_group_id()

        # 直接从 self.config 获取最新的用户黑名单并检查
        blacklisted_users = set(str(uid) for uid in self.config.get("blacklisted_users", []))
        if sender_id in blacklisted_users:
            return True, "user", sender_id

        # 直接从 self.config 获取最新的群聊黑名单并检查
        if group_id:
            blacklisted_groups = set(str(gid) for gid in self.config.get("blacklisted_groups", []))
            if str(group_id) in blacklisted_groups:
                return True, "group", str(group_id)

        return False, None, None

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10)
    async def check_weak_blacklist(self, event: AstrMessageEvent):
        """检查弱黑名单并进行概率判断，包含保底回复机制"""
        # 检查是否在黑名单中
        is_blacklisted, blacklist_type, target_id = self._check_blacklist_status(event)
        
        if not is_blacklisted:
            # 如果曾经在黑名单中但现在已移除，清除其计数
            sender_id = str(event.get_sender_id())
            group_id = event.get_group_id()
            
            if sender_id in self.user_interception_counters:
                del self.user_interception_counters[sender_id]
                # 注意：不再每次都保存，而是在插件终止时统一保存
            
            if group_id and str(group_id) in self.group_interception_counters:
                del self.group_interception_counters[str(group_id)]
                # 注意：不再每次都保存，而是在插件终止时统一保存
            
            return
        
        # 根据黑名单类型获取相应配置
        if blacklist_type == "user":
            reply_probability = float(self.config.get("reply_probability", 0.3))
            max_interception_cfg = self.config.get("max_interception_count", 5)
            current_count = self.user_interception_counters.get(target_id, 0)
            counters_dict = self.user_interception_counters
        else:  # group
            reply_probability = float(self.config.get("group_reply_probability", 0.3))
            max_interception_cfg = self.config.get("max_group_interception_count", 8)
            current_count = self.group_interception_counters.get(target_id, 0)
            counters_dict = self.group_interception_counters
        
        log_messages = bool(self.config.get("log_blocked_messages", True))
        
        # 确保概率在合理范围内
        reply_probability = max(0.0, min(1.0, reply_probability))
        
        # 解析最大拦截次数，0或负数表示禁用保底机制
        try:
            max_interception_count = int(max_interception_cfg)
            if max_interception_count <= 0:
                max_interception_count = float('inf')  # 禁用保底机制
        except (ValueError, TypeError):
            logger.warning(f"max_interception_count 配置值 '{max_interception_cfg}' 非法，使用默认值")
            max_interception_count = 5 if blacklist_type == "user" else 8
        
        # 决定是否回复
        should_suppress_reply = True
        random_value = random.random()
        sender_name = event.get_sender_name() or "未知用户"
        
        # 生成日志标识
        if blacklist_type == "user":
            log_identifier = f"用户: {sender_name}({target_id})"
        else:
            log_identifier = f"群聊: {target_id} 中的用户: {sender_name}"
        
        # 检查是否触发保底回复
        if current_count + 1 >= max_interception_count:
            # 保底回复，重置计数
            should_suppress_reply = False
            if log_messages:
                logger.info(f"弱黑名单保底回复 - {log_identifier}, "
                           f"已达到最大拦截次数: {current_count}/{max_interception_count}")
            counters_dict[target_id] = 0
        # 如果不是保底回复，进行概率判断
        elif random_value <= reply_probability:
            # 概率允许回复，重置计数
            should_suppress_reply = False
            if log_messages and current_count > 0:
                logger.info(f"弱黑名单概率允许回复 - {log_identifier}, "
                           f"概率: {reply_probability:.2f}, 随机值: {random_value:.3f}, 重置拦截计数")
            counters_dict[target_id] = 0
        else:
            # 拦截回复，增加计数
            should_suppress_reply = True
            counters_dict[target_id] = current_count + 1
            if log_messages:
                message_preview = event.message_str[:50] + ("..." if len(event.message_str) > 50 else "")
                logger.info(f"弱黑名单拦截 - {log_identifier}, "
                           f"消息: {message_preview}, 拦截计数: {counters_dict[target_id]}/{max_interception_count}")
        
        # 注意：不再每次都保存，而是在 terminate 中统一保存
        # self._save_interception_counters() <- 移除此行
        
        # 设置事件标记
        event.set_extra("weak_blacklist_suppress_reply", should_suppress_reply)

    @filter.on_decorating_result(priority=1)
    async def suppress_reply_if_marked(self, event: AstrMessageEvent):
        """
        清空最终要发送的消息链。
        """
        if event.get_extra("weak_blacklist_suppress_reply") is True:
            log_messages = bool(self.config.get("log_blocked_messages", True))
            
            current_result = event.get_result()
            if current_result and hasattr(current_result, 'chain'):
                if log_messages:
                    sender_id = str(event.get_sender_id())
                    group_id = event.get_group_id()
                    identifier = f"群聊 {group_id} 中的用户 {sender_id}" if group_id else f"用户 {sender_id}"
                    original_chain_length = len(current_result.chain)
                    logger.info(f"弱黑名单：替换 {identifier} 的待发送消息链，长度: {original_chain_length}")
                
                # 不完全清空消息链，而是替换为一个空文本消息
                # 这样可以避免其他插件尝试访问chain[0]时出现索引越界错误
                from astrbot.api.message_components import Plain
                current_result.chain.clear()
                current_result.chain.append(Plain(text=""))
            
            # 清除标记，避免对同一事件对象的后续影响
            event.set_extra("weak_blacklist_suppress_reply", False)

    async def terminate(self):
        """插件卸载或关闭时的清理工作"""
        # 在此一次性保存最后的拦截计数，这是最合适的时机
        self._save_interception_counters()
        logger.info("弱黑名单插件已停用，拦截计数已保存。")
