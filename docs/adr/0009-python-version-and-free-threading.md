# Python 采用 3.14 标准构建；不使用 3.15，不使用 free-threaded（无 GIL）构建

## 背景与决策

技术栈文档原先写定 Python 3.12。2026-09-13 有人提出改用 **3.14 或 3.15**，并使用**无 GIL 的 free-threaded 构建**。

**决策**：
1. **Python 采用 3.14 标准构建**（有 GIL），在 `pyproject.toml` 中约束为 `>=3.14,<3.15`。
2. **不使用 Python 3.15**（当前为 beta，未正式发布）。
3. **不使用 free-threaded 构建**，并在环境自检中**显式拒绝** free-threaded 解释器。

## 实测证据（2026-09-13）

在本机对两个解释器做了**完整运行时验证**（不止 import，而是真实路由、序列化、签名、并发），而非查阅资料：

| 验证项 | 标准 3.14.4（有 GIL） | free-threaded 3.14.5t（GIL 禁用） |
| --- | --- | --- |
| FastAPI 路由 + Pydantic 校验 | ✅ 正常请求 200 / 校验拒绝 422 | ✅ 同 |
| Pydantic 序列化（ID 字符串契约） | ✅ 无损 | ✅ 同 |
| SQLAlchemy 引擎 + 唯一约束 | ✅ | ✅ 同 |
| Pillow PNG 往返 / cryptography RSA-2048 签名验签 / bcrypt / PyJWT | ✅ | ✅ 同 |
| asyncio / httpx | ✅ | ✅ 同 |
| **多线程 CPU 并行度** | 单线程 0.040s → 4 线程 0.164s，**比值 4.12（无加速）** | 单线程 0.046s → 4 线程 0.060s，**比值 1.29（真并行）** |
| **一期核心依赖安装** | ✅ 成功 | ✅ 成功 |
| **`chromadb` + `langchain` 安装** | ✅ **成功**（chromadb 1.5.9 + tokenizers 0.23.2 + onnxruntime 1.30.0 + numpy 2.5.3） | ❌ **失败** |

**free-threaded 上的失败过程值得记录**：依赖解析器**没有报"不支持"**，而是退回 `chromadb 0.3.23`（2023 年的版本），随后其传递依赖 `tokenizers` 无 free-threaded 轮子，需从源码编译，uv 尝试自动安装 Rust 工具链并失败。

> ⚠️ **这类失败最具迷惑性**：它不是明确的错误，而是**静默降级到一个远古版本**，直到安装中途才崩溃。若只看"包装上了没有"，会误以为兼容。

## 理由

### 1. 为什么不用 Python 3.15

当前最新为 `3.15.0b1`，处于 **beta 阶段且未正式发布**。课程项目只有 4–6 周与 4 名开发者，使用 beta 解释器会使故障排查无法区分"自身缺陷"与"解释器缺陷"，收益为零而风险明确。

### 2. 为什么不用 free-threaded：三重理由，任一即足够

**(a) 本项目的负载是 I/O 密集型，free-threading 无收益。**
本项目的耗时集中在等待外部能力返回：LLM 推断、OCR 识别、数据库查询、对象存储读写。`httpx` 在发起请求时**会释放 GIL**，`asyncio` 已能并发这些等待。free-threading 的收益只体现在**多线程 CPU 密集计算**上，而本架构恰恰把这类工作全部外推给了外部 API —— 我们的后端几乎不做 CPU 密集计算。

**(b) 生态缺口是真实且致命的。**
实测已证明一期的核心依赖 `chromadb` 在 free-threaded 上无法安装。RAG 链路是本项目一期的**核心功能**，不是可选项。

**(c) 内存与单线程性能更差，而服务器内存是最紧张的资源。**
free-threaded 构建以**更高的内存占用**与**更差的单线程性能**为代价（官方文档明确说明）。目标服务器仅 1.7 GiB 内存、可用约 950 MiB，这是本项目的硬约束（见 ADR-0008）。

### 3. 为什么是 3.14 而不是继续用 3.12

3.14 已发布且稳定（当前 3.14.5），全栈依赖在该版本上**实测全部可用**；且开发机已安装 3.14.4。继续停留在 3.12 没有收益，而 3.14 是当前稳定基线。

## 被否决的替代方案

| 方案 | 否决理由 |
| --- | --- |
| **Python 3.15** | beta 阶段未正式发布，故障归因困难，收益为零 |
| **free-threaded 3.14t** | `chromadb` 无法安装（实测）；I/O 密集型负载无收益；内存与单线程性能更差 |
| **继续用 Python 3.12** | 无收益；3.14 已稳定且开发机已具备 |
| **Python 3.13** | 可行，但无理由放弃 3.14 的两年支持窗口 |

## 后果

- `pyproject.toml` 中约束 **`requires-python = ">=3.14,<3.15"`**；`uv.lock` 锁定具体版本。
- **环境自检必须拒绝 free-threaded 解释器**，理由见下一条。
- `GET /health` 的响应增加 `python` 与 `free_threading` 字段，使运行环境在部署后可自查（见 [05-接口设计](../05-接口设计.md) §5.7）。

### ⚠️ 一个必须写进代码的陷阱：`uv venv --python 3.14` 会选中 free-threaded 解释器

**实测复现**（2026-09-13）：执行 `uv venv --python 3.14` 后，创建出的环境 `Py_GIL_DISABLED = 1`、`GIL 启用 = False` —— 即**它选中了 free-threaded 构建**，因为该解释器已在 uv 的托管目录中且满足 `3.14` 的版本约束。

**这意味着团队成员在执行文档里写的"创建 3.14 环境"命令时，可能不知不觉拿到一个 free-threaded 环境**，然后在安装 `chromadb` 时失败，且极难定位原因（报错指向 Rust 工具链，与 Python 无关）。

**因此要求**：应用启动时**强制自检**，若检测到 free-threaded 解释器则**拒绝启动**并给出明确指引：

```python
import sys, sysconfig

if sysconfig.get_config_var("Py_GIL_DISABLED"):
    raise RuntimeError(
        "检测到 free-threaded Python（无 GIL 构建）。本项目要求标准构建："
        "chromadb 等核心依赖在 free-threaded 上无法安装（见 ADR-0009）。"
        "请用绝对路径指定解释器重建环境，例如："
        "uv venv --python 3.14.4 或 uv venv --python <标准解释器绝对路径>"
    )
```

**创建环境时使用绝对路径最稳妥**（实测：指定绝对路径的标准解释器可正确创建有 GIL 的环境）：

```powershell
uv venv --python "C:\Users\<用户>\AppData\Local\Python\pythoncore-3.14-64\python.exe"
```

> **fail-fast 优于事后排查**：这个自检只花两行代码，但能避免"某位成员的环境装不上 chromadb 却查不出原因"这类会浪费半天的团队问题。
