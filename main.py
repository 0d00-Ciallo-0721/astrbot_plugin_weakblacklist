from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import random
import os
import json
from typing import Set, Dict

@register("astrbot_plugin_weakblacklist", 
          "和泉智宏", 
          "弱黑名单插件，概率回复黑名单的人", 
          "1.0", 
          "https://github.com/0d00-Ciallo-0721/astrbot_plugin_weakblacklist")
class WeakBlacklistPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 从配置中加载黑名单
        self._load_blacklist_from_config()

        # 初始化保底回复计数器存储
        self.data_dir = os.path.join("data", "WeakBlacklist")
        os.makedirs(self.data_dir, exist_ok=True)
        self.counters_path = os.path.join(self.data_dir, "interception_counters.json")
        self.interception_counters: Dict[str, int] = {}
        self._load_interception_counters()
        
        logger.info(f"弱黑名单插件已加载，当前黑名单用户数: {len(self.blacklisted_users)}")

    def _load_blacklist_from_config(self):
        """从配置文件加载弱黑名单数据"""
        try:
            blacklist_config = self.config.get("blacklisted_users", [])
            self.blacklisted_users: Set[str] = set(str(user_id) for user_id in blacklist_config)
        except Exception as e:
            logger.error(f"加载弱黑名单配置失败: {e}")
            self.blacklisted_users = set()

    def _load_interception_counters(self):
        """加载用户被拦截次数记录"""
        try:
            if os.path.exists(self.counters_path):
                with open(self.counters_path, 'r', encoding='utf-8') as f:
                    self.interception_counters = json.load(f)
                    # 确保所有值都是整数类型
                    for key in self.interception_counters:
                        self.interception_counters[key] = int(self.interception_counters[key])
            else:
                self.interception_counters = {}
                logger.info("拦截计数器文件不存在，已初始化为空")
        except json.JSONDecodeError:
            logger.error(f"拦截计数器文件格式错误，已重置为空")
            self.interception_counters = {}
        except Exception as e:
            logger.error(f"加载拦截计数器失败: {e}")
            self.interception_counters = {}

    def _save_interception_counters(self):
        """保存用户被拦截次数记录"""
        try:
            with open(self.counters_path, 'w', encoding='utf-8') as f:
                json.dump(self.interception_counters, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存拦截计数器失败: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10)
    async def check_weak_blacklist(self, event: AstrMessageEvent):
        """检查弱黑名单并进行概率判断，包含保底回复机制"""
        # 热更新黑名单
        self._load_blacklist_from_config()
        
        sender_id = str(event.get_sender_id())
        
        # 如果发送者不在弱黑名单中，直接放行
        if sender_id not in self.blacklisted_users:
            # 如果曾经在黑名单中但现在已移除，清除其计数
            if sender_id in self.interception_counters:
                del self.interception_counters[sender_id]
                self._save_interception_counters()
            return
        
        # 获取配置
        reply_probability = float(self.config.get("reply_probability", 0.3))
        max_interception_cfg = self.config.get("max_interception_count", 5)
        log_messages = bool(self.config.get("log_blocked_messages", True))
        
        # 确保概率在合理范围内
        reply_probability = max(0.0, min(1.0, reply_probability))
        
        # 解析最大拦截次数，0或负数表示禁用保底机制
        try:
            max_interception_count = int(max_interception_cfg)
            if max_interception_count <= 0:
                max_interception_count = float('inf')  # 禁用保底机制
        except (ValueError, TypeError):
            logger.warning(f"max_interception_count 配置值 '{max_interception_cfg}' 非法，使用默认值5")
            max_interception_count = 5
        
        # 获取当前用户的拦截计数
        current_count = self.interception_counters.get(sender_id, 0)
        
        # 决定是否回复
        should_suppress_reply = True
        random_value = random.random()
        sender_name = event.get_sender_name() or "未知用户"
        
        # 检查是否触发保底回复
        if current_count + 1 >= max_interception_count:
            # 保底回复，重置计数
            should_suppress_reply = False
            if log_messages:
                logger.info(f"弱黑名单保底回复 - 用户: {sender_name}({sender_id}), "
                           f"已达到最大拦截次数: {current_count}/{max_interception_count}")
            self.interception_counters[sender_id] = 0
        # 如果不是保底回复，进行概率判断
        elif random_value <= reply_probability:
            # 概率允许回复，重置计数
            should_suppress_reply = False
            if log_messages and current_count > 0:
                logger.info(f"弱黑名单概率允许回复 - 用户: {sender_name}({sender_id}), "
                           f"概率: {reply_probability:.2f}, 随机值: {random_value:.3f}, 重置拦截计数")
            self.interception_counters[sender_id] = 0
        else:
            # 拦截回复，增加计数
            should_suppress_reply = True
            self.interception_counters[sender_id] = current_count + 1
            if log_messages:
                message_preview = event.message_str[:50] + ("..." if len(event.message_str) > 50 else "")
                logger.info(f"弱黑名单拦截 - 用户: {sender_name}({sender_id}), "
                           f"消息: {message_preview}, 拦截计数: {self.interception_counters[sender_id]}/{max_interception_count}")
        
        # 保存拦截计数
        self._save_interception_counters()
        
        # 设置事件标记
        event.set_extra("weak_blacklist_suppress_reply", should_suppress_reply)

    @filter.on_decorating_result(priority=1)
    async def suppress_reply_if_marked(self, event: AstrMessageEvent):
        """如果消息被标记为抑制回复，则清空最终要发送的消息链"""
        if event.get_extra("weak_blacklist_suppress_reply") is True:
            log_messages = bool(self.config.get("log_blocked_messages", True))
            
            current_result = event.get_result()
            if current_result and hasattr(current_result, 'chain'):
                if log_messages:
                    sender_id = str(event.get_sender_id())
                    original_chain_length = len(current_result.chain)
                    logger.info(f"弱黑名单：清空用户 {sender_id} 的待发送消息链，长度: {original_chain_length}")
                
                # 清空消息链，这样用户就收不到回复了
                current_result.chain.clear()
            
            # 清除标记，避免对同一事件对象的后续影响
            event.set_extra("weak_blacklist_suppress_reply", False)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("weakblacklist list")
    async def list_blacklist(self, event: AstrMessageEvent):
        """查看弱黑名单列表"""
        # 重新从配置加载黑名单
        self._load_blacklist_from_config()
        
        if not self.blacklisted_users:
            yield event.plain_result("弱黑名单为空")
            return
        
        probability = float(self.config.get("reply_probability", 0.3))
        max_interception = self.config.get("max_interception_count", 5)
        
        # 生成带拦截计数的用户列表
        users_list = []
        for user_id in sorted(self.blacklisted_users):
            count = self.interception_counters.get(user_id, 0)
            users_list.append(f"{user_id} (拦截计数: {count})")
        
        message = f"弱黑名单用户列表 (共 {len(self.blacklisted_users)} 个)\n"
        message += f"回复概率: {probability:.1%}\n"
        message += f"最大连续拦截次数: {max_interception}\n"
        message += f"保持对话上下文: 是\n\n"
        message += "\n".join(users_list)
        
        yield event.plain_result(message)

    async def terminate(self):
        """插件卸载时的清理工作"""
        # 保存最后的拦截计数
        self._save_interception_counters()
        logger.info("弱黑名单插件已停用")
