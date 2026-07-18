下面给出一份**Hermes Agent 多 Agent / 子 Agent（profile、agent slot、delegated agent 或 specialized agent）添加与运维说明**。目标是：

* 主 Agent 保持通用能力；
* 新增一个独立的“特殊内容处理 Agent”；
* 该 Agent 使用独立 system prompt / persona；
* 指定 Ollama 作为 provider；
* 可由主 Agent 路由调用。

Hermes 的配置主体位于 `~/.hermes/`，核心配置文件是 `config.yaml`。Provider、模型和 agent 配置都在这里管理。([GitHub][1])

---

# Hermes Agent 增加专项 Agent（Preset/Profile）运维说明

## 1. 架构说明

推荐采用如下结构：

```
                User
                  |
                  v
          +---------------+
          | Main Hermes   |
          | Agent         |
          +---------------+
                  |
        delegation / routing
                  |
      +-----------+------------+
      |                        |
      v                        v

+--------------+       +--------------+
| General      |       | Specialist   |
| Agent        |       | Agent        |
| Claude/GPT   |       | Ollama       |
+--------------+       +--------------+

                         |
                         v

                 qwen / llama / mistral
                 Ollama runtime
```

用途：

| Agent            | Provider | 用途                   |
| ---------------- | -------- | -------------------- |
| Main Agent       | 云端模型     | 日常任务、规划、工具调用         |
| Specialist Agent | Ollama   | 私密数据、本地知识、代码审查、文档分析等 |

---

# 2. 环境准备

## 2.1 安装 Ollama

确认：

```bash
ollama --version
```

启动：

```bash
ollama serve
```

默认 API：

```
http://127.0.0.1:11434
```

Hermes 使用 Ollama 的 OpenAI-compatible endpoint：

```
http://127.0.0.1:11434/v1
```

([Ollama][2])

---

## 2.2 下载模型

例如：

```bash
ollama pull qwen3:32b
```

或者：

```bash
ollama pull llama3.1:8b
```

检查：

```bash
ollama list
```

输出：

```
NAME              SIZE
qwen3:32b         20GB
llama3.1:8b       5GB
```

---

# 3. Hermes 配置目录

进入：

```bash
cd ~/.hermes
```

结构：

```
~/.hermes/
|
├── config.yaml
├── SOUL.md
├── agents/
│
├── skills/
└── memories/
```

官方配置默认使用：

```
~/.hermes/config.yaml
```

管理 provider、model 等。([GitHub][1])

---

# 4. 添加 Ollama Provider

编辑：

```bash
vim ~/.hermes/config.yaml
```

加入：

```yaml
providers:

  ollama-local:
    name: ollama-local
    api:
      base_url: http://127.0.0.1:11434/v1
    type: openai-compatible
```

说明：

| 字段                | 作用               |
| ----------------- | ---------------- |
| ollama-local      | provider 名称      |
| base_url          | Ollama API 地址    |
| openai-compatible | 兼容 OpenAI API 格式 |

Hermes 支持通过 custom endpoint 连接 Ollama。([GitHub][3])

---

# 5. 创建专项 Agent

假设创建：

```
security-review-agent
```

用途：

> 专门处理安全审计、漏洞分析、代码扫描。

创建目录：

```bash
mkdir -p ~/.hermes/agents/security-review-agent
```

结构：

```
agents/
└── security-review-agent/
    |
    ├── agent.yaml
    └── SOUL.md
```

---

# 6. 编写 Agent 配置

创建：

```bash
vim ~/.hermes/agents/security-review-agent/agent.yaml
```

内容：

```yaml
name: security-review-agent

description:
  Security analysis specialist

model:
  provider: ollama-local
  name: qwen3:32b

temperature:
  0.1

context_length:
  64000

tools:
  enabled:
    - file
    - terminal
```

说明：

* 使用独立 provider；
* 不影响主 Agent；
* 温度降低，提高审计稳定性；
* 使用本地模型。

Hermes 对 Ollama 建议显式设置 context length，避免 Ollama 默认 context 较小导致 Agent 能力下降。([GitHub][4])

---

# 7. 创建 Agent Persona

创建：

```bash
vim ~/.hermes/agents/security-review-agent/SOUL.md
```

示例：

```markdown
# Identity

You are a cybersecurity review specialist.

Your responsibility:

- Analyze source code vulnerabilities
- Review authentication logic
- Identify security risks
- Provide remediation suggestions

Rules:

1. Never modify production code directly.
2. Always explain risk severity.
3. Provide CVSS-style reasoning.
4. Prefer defensive recommendations.
```

---

# 8. 注册 Agent

在：

```
~/.hermes/config.yaml
```

增加：

```yaml
agents:

  security-review:
    path: ~/.hermes/agents/security-review-agent
```

最终：

```yaml
agents:

  security-review:
    path: ~/.hermes/agents/security-review-agent


providers:

  ollama-local:
    name: ollama-local
    api:
      base_url: http://127.0.0.1:11434/v1
    type: openai-compatible
```

---

# 9. 测试 Provider

测试 Ollama：

```bash
curl http://127.0.0.1:11434/v1/models
```

应该返回：

```json
{
 "data":[
   {
     "id":"qwen3:32b"
   }
 ]
}
```

---

# 10. 测试 Hermes 模型切换

进入 Hermes：

```bash
hermes chat
```

检查：

```
/model
```

切换：

```
/model ollama-local:qwen3:32b
```

官方支持通过 `/model` 切换 provider/model。([GitHub][4])

---

# 11. 主 Agent 调用专项 Agent

推荐增加 delegation skill。

例如：

```
~/.hermes/SOUL.md
```

加入：

```markdown
When user requests:

- security audit
- vulnerability analysis
- code security review

delegate task to:

security-review-agent
```

效果：

用户：

> 帮我检查这个 API 是否安全

流程：

```
Main Agent

    |
    |
    +--> security-review-agent

              |
              |
          Ollama qwen3:32b

              |
              |
          security report
```

---

# 12. 运维管理

## 查看 Agent

```bash
ls ~/.hermes/agents
```

---

## 修改模型

例如从：

```
qwen3:32b
```

换：

```
deepseek-r1:32b
```

修改：

```yaml
model:
  name: deepseek-r1:32b
```

无需改变主 Agent。

---

## 更新 Ollama 模型

查看：

```bash
ollama list
```

删除：

```bash
ollama rm old-model
```

升级：

```bash
ollama pull qwen3:32b
```

---

## 日志排查

查看：

```bash
journalctl -u ollama
```

检查 Hermes：

```bash
tail -f ~/.hermes/logs/*
```

---

# 13. 常见故障

## 问题1：Agent 找不到 Ollama

错误：

```
connection refused
```

检查：

```bash
ps aux | grep ollama
```

启动：

```bash
ollama serve
```

---

## 问题2：模型能聊天但是不会调用工具

原因：

很多本地模型工具调用能力弱。

建议：

| 模型             | 工具能力 |
| -------------- | ---- |
| Qwen 系列        | 较好   |
| Llama 小模型      | 一般   |
| 纯 reasoning 模型 | 可能较差 |

社区也反馈本地小模型在 Hermes tool calling 上容易受限，需要更大的模型或更强工具训练模型。([Reddit][5])

---

## 问题3：上下文不足

检查：

```bash
ollama show gemma4:31b
```

运行：

```bash
ollama run show gemma4:31b --ctx-size 85536
```

Hermes Agent 长上下文任务建议至少 64K context。([GitHub][3])

---

# 14. 推荐生产部署方式

目录：

```
~/.hermes/

config.yaml
|
+-- main agent
|
+-- agents/
      |
      +-- security-agent
      |
      +-- coding-agent
      |
      +-- private-doc-agent
```

Provider：

```
cloud provider
        |
        |
Main Agent


ollama provider
        |
        |
Special Agents
```

这样可以做到：

* 公共任务走强模型；
* 私密任务走本地模型；
* 专项 Agent 独立升级；
* 不污染主 Agent memory；
* 降低 token 成本。

---

补充说明：Hermes 当前文档里更常见的叫法是 **agent profile / specialized agent / delegated agent**，你说的 “preset” 在运维语境里可以理解，但如果写内部文档，建议统一叫 **Specialized Agent Profile（专项 Agent Profile）**。

[1]: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/configuration.md?utm_source=chatgpt.com "hermes-agent/website/docs/user-guide/configuration.md at main · NousResearch/hermes-agent · GitHub"
[2]: https://docs.ollama.com/integrations/hermes?utm_source=chatgpt.com "Hermes Agent - Ollama"
[3]: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/faq.md?utm_source=chatgpt.com "hermes-agent/website/docs/reference/faq.md at main · NousResearch/hermes-agent · GitHub"
[4]: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/integrations/providers.md?utm_source=chatgpt.com "hermes-agent/website/docs/integrations/providers.md at main · NousResearch/hermes-agent · GitHub"
[5]: https://www.reddit.com/r/hermesagent/comments/1teynbf/hermes_x_ollama_configuration/?utm_source=chatgpt.com "Hermes x Ollama Configuration?"
