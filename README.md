 # WeakBlacklist 插件

## 简介
弱黑名单插件，可以对指定用户进行概率性回复，同时保持对话上下文的连贯性。与传统黑名单不同，弱黑名单用户的消息会被记录到对话历史中，只是不一定会收到回复。插件还支持保底回复机制，确保黑名单用户不会长时间得不到任何回应。

## 主要是防止多个机器人在一个群聊里面炸群的

## 功能特点
- **概率性回复**：对黑名单用户按设定概率决定是否回复
- **保持上下文**：黑名单用户的消息依然会被大语言模型处理并记录到对话历史
- **保底回复机制**：当用户连续被拦截次数达到设定值时，触发强制回复

## 使用方法
### 管理员命令
- `/weakblacklist list` - 查看当前黑名单列表及每个用户的拦截计数状态

### 工作原理
1. 当黑名单用户发送消息时，插件会检查是否应该回复：
   - 如果用户已连续被拦截次数接近最大值，触发保底回复
   - 否则根据设定的概率决定是否回复
2. 如果决定不回复，用户消息仍会被处理但不会收到回复，同时拦截计数+1
3. 如果决定回复（概率通过或保底触发），拦截计数重置为0

## 注意事项
- 即使不回复，消息也会被发送到大语言模型处理，可能产生API费用
- 如果要完全屏蔽某用户，建议使用其他黑名单插件
- 将黑名单用户从列表中移除后，其拦截计数会自动清除
