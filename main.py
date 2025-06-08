from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import random
import os
import json
from typing import Set, Dict

@register("astrbot_plugin_weakblacklist", "和泉智宏", "弱黑名单插件 - 支持用户和群聊，带保底回复，保持对话上下文", "1.1.0", "https://github.com/0d00-Ciallo-0721/astrbot_plugin_weakblacklist")
class WeakBlacklistPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 从配置中加载黑名单
        self._load_blacklists_from_config()

        # 初始化保底回复计数器存储
        self.data_dir = os.path.join("data", "WeakBlacklist")
        os.makedirs(self.data_dir, exist_ok=True)
        self.user_counters_path = os.path.join(self.data_dir, "user_interception_counters.json")
        self.group_counters_path = os.path.join(self.data_dir, "group_interception_counters.json")
        
        self.user_interception_counters: Dict[str, int] = {}
        self.group_interception_counters: Dict[str, int] = {}
        
        self._load_interception_counters()
        
        logger.info(f"弱黑名单插件已加载，用户黑名单: {len(self.blacklisted_users)} 个，群聊黑名单: {len(self.blacklisted_groups)} 个")

    def _load_blacklists_from_config(self):
        """从配置文件加载弱黑名单数据"""
        try:
            # 加载用户黑名单
            user_blacklist_config = self.config.get("blacklisted_users", [])
            self.blacklisted_users: Set[str] = set(str(user_id) for user_id in user_blacklist_config)
            
            # 加载群聊黑名单
            group_blacklist_config = self.config.get("blacklisted_groups", [])
            self.blacklisted_groups: Set[str] = set(str(group_id) for group_id in group_blacklist_config)
        except Exception as e:
            logger.error(f"加载弱黑名单配置失败: {e}")
            self.blacklisted_users = set()
            self.blacklisted_groups = set()

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
        except Exception as e:
            logger.error(f"保存拦截计数器失败: {e}")

    def _check_blacklist_status(self, event: AstrMessageEvent):
        """检查消息是否来自黑名单用户或群聊，返回 (is_blacklisted, blacklist_type, target_id)"""
        sender_id = str(event.get_sender_id())
        group_id = event.get_group_id()
        
        # 检查用户黑名单
        if sender_id in self.blacklisted_users:
            return True, "user", sender_id
        
        # 检查群聊黑名单
        if group_id and str(group_id) in self.blacklisted_groups:
            return True, "group", str(group_id)
        
        return False, None, None

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10)
    async def check_weak_blacklist(self, event: AstrMessageEvent):
        """检查弱黑名单并进行概率判断，包含保底回复机制"""
        # 热更新黑名单
        self._load_blacklists_from_config()
        
        # 检查是否在黑名单中
        is_blacklisted, blacklist_type, target_id = self._check_blacklist_status(event)
        
        if not is_blacklisted:
            # 如果曾经在黑名单中但现在已移除，清除其计数
            sender_id = str(event.get_sender_id())
            group_id = event.get_group_id()
            
            if sender_id in self.user_interception_counters:
                del self.user_interception_counters[sender_id]
                self._save_interception_counters()
            
            if group_id and str(group_id) in self.group_interception_counters:
                del self.group_interception_counters[str(group_id)]
                self._save_interception_counters()
            
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
                    group_id = event.get_group_id()
                    identifier = f"群聊 {group_id} 中的用户 {sender_id}" if group_id else f"用户 {sender_id}"
                    original_chain_length = len(current_result.chain)
                    logger.info(f"弱黑名单：清空 {identifier} 的待发送消息链，长度: {original_chain_length}")
                
                # 清空消息链，这样用户就收不到回复了
                current_result.chain.clear()
            
            # 清除标记，避免对同一事件对象的后续影响
            event.set_extra("weak_blacklist_suppress_reply", False)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("weakblacklist list")
    async def list_blacklist(self, event: AstrMessageEvent):
        """查看弱黑名单列表"""
        # 重新从配置加载黑名单
        self._load_blacklists_from_config()
        
        user_probability = float(self.config.get("reply_probability", 0.3))
        group_probability = float(self.config.get("group_reply_probability", 0.3))
        max_user_interception = self.config.get("max_interception_count", 5)
        max_group_interception = self.config.get("max_group_interception_count", 8)
        
        message_parts = []
        
        # 用户黑名单部分
        if self.blacklisted_users:
            message_parts.append(f"弱黑名单用户 (共 {len(self.blacklisted_users)} 个)")
            message_parts.append(f"回复概率: {user_probability:.1%}")
            message_parts.append(f"最大连续拦截次数: {max_user_interception}")
            message_parts.append("")
            
            for user_id in sorted(self.blacklisted_users):
                count = self.user_interception_counters.get(user_id, 0)
                message_parts.append(f"用户 {user_id} (拦截计数: {count})")
        else:
            message_parts.append("用户黑名单为空")
        
        message_parts.append("")
        message_parts.append("=" * 30)
        message_parts.append("")
        
        # 群聊黑名单部分
        if self.blacklisted_groups:
            message_parts.append(f"弱黑名单群聊 (共 {len(self.blacklisted_groups)} 个)")
            message_parts.append(f"回复概率: {group_probability:.1%}")
            message_parts.append(f"最大连续拦截次数: {max_group_interception}")
            message_parts.append("")
            
            for group_id in sorted(self.blacklisted_groups):
                count = self.group_interception_counters.get(group_id, 0)
                message_parts.append(f"群聊 {group_id} (拦截计数: {count})")
        else:
            message_parts.append("群聊黑名单为空")
        
        message_parts.append("")
        message_parts.append("保持对话上下文: 是")
        
        yield event.plain_result("\n".join(message_parts))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("weakblacklist status")
    async def show_status(self, event: AstrMessageEvent):
        """显示弱黑名单插件状态概览"""
        self._load_blacklists_from_config()
        
        user_probability = float(self.config.get("reply_probability", 0.3))
        group_probability = float(self.config.get("group_reply_probability", 0.3))
        max_user_interception = self.config.get("max_interception_count", 5)
        max_group_interception = self.config.get("max_group_interception_count", 8)
        log_blocked = bool(self.config.get("log_blocked_messages", True))
        
        # 统计拦截计数
        total_user_interceptions = sum(self.user_interception_counters.values())
        total_group_interceptions = sum(self.group_interception_counters.values())
        
        status_msg = f"弱黑名单插件状态概览\n\n"
        status_msg += f"用户黑名单: {len(self.blacklisted_users)} 个\n"
        status_msg += f"群聊黑名单: {len(self.blacklisted_groups)} 个\n"
        status_msg += f"用户回复概率: {user_probability:.1%}\n"
        status_msg += f"群聊回复概率: {group_probability:.1%}\n"
        status_msg += f"用户最大拦截次数: {max_user_interception}\n"
        status_msg += f"群聊最大拦截次数: {max_group_interception}\n"
        status_msg += f"日志记录: {'开启' if log_blocked else '关闭'}\n"
        status_msg += f"累计用户拦截次数: {total_user_interceptions}\n"
        status_msg += f"累计群聊拦截次数: {total_group_interceptions}"
        
        yield event.plain_result(status_msg)

    async def terminate(self):
        """插件卸载时的清理工作"""
        # 保存最后的拦截计数
        self._save_interception_counters()
        logger.info("弱黑名单插件已停用")
